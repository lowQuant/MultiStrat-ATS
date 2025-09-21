"""
Strategies API routes
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
import json
import os
import importlib.util

from core.strategy_manager import StrategyManager

# Create router for strategies endpoints
router = APIRouter(prefix="/api/strategies", tags=["strategies"])

# This will be injected by main.py
strategy_manager: StrategyManager = None

def _load_params_from_file(filename: str) -> Dict[str, Any]:
    """Dynamically load PARAMS from a strategy file."""
    if not filename:
        return {}
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(current_dir)
        strategy_path = os.path.join(backend_dir, "strategies", filename)
        module_name = filename[:-3]

        spec = importlib.util.spec_from_file_location(module_name, strategy_path)
        if not spec or not spec.loader:
            return {}
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        return getattr(module, 'PARAMS', {})
    except Exception:
        return {}

def set_strategy_manager(sm: StrategyManager):
    """Set the strategy manager instance"""
    global strategy_manager
    strategy_manager = sm

class StrategyMetadata(BaseModel):
    name: str
    strategy_symbol: str = Field(..., description="Canonical symbol identifier, e.g., SPY")
    description: Optional[str] = ""
    target_weight: Optional[float] = None
    min_weight: Optional[float] = None
    max_weight: Optional[float] = None
    filename: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    color: Optional[str] = None  # hex code
    active: bool = False

@router.get("")
async def get_strategies(active_only: bool = False):
    """Return only saved strategies (latest row per symbol) and their running status.
    Also include discovered strategy filenames for the create dialog.
    """
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")

    # Discover filenames to populate the create form dropdown
    discovered = strategy_manager.list_strategy_files()

    # Read saved strategies from ArcticDB via shared StrategyManager client
    ac = strategy_manager.ac if getattr(strategy_manager, 'ac', None) is not None else strategy_manager.get_arctic_client()
    lib = ac.get_library("general", create_if_missing=True)
    saved_list = []
    if lib.has_symbol("strategies"):
        df = lib.read("strategies").data
        if df.index.name == "strategy_symbol":
            df = df.reset_index()
        # Keep only latest per symbol in append order
        df_latest = df.drop_duplicates(subset=["strategy_symbol"], keep="last")
        # Optional filter
        if active_only:
            df_latest = df_latest[df_latest["active"] == True]
        
        # Replace NaN with None for JSON compatibility
        df_latest = df_latest.replace({np.nan: None})

        # Ensure params are present for UI: if empty/missing, use defaults from file.PARAMS
        try:
            for idx, row in df_latest.iterrows():
                pval = row.get('params') if isinstance(row, dict) else row['params'] if 'params' in row else None
                filename = (row.get('filename') if isinstance(row, dict) else row['filename']) if 'filename' in df_latest.columns else None
                needs_defaults = (pval is None) or (isinstance(pval, str) and (pval.strip() == '' or pval.strip() == '{}'))
                if needs_defaults and filename:
                    file_params = _load_params_from_file(filename) or {}
                    if isinstance(file_params, dict) and file_params:
                        df_latest.loc[idx, 'params'] = json.dumps(file_params)
                else:
                    # Normalize existing dict to JSON string for frontend consumption
                    if isinstance(pval, dict):
                        df_latest.loc[idx, 'params'] = json.dumps(pval)
        except Exception:
            # Non-fatal; if anything goes wrong we just return whatever exists
            pass

        # Build list (params already normalized to JSON string above if needed)
        saved_list = df_latest.to_dict(orient="records")

    # Running status
    status = strategy_manager.get_strategy_status()
    running_map = {k: bool(v) for k, v in (status.get("strategies", {}) or {}).items()}

    # Attach running to each saved item
    for item in saved_list:
        sym = str(item.get("strategy_symbol", "")).upper()
        item["running"] = running_map.get(sym, False)


    return {
        "strategies": saved_list,
        "discovered_strategies": discovered,
        "active_only": active_only,
    }

@router.get("/params-from-file")
async def get_params_from_file(filename: str):
    """Return PARAMS dict for a given strategy filename to prefill create dialog."""
    try:
        params = _load_params_from_file(filename) or {}
        # Ensure serializable
        return {"params": params}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load params from file '{filename}': {e}")

@router.post("/save")
async def save_strategy_metadata(payload: StrategyMetadata):
    """Create a new strategy or update an existing one.
    If a strategy with the same `strategy_symbol` exists, it's updated in-place.
    Otherwise, a new strategy record is created.
    """
    try:
        ac = strategy_manager.ac if getattr(strategy_manager, 'ac', None) is not None else strategy_manager.get_arctic_client()
        lib = ac.get_library("general", create_if_missing=True)

        # Params: if not provided by frontend, load defaults from file's PARAMS
        params_dict = dict(payload.params or {})
        if (not params_dict) and payload.filename:
            try:
                file_params = _load_params_from_file(payload.filename) or {}
                if isinstance(file_params, dict):
                    params_dict = file_params
            except Exception:
                params_dict = params_dict or {}

        # Streamline weights: always keep weights in params only
        # Backward-compat: if payload provided top-level weights, fold them into params
        for k in ("target_weight", "min_weight", "max_weight"):
            v = getattr(payload, k, None)
            if v is not None:
                params_dict[k] = v
        params_json = json.dumps(params_dict)
        row = {
            "name": payload.name,
            "description": payload.description,
            "filename": payload.filename,
            "params": params_json,
            "color": payload.color,
            "active": payload.active,
        }
        row_data = {**row, "strategy_symbol": payload.strategy_symbol.upper()}

        symbol = "strategies"
        if lib.has_symbol(symbol):
            existing_df = lib.read(symbol).data
            if existing_df.index.name == "strategy_symbol":
                existing_df = existing_df.reset_index()

            # Check if the strategy symbol already exists
            mask = existing_df['strategy_symbol'] == payload.strategy_symbol.upper()
            if mask.any():
                # Update the last matching row
                idx_to_update = existing_df[mask].index[-1]
                for key, value in row_data.items():
                    existing_df.loc[idx_to_update, key] = value
                updated_df = existing_df
            else:
                # Append as a new row
                new_row_df = pd.DataFrame([row_data])
                updated_df = pd.concat([existing_df, new_row_df], ignore_index=True)
        else:
            # Table doesn't exist, create it with the first entry
            updated_df = pd.DataFrame([row_data])

        lib.write(symbol, updated_df)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save strategy metadata: {e}")

@router.post("/{strategy_symbol}/activate")
async def activate_strategy(strategy_symbol: str):
    """Activate a saved strategy by updating its 'active' flag to True."""
    try:
        ac = strategy_manager.ac if getattr(strategy_manager, 'ac', None) is not None else strategy_manager.get_arctic_client()
        lib = ac.get_library("general", create_if_missing=True)
        symbol = "strategies"
        if not lib.has_symbol(symbol):
            raise HTTPException(status_code=404, detail="No strategies found")
        df = lib.read(symbol).data
        if df.index.name == "strategy_symbol":
            df = df.reset_index()
        sym = strategy_symbol.upper()
        mask = df["strategy_symbol"].str.upper() == sym
        if not mask.any():
            raise HTTPException(status_code=404, detail=f"Strategy {sym} not found")
        df.loc[mask, "active"] = True
        lib.write(symbol, df.reset_index(drop=True))
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to activate strategy: {e}")

@router.post("/{strategy_symbol}/deactivate")
async def deactivate_strategy(strategy_symbol: str):
    """Deactivate a saved strategy by updating its 'active' flag to False."""
    try:
        ac = strategy_manager.ac if getattr(strategy_manager, 'ac', None) is not None else strategy_manager.get_arctic_client()
        lib = ac.get_library("general", create_if_missing=True)
        symbol = "strategies"
        if not lib.has_symbol(symbol):
            raise HTTPException(status_code=404, detail="No strategies found")
        df = lib.read(symbol).data
        if df.index.name == "strategy_symbol":
            df = df.reset_index()
        sym = strategy_symbol.upper()
        mask = df["strategy_symbol"].str.upper() == sym
        if not mask.any():
            raise HTTPException(status_code=404, detail=f"Strategy {sym} not found")
        df.loc[mask, "active"] = False
        df.reset_index(drop=True, inplace=True)
        lib.write(symbol, df)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deactivate strategy: {e}")

@router.post("/{strategy_symbol}/delete")
async def delete_strategy(strategy_symbol: str):
    """Delete a saved strategy by removing its row from the 'strategies' library."""
    try:
        ac = strategy_manager.ac if getattr(strategy_manager, 'ac', None) is not None else strategy_manager.get_arctic_client()
        lib = ac.get_library("general", create_if_missing=True)
        symbol = "strategies"
        if not lib.has_symbol(symbol):
            raise HTTPException(status_code=404, detail="No strategies found")
        df = lib.read(symbol).data
        if df.index.name == "strategy_symbol":
            df = df.reset_index()
        sym = strategy_symbol.upper()
        mask = df["strategy_symbol"].str.upper() == sym
        if not mask.any():
            raise HTTPException(status_code=404, detail=f"Strategy {sym} not found")
        df = df[~mask].reset_index(drop=True)
        lib.write(symbol, df)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete strategy: {e}")

@router.post("/{strategy_symbol}/start")
async def start_strategy(strategy_symbol: str):
    """Start a specific strategy"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    success = strategy_manager.start_strategy(strategy_symbol)
    
    if success:
        return {"success": True, "message": f"Strategy {strategy_symbol} started successfully"}
    else:
        raise HTTPException(status_code=400, detail=f"Failed to start strategy {strategy_symbol}")


@router.post("/{strategy_symbol}/stop")
async def stop_strategy(strategy_symbol: str):
    """Stop a specific strategy"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    success = strategy_manager.stop_strategy(strategy_symbol)
    
    if success:
        return {"success": True, "message": f"Strategy {strategy_symbol} stopped successfully"}
    else:
        raise HTTPException(status_code=400, detail=f"Failed to stop strategy {strategy_symbol}")


@router.post("/start-all")
async def start_all_strategies():
    """Start all discovered strategies"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    results = strategy_manager.start_all_strategies()
    
    return {
        "success": True,
        "results": results,
        "message": f"Started {sum(results.values())} out of {len(results)} strategies"
    }


@router.post("/stop-all")
async def stop_all_strategies():
    """Stop all running strategies"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    strategy_manager.stop_all_strategies()
    
    return {"success": True, "message": "All strategies stopped"}
