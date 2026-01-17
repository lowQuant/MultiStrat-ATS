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
from datetime import datetime, timezone

from core.strategy_manager import StrategyManager
from utils.strategy_table_helpers import initialize_strategy_cash, get_strategy_equity_history, get_strategy_positions

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


class PortfolioAssignmentRequest(BaseModel):
    symbol: str = Field(..., description="Instrument symbol to reassign, e.g., AAPL")
    asset_class: str = Field(..., description="Asset class/security type as stored in portfolio, e.g., STK")
    target_strategy: str = Field(..., description="Strategy identifier the position should be assigned to")
    current_strategy: Optional[str] = Field(None, description="Existing strategy assignment, if any")

@router.get("/{strategy_symbol}/details")
async def get_strategy_details(strategy_symbol: str):
    """Get full details for a specific strategy including metadata, positions, and performance history."""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")

    # 1. Get Metadata
    ac = strategy_manager.ac if getattr(strategy_manager, 'ac', None) is not None else strategy_manager.get_arctic_client()
    lib = ac.get_library("general", create_if_missing=True)
    
    metadata = {}
    if lib.has_symbol("strategies"):
        df = lib.read("strategies").data
        if df.index.name == "strategy_symbol":
            df = df.reset_index()
        
        mask = df["strategy_symbol"].str.upper() == strategy_symbol.upper()
        if mask.any():
            row = df[mask].iloc[-1]
            # Convert params JSON string to dict
            params_val = row.get('params')
            if isinstance(params_val, str) and params_val.strip():
                try:
                    params = json.loads(params_val)
                except:
                    params = {}
            elif isinstance(params_val, dict):
                params = params_val
            else:
                params = {}
            
            metadata = {
                "name": row.get("name"),
                "strategy_symbol": row.get("strategy_symbol"),
                "description": row.get("description"),
                "filename": row.get("filename"),
                "color": row.get("color"),
                "active": bool(row.get("active")),
                "params": params
            }
    
    if not metadata:
         raise HTTPException(status_code=404, detail=f"Strategy {strategy_symbol} not found")

    # Check if running
    status = strategy_manager.get_strategy_status()
    running_map = {k: bool(v) for k, v in (status.get("strategies", {}) or {}).items()}
    metadata["running"] = running_map.get(strategy_symbol.upper(), False)

    # 2. Get Current Positions
    pm = strategy_manager.portfolio_manager
    positions_df = await get_strategy_positions(pm, strategy_symbol.upper(), current_only=True)
    
    positions = []
    total_equity = 0.0
    cash_balance = 0.0
    
    if positions_df is not None and not positions_df.empty:
        # Calculate equity and format positions
        for idx, row in positions_df.iterrows():
            qty = float(row['quantity'])
            if qty == 0: continue
            
            asset_class = row['asset_class']
            symbol = row['symbol']
            
            pos_dict = {
                "symbol": symbol,
                "asset_class": asset_class,
                "quantity": qty,
                "avg_cost": float(row['avg_cost']),
                "currency": row['currency'],
                "market_value": 0.0, # To be filled if we have price
                "pnl": 0.0
            }
            
            if asset_class == 'CASH':
                cash_balance += qty
                pos_dict['market_value'] = qty
                total_equity += qty
            else:
                # Try to get current market price from PortfolioManager cache or last trade
                # For now, use avg_cost as approximation if no live price
                # TODO: Integrate live price if available in PM
                val = qty * float(row['avg_cost'])
                pos_dict['market_value'] = val
                total_equity += val
            
            positions.append(pos_dict)

    # 3. Get Performance History (Equity Curve)
    equity_history = []
    try:
        hist_df = await get_strategy_equity_history(pm, strategy_symbol.upper(), days_lookback=90)
        if not hist_df.empty:
            # Sort by timestamp
            hist_df = hist_df.sort_index()
            # Downsample if too many points (optional)
            
            for ts, row in hist_df.iterrows():
                equity_history.append({
                    "timestamp": ts.isoformat(),
                    "equity": float(row['equity']),
                    "realized_pnl": float(row['realized_pnl'])
                })
    except Exception as e:
        print(f"Error fetching equity history: {e}")

    return {
        "metadata": metadata,
        "positions": positions,
        "stats": {
            "total_equity": total_equity,
            "cash_balance": cash_balance,
            "position_count": len([p for p in positions if p['asset_class'] != 'CASH'])
        },
        "performance": equity_history
    }

