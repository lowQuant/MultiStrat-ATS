"""
ArcticDB browsing routes
Provides endpoints to list libraries, list symbols in a library, and read table data
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any

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
) -> Dict[str, Any]:
    """Read a table and return a simple JSON structure with columns and rows.
    Supports basic pagination via offset/limit to avoid sending huge payloads.
    """
    try:
        ac = _get_ac()
        lib = ac.get_library(library)
        if not lib.has_symbol(symbol):
            raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found in '{library}'")
        df = lib.read(symbol).data
        if df is None:
            return {"success": True, "columns": [], "rows": []}
        df_reset = df.reset_index()
        # Slice for pagination
        paged = df_reset.iloc[offset: offset + limit]
        columns = [str(c) for c in paged.columns]
        rows = [list(map(_to_jsonable, row)) for row in paged.itertuples(index=False, name=None)]
        total = len(df_reset)
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
