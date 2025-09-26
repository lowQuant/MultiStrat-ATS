"""
ArcticDB browsing routes
Provides endpoints to list libraries, list symbols in a library, and read table data
"""
import json

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any, Literal

from core.strategy_manager import StrategyManager

router = APIRouter(prefix="/api/arctic", tags=["arctic"])

# Injected by main.py
strategy_manager: Optional[StrategyManager] = None

def set_strategy_manager(sm: StrategyManager):
    global strategy_manager
    strategy_manager = sm


def _get_ac():
    if strategy_manager is None:
        raise HTTPException(status_code=503, detail="Strategy manager not initialized")
    ac = strategy_manager.ac if getattr(strategy_manager, 'ac', None) is not None else strategy_manager.get_arctic_client()
    if ac is None:
        raise HTTPException(status_code=503, detail="Arctic client not available")
    return ac


@router.get("/libraries")
async def list_libraries() -> Dict[str, Any]:
    try:
        ac = _get_ac()
        libs = ac.list_libraries()
        return {"success": True, "libraries": libs}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/delete_library")
async def delete_library(
    library: str = Query(..., description="Library name"),
) -> Dict[str, Any]:
    """Delete a library from ArcticDB."""
    try:
        ac = _get_ac()
        libs = ac.list_libraries()
        if library not in libs:
            raise HTTPException(status_code=404, detail=f"Library '{library}' not found")
        # Drop the library
        ac.delete_library(library)
        return {"success": True, "message": f"Deleted library '{library}'"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/symbols")
async def list_symbols(library: str = Query(..., description="Library name")) -> Dict[str, Any]:
    try:
        ac = _get_ac()
        lib = ac.get_library(library)
        symbols = lib.list_symbols()
        return {"success": True, "symbols": symbols}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/read")
async def read_table(
    library: str = Query(..., description="Library name"),
    symbol: str = Query(..., description="Symbol name"),
    limit: int = Query(200, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    sort_by: Optional[str] = Query(None, description="Column header to sort by (use the header label). Pass '__index__' for the index column."),
    sort_order: Literal["asc", "desc"] = Query("asc", description="Sort order"),
    filters: Optional[str] = Query(None, description="JSON-encoded list of filters, e.g. [{\"column\":\"symbol\",\"operator\":\"eq\",\"value\":\"AAPL\"}]"),
) -> Dict[str, Any]:
    """Read a table and return a simple JSON structure with columns and rows.
    Supports basic pagination via offset/limit to avoid sending huge payloads.
    """
    try:
        ac = _get_ac()
        lib = ac.get_library(library)
        if not lib.has_symbol(symbol):
            raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found in '{library}'")
        # Parse filters if provided
        filter_items: List[Dict[str, Any]] = []
        if filters:
            try:
                filter_items = _parse_filters(filters)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        # Determine total rows without materializing the full table when possible
        total_rows = None
        try:
            description = lib.get_description(symbol)  # type: ignore[attr-defined]
            total_rows = getattr(description, "rows", None)
        except Exception:
            total_rows = None

        ascending = sort_order != "desc"
        normalize_index = False
        index_aliases = {"__index__", "index", None, ""}

        if sort_by in index_aliases and not filter_items:
            # Efficient pagination by index when possible
            if total_rows is not None:
                if total_rows == 0 or offset >= total_rows:
                    return {"success": True, "columns": [], "rows": [], "total": total_rows}

                if ascending:
                    start = offset
                    end = min(offset + limit, total_rows)
                else:
                    start = max(total_rows - offset - limit, 0)
                    end = total_rows - offset
                if start >= end:
                    return {"success": True, "columns": [], "rows": [], "total": total_rows}

                df_chunk = lib.read(symbol, row_range=(start, end)).data
                if df_chunk is None or df_chunk.empty:
                    return {"success": True, "columns": [], "rows": [], "total": total_rows}

                df_reset = df_chunk.reset_index()
                if not ascending:
                    df_reset = df_reset.iloc[::-1].reset_index(drop=True)

                columns = [str(c) for c in df_reset.columns]
                rows = [list(map(_to_jsonable, row)) for row in df_reset.itertuples(index=False, name=None)]
                return {"success": True, "columns": columns, "rows": rows, "total": total_rows}
            else:
                normalize_index = True

        # Fallback: materialize the full dataframe for arbitrary column sorting or missing metadata
        df = lib.read(symbol).data
        if df is None:
            return {"success": True, "columns": [], "rows": [], "total": 0}

        df_reset = df.reset_index() if normalize_index or sort_by in index_aliases else df.reset_index()

        if filter_items:
            try:
                df_reset = _apply_filters(df_reset, filter_items)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            if df_reset.empty:
                return {"success": True, "columns": [str(c) for c in df_reset.columns], "rows": [], "total": 0}

        chosen_column = sort_by if sort_by not in index_aliases else df_reset.columns[0]
        if chosen_column not in df_reset.columns:
            chosen_column = df_reset.columns[0]

        df_sorted = df_reset.sort_values(by=chosen_column, ascending=ascending, kind="mergesort", na_position="last")

        total = len(df_sorted)
        start = min(offset, total)
        end = min(offset + limit, total)
        paged = df_sorted.iloc[start:end]

        columns = [str(c) for c in paged.columns]
        rows = [list(map(_to_jsonable, row)) for row in paged.itertuples(index=False, name=None)]
        return {"success": True, "columns": columns, "rows": rows, "total": total}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


def _to_jsonable(v: Any):
    try:
        import pandas as pd
        if isinstance(v, (pd.Timestamp, )):
            return v.isoformat()
    except Exception:
        pass
    try:
        import numpy as np
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
    except Exception:
        pass
    return v


_ALLOWED_FILTER_OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "contains", "startswith", "endswith"}


def _parse_filters(raw_filters: str) -> List[Dict[str, Any]]:
    try:
        payload = json.loads(raw_filters)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid filters payload: {exc.msg}")

    if not isinstance(payload, list):
        raise ValueError("Filters payload must be a list")

    parsed: List[Dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        column = item.get("column")
        operator = item.get("operator")
        value = item.get("value")
        if not column or not operator:
            continue
        if operator not in _ALLOWED_FILTER_OPERATORS:
            raise ValueError(f"Unsupported filter operator '{operator}'")
        parsed.append({"column": str(column), "operator": operator, "value": value})

    return parsed


def _apply_filters(df, filters: List[Dict[str, Any]]):
    if df is None or df.empty or not filters:
        return df

    try:
        import pandas as pd
        from pandas.api.types import (
            is_bool_dtype,
            is_datetime64_any_dtype,
            is_numeric_dtype,
        )
    except Exception as exc:
        raise ValueError(f"Filtering requires pandas: {exc}")

    index_column = df.columns[0] if len(df.columns) else None
    current = df

    for flt in filters:
        column_key = flt.get("column")
        operator = flt.get("operator")
        value = flt.get("value")

        column_name = index_column if column_key == "__index__" else column_key
        if column_name not in current.columns:
            raise ValueError(f"Column '{column_name}' not found in result set")

        series = current[column_name]

        if operator in {"eq", "ne", "lt", "lte", "gt", "gte"}:
            if is_numeric_dtype(series):
                coerced = _coerce_numeric(value, series)
                series_cmp = pd.to_numeric(series, errors="coerce")
            elif is_datetime64_any_dtype(series):
                coerced = _coerce_datetime(value)
                series_cmp = pd.to_datetime(series, errors="coerce")
            elif is_bool_dtype(series):
                coerced = _coerce_bool(value)
                series_cmp = series.astype(bool)
            else:
                coerced = str(value) if value is not None else ""
                series_cmp = series.astype(str)

            if coerced is None:
                raise ValueError(f"Unable to parse value '{value}' for column '{column_name}'")

            if operator == "eq":
                mask = series_cmp == coerced
            elif operator == "ne":
                mask = series_cmp != coerced
            elif operator == "lt":
                mask = series_cmp < coerced
            elif operator == "lte":
                mask = series_cmp <= coerced
            elif operator == "gt":
                mask = series_cmp > coerced
            else:
                mask = series_cmp >= coerced
        else:
            if value is None:
                raise ValueError(f"Filter value required for operator '{operator}'")
            value_str = str(value)
            series_str = series.astype(str)
            if operator == "contains":
                mask = series_str.str.contains(value_str, case=False, na=False)
            elif operator == "startswith":
                mask = series_str.str.startswith(value_str, na=False)
            else:
                mask = series_str.str.endswith(value_str, na=False)

        current = current[mask]
        if current.empty:
            break

    return current


def _coerce_numeric(value: Any, series):
    if value is None:
        return None
    try:
        import pandas as pd
        import numpy as np

        numeric_value = pd.to_numeric([value], errors="coerce")[0]
        if pd.isna(numeric_value):
            return None
        if pd.api.types.is_integer_dtype(series):
            return int(numeric_value)
        return float(numeric_value)
    except Exception:
        return None


def _coerce_datetime(value: Any):
    if value is None:
        return None
    try:
        import pandas as pd

        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return None
        return ts
    except Exception:
        return None


def _coerce_bool(value: Any):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return None


@router.delete("/delete_symbol")
async def delete_symbol(
    library: str = Query(..., description="Library name"),
    symbol: str = Query(..., description="Symbol name"),
) -> Dict[str, Any]:
    """Delete a symbol from the specified library."""
    try:
        ac = _get_ac()
        lib = ac.get_library(library)
        if not lib.has_symbol(symbol):
            raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found in '{library}'")
        lib.delete(symbol)
        return {"success": True, "message": f"Deleted '{symbol}' from '{library}'"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}