@router.post("/{strategy_symbol}/signals")
async def get_strategy_signals(strategy_symbol: str):
    """
    Trigger signal generation for a strategy.
    If the strategy is running, it triggers the scan logic.
    """
    sym = strategy_symbol.upper()
    if sym not in strategy_manager.active_strategies:
        raise HTTPException(status_code=400, detail="Strategy must be active/running to generate signals")
    
    strat_instance = strategy_manager.active_strategies[sym]
    
    # Check for known methods
    if hasattr(strat_instance, "scan_and_place_orders"):
        # This is async
        try:
            await strat_instance.scan_and_place_orders()
            return {"success": True, "message": "Signal generation and order placement triggered"}
        except Exception as e:
             raise HTTPException(status_code=500, detail=f"Error generating signals: {e}")
    elif hasattr(strat_instance, "run_strategy"):
         # Warning: run_strategy might be an infinite loop
         return {"success": False, "message": "Strategy does not support one-off signal generation"}
    else:
         return {"success": False, "message": "Strategy does not support signal generation"}

@router.post("/{strategy_symbol}/rebalance")
async def rebalance_strategy(strategy_symbol: str):
    """
    Trigger rebalancing for a strategy.
    """
    sym = strategy_symbol.upper()
    # Placeholder logic
    return {"success": True, "message": f"Rebalance triggered for {sym} (Not implemented)"}

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
        is_new_strategy = False
        
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
                is_new_strategy = False
            else:
                # Append as a new row
                new_row_df = pd.DataFrame([row_data])
                updated_df = pd.concat([existing_df, new_row_df], ignore_index=True)
                is_new_strategy = True
        else:
            # Table doesn't exist, create it with the first entry
            updated_df = pd.DataFrame([row_data])
            is_new_strategy = True

        lib.write(symbol, updated_df)
        
        if is_new_strategy:
            try:
                # Get strategy parameters
                strategy_params = json.loads(params_json) if params_json else {}
                # Handle case where target_weight is explicitly null/None in JSON
                target_weight_val = strategy_params.get('target_weight')
                target_weight = float(target_weight_val) if target_weight_val is not None else 0.0
                strategy_currency = strategy_params.get('currency', 'USD')
                
                # Calculate initial cash from target_weight * total_equity
                if strategy_manager and strategy_manager.portfolio_manager:
                    pm = strategy_manager.portfolio_manager
                    
                    # Get total account equity and cash in base currency
                    total_equity_base = 0.0
                    total_cash_base = 0.0

                    if pm.ib and pm.ib.isConnected():
                        account_summary = await pm.ib.accountSummaryAsync()
                        total_equity_base = sum(
                            float(entry.value) for entry in account_summary 
                            if entry.tag == "EquityWithLoanValue"
                        )
                        total_cash_base = sum(
                            float(entry.value) for entry in account_summary 
                            if entry.tag == "TotalCashValue"
                        )
                    else:
                        # Fallback: use cached value or 0
                        total_equity_base = getattr(pm, 'total_equity', 0.0)
                        # Assuming cash is 0 if not connected and not cached easily (could add cash cache later)
                    
                    # Calculate allocation in base currency
                    initial_cash_base = 0.0
                    if target_weight > 0:
                        initial_cash_base = total_equity_base * target_weight
                    else:
                        # Fallback: use available cash if no weight specified
                        print(f"[STRATEGY] No target weight set for {payload.strategy_symbol}, using available cash as fallback")
                        initial_cash_base = total_cash_base
                    
                    # Convert to strategy currency if different
                    if strategy_currency != pm.base_currency:
                        if pm.fx_cache:
                            fx_rate = await pm.fx_cache.get_fx_rate(strategy_currency,pm.base_currency)
                            initial_cash = initial_cash_base * fx_rate
                            print(f"[STRATEGY] Converted {pm.base_currency} {initial_cash_base:,.2f} to {strategy_currency} {initial_cash:,.2f} (rate={fx_rate:.4f})")
                        else:
                            # FX cache not initialized - skip currency conversion
                            print(f"[STRATEGY] Warning: FX cache not available, using base currency amount for {payload.strategy_symbol}")
                            initial_cash = initial_cash_base
                    else:
                        initial_cash = initial_cash_base
                    
                    # Initialize CASH position
                    if initial_cash > 0:
                        await initialize_strategy_cash(
                            portfolio_manager=pm,
                            strategy_symbol=payload.strategy_symbol.upper(),
                            initial_cash=initial_cash,
                            currency=strategy_currency
                        )
            except Exception as cash_error:
                # Log but don't fail the entire save operation
                print(f"[STRATEGY] Warning: Failed to initialize CASH for {payload.strategy_symbol}: {cash_error}")
        
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

        # Delete strategy library
        account_lib = strategy_manager.portfolio_manager.account_id
        ac.get_library(account_lib).delete(f"strategy_{sym}")

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


