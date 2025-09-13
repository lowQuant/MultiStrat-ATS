"""
Strategies API routes
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import pandas as pd
import json

from core.strategy_manager import StrategyManager

# Create router for strategies endpoints
router = APIRouter(prefix="/api/strategies", tags=["strategies"])

# This will be injected by main.py
strategy_manager: StrategyManager = None

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
        # Build list
        saved_list = df_latest.to_dict(orient="records")

    # Running status
    status = strategy_manager.get_strategy_status()
    running_map = {k: bool(v) for k, v in (status.get("strategies", {}) or {}).items()}

    # Attach running to each saved item
    for item in saved_list:
        sym = str(item.get("strategy_symbol", "")).upper()
        item["running"] = running_map.get(sym, False)

    print({
        "strategies": saved_list,
        "discovered_strategies": discovered,
        "active_only": active_only,
    })
    return {
        "strategies": saved_list,
        "discovered_strategies": discovered,
        "active_only": active_only,
    }

@router.post("/save")
async def save_strategy_metadata(payload: StrategyMetadata):
    """Append strategy metadata row to ArcticDB 'general' library under symbol 'strategies'.
    Index is 'strategy_symbol'. If the symbol exists, a new row is appended (historical record).
    """
    try:
        ac = strategy_manager.ac if getattr(strategy_manager, 'ac', None) is not None else strategy_manager.get_arctic_client()
        lib = ac.get_library("general", create_if_missing=True)

        # Build one-row DataFrame with index strategy_symbol
        # Ensure Arctic-friendly types: params stored as JSON string
        params_json = json.dumps(payload.params or {})
        row = {
            "name": payload.name,
            "description": payload.description,
            "target_weight": payload.target_weight,
            "min_weight": payload.min_weight,
            "max_weight": payload.max_weight,
            "filename": payload.filename,
            "params": params_json,
            "color": payload.color,
            "active": payload.active,
        }
        df_new = pd.DataFrame([row])
        # Keep a symbol column to avoid mixed index schemas
        df_new.insert(0, "strategy_symbol", payload.strategy_symbol.upper())

        symbol = "strategies"
        if lib.has_symbol(symbol):
            existing = lib.read(symbol).data
            # Normalize: ensure strategy_symbol is a column on existing as well
            if existing.index.name == "strategy_symbol":
                existing = existing.reset_index()
            combined = pd.concat([existing, df_new], ignore_index=True, sort=False)
        else:
            # First write: use our defined index
            combined = df_new

        lib.write(symbol, combined)
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