@router.post("/assign-portfolio")
async def assign_portfolio_strategy(payload: PortfolioAssignmentRequest):
    """Reassign a portfolio position to a different strategy."""
    lib = strategy_manager.portfolio_manager.account_library
    df = lib.read("portfolio").data
    
    # Find position row
    mask = (df["symbol"] == payload.symbol) & (df["asset_class"] == payload.asset_class)
    if not mask.any(): raise HTTPException(404, "Position not found")
    
    # Handle ambiguous matches (e.g. multiple lots) - simple first match logic for brevity
    idx = df[mask].index[0]
    row = df.loc[idx]
    old_strat, target_strat = row['strategy'], payload.target_strategy
    
    # Guard: If strategy unchanged, exit early
    if old_strat == target_strat: return {"success": True}

    # 1. Update Portfolio
    df.loc[idx, "strategy"] = target_strat
    lib.write("portfolio", df, prune_previous_versions=True)

    # 2. Update Strategy Tables
    cost = float(row['position']) * float(row['averageCost'])
    ts = datetime.now(timezone.utc)
    
    for strat, amount, add_pos in [(target_strat, -cost, True), (old_strat, cost, False)]:
        if not strat or strat in ["", "Discretionary", "Unassigned"] or pd.isna(strat): continue
        
        tbl = f"strategy_{strat}"
        # Get current cash
        cash = 0.0
        if lib.has_symbol(tbl):
            sdf = lib.read(tbl).data
            c_rows = sdf[sdf['asset_class'] == 'CASH']
            if not c_rows.empty: cash = float(c_rows.iloc[-1]['quantity'])
            
        # Create rows
        new_rows = [{
            'strategy': strat, 'symbol': row['currency'], 'asset_class': 'CASH', 'exchange': '',
            'currency': row['currency'], 'quantity': cash + amount, 'avg_cost': 1.0, 'realized_pnl': 0.0, 'timestamp': ts
        }]
        if add_pos:
            new_rows.append({
                'strategy': strat, 'symbol': row['symbol'], 'asset_class': row['asset_class'],
                'exchange': row.get('exchange',''), 'currency': row['currency'], 'quantity': float(row['position']),
                'avg_cost': float(row['averageCost']), 'realized_pnl': 0.0, 'timestamp': ts
            })

        # Write/Append
        update = pd.DataFrame(new_rows).set_index('timestamp')
        # Ensure cols
        for c in ['strategy','symbol','asset_class','exchange','currency','quantity','avg_cost','realized_pnl']:
            if c not in update: update[c] = "" if c == 'exchange' else 0.0
        
        if lib.has_symbol(tbl): lib.append(tbl, update[update.columns], prune_previous_versions=True)
        else: lib.write(tbl, update[update.columns], prune_previous_versions=True)

    strategy_manager.portfolio_manager.clear_cache()
    return {"success": True}
