"""
Portfolio routes for IB Multi-Strategy ATS
Provides REST API endpoints for portfolio data and management
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
import pandas as pd
from core.log_manager import add_log

# Global reference to strategy manager (will be set by main.py)
strategy_manager = None

def get_strategy_manager():
    """Dependency to get strategy manager instance"""
    if strategy_manager is None:
        raise HTTPException(status_code=503, detail="Strategy manager not initialized")
    return strategy_manager

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

@router.get("/positions")
async def get_positions(sm = Depends(get_strategy_manager)):
    """
    Get current portfolio positions formatted for frontend display.
    
    Returns:
        dict: Portfolio positions with metadata
    """
    try:
        if not sm.portfolio_manager:
            raise HTTPException(status_code=503, detail="Portfolio manager not available")
        
        # Get positions from IB formatted for frontend
        positions_df = await sm.portfolio_manager.get_ib_positions_for_frontend()
        
        if positions_df.empty:
            return {
                "success": True,
                "message": "No positions found",
                "data": {
                    "positions": [],
                    "total_positions": 0,
                    "total_equity": 0.0,
                    "base_currency": sm.portfolio_manager.base_currency
                }
            }
        
        # Convert DataFrame to list of dictionaries for JSON response
        positions_list = []
        for _, row in positions_df.iterrows():
            position = {}
            for col in positions_df.columns:
                value = row[col]
                # Handle pandas/numpy types for JSON serialization
                if pd.isna(value):
                    position[col] = None
                elif isinstance(value, (pd.Timestamp,)):
                    position[col] = value.isoformat()
                else:
                    position[col] = value
            positions_list.append(position)
        
        return {
            "success": True,
            "message": f"Retrieved {len(positions_list)} positions",
            "data": {
                "positions": positions_list,
                "total_positions": len(positions_list),
                "total_equity": sm.portfolio_manager.total_equity,
                "base_currency": sm.portfolio_manager.base_currency
            }
        }
        
    except Exception as e:
        print(f"Error in /portfolio/positions endpoint: {e}", "API", "ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve positions: {str(e)}")

@router.get("/summary")
async def get_portfolio_summary(sm = Depends(get_strategy_manager)):
    """
    Get overall portfolio summary with P&L and statistics.
    
    Returns:
        dict: Portfolio summary data
    """
    try:
        if not sm.portfolio_manager:
            raise HTTPException(status_code=503, detail="Portfolio manager not available")
        
        # Get portfolio summary from PortfolioManager
        summary = await sm.portfolio_manager.get_portfolio_summary()
        
        return {
            "success": True,
            "message": "Portfolio summary retrieved",
            "data": summary
        }
        
    except Exception as e:
        print(f"Error in /portfolio/summary endpoint: {e}", "API", "ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve portfolio summary: {str(e)}")

@router.get("/pnl")
async def get_total_pnl(sm = Depends(get_strategy_manager)):
    """
    Get total portfolio P&L.
    """
    try:
        if not sm.portfolio_manager:
            raise HTTPException(status_code=503, detail="Portfolio manager not available")
            
        # Read account_summary from ArcticDB
        library = sm.portfolio_manager.account_library
        base_currency = sm.portfolio_manager.base_currency
        
        if not library or 'account_summary' not in library.list_symbols():
             return {"success": True, "data": {"total_pnl": 0.0, "currency": base_currency}}
             
        # Read data
        df = library.read("account_summary").data
        
        if df.empty:
             return {"success": True, "data": {"total_pnl": 0.0, "currency": base_currency}}
             
        df.sort_index(inplace=True)
        
        # Initial Equity (first record)
        initial_equity = float(df['equity'].iloc[0])
        
        # Current Equity (from PortfolioManager if available, else last record)
        current_equity = getattr(sm.portfolio_manager, 'total_equity', 0.0)
        if current_equity == 0.0:
             current_equity = float(df['equity'].iloc[-1])
        total_pnl = current_equity - initial_equity
        
        return {
            "success": True,
            "message": "Total P&L retrieved",
            "data": {
                "total_pnl": total_pnl,
                "currency": base_currency
            }
        }
    except Exception as e:
        print(f"Error in /portfolio/pnl endpoint: {e}", "API", "ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve total P&L: {str(e)}")

@router.get("/strategy/{strategy_name}")
async def get_strategy_positions(strategy_name: str, sm = Depends(get_strategy_manager)):
    """
    Get positions for a specific strategy.
    
    Args:
        strategy_name: Name of the strategy
        
    Returns:
        dict: Strategy-specific position data
    """
    try:
        if not sm.portfolio_manager:
            raise HTTPException(status_code=503, detail="Portfolio manager not available")
        
        # Get strategy summary
        summary = await sm.portfolio_manager.get_strategy_summary(strategy_name)
        
        return {
            "success": True,
            "message": f"Strategy {strategy_name} positions retrieved",
            "data": summary
        }
        
    except Exception as e:
        add_log(f"Error in /portfolio/strategy/{strategy_name} endpoint: {e}", "API", "ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve strategy positions: {str(e)}")

@router.get("/consolidated")
async def get_consolidated_positions(sm = Depends(get_strategy_manager)):
    """
    Get consolidated positions across all strategies with attribution.
    
    Returns:
        dict: Consolidated position data with per-strategy breakdown
    """
    try:
        if not sm.portfolio_manager:
            raise HTTPException(status_code=503, detail="Portfolio manager not available")
        
        # Get consolidated positions
        positions = await sm.portfolio_manager.get_consolidated_positions()
        
        return {
            "success": True,
            "message": f"Retrieved {len(positions)} consolidated positions",
            "data": {
                "positions": positions,
                "total_positions": len(positions),
                "base_currency": sm.portfolio_manager.base_currency
            }
        }
        
    except Exception as e:
        add_log(f"Error in /portfolio/consolidated endpoint: {e}", "API", "ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve consolidated positions: {str(e)}")

@router.get("/fx-rates")
async def get_fx_rates(sm = Depends(get_strategy_manager)):
    """
    Get current FX rates cache status and rates.
    
    Returns:
        dict: FX cache information
    """
    try:
        if not sm.portfolio_manager or not sm.portfolio_manager.fx_cache:
            raise HTTPException(status_code=503, detail="FX cache not available")
        
        cache_status = sm.portfolio_manager.fx_cache.get_cache_status()
        
        return {
            "success": True,
            "message": "FX rates retrieved",
            "data": cache_status
        }
        
    except Exception as e:
        add_log(f"Error in /portfolio/fx-rates endpoint: {e}", "API", "ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve FX rates: {str(e)}")

@router.post("/refresh-positions")
async def refresh_positions(sm = Depends(get_strategy_manager)):
    """
    Refresh portfolio positions from IB and clear caches.
    
    Returns:
        dict: Refresh status
    """
    try:
        if not sm.portfolio_manager:
            raise HTTPException(status_code=503, detail="Portfolio manager not available")
        
        # Clear position cache
        sm.portfolio_manager.clear_cache()
        
        # Clear FX cache only if stale (>30 minutes)
        if sm.portfolio_manager.fx_cache:
            sm.portfolio_manager.fx_cache.clear_cache_if_stale(30)
        
        # Get fresh positions
        positions_df = await sm.portfolio_manager.get_ib_positions_for_frontend()
        
        return {
            "success": True,
            "message": f"Positions refreshed, found {len(positions_df)} positions",
            "data": {
                "total_positions": len(positions_df),
                "total_equity": sm.portfolio_manager.total_equity
            }
        }
        
    except Exception as e:
        add_log(f"Error in /portfolio/refresh-positions endpoint: {e}", "API", "ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to refresh positions: {str(e)}")

@router.delete("/position")
async def delete_position(
    symbol: str, 
    asset_class: str, 
    strategy: str = 'Discretionary',
    sm = Depends(get_strategy_manager)
):
    """
    Delete a specific position from the portfolio table.
    
    Args:
        symbol: Ticker symbol (e.g. AAPL)
        asset_class: Asset class (e.g. STK)
        strategy: Strategy name (default: Discretionary)
    """
    try:
        if not sm.portfolio_manager:
            raise HTTPException(status_code=503, detail="Portfolio manager not available")
        
        # Normalize strategy name
        strategy = strategy or 'Discretionary'
        
        library = sm.portfolio_manager.account_library
        if not library or 'portfolio' not in library.list_symbols():
            raise HTTPException(status_code=404, detail="Portfolio not found")
            
        # Read current portfolio
        df = library.read('portfolio').data
        
        # Find row to delete
        # Normalize empty strategy in DF for comparison
        if 'strategy' in df.columns:
            df['strategy'] = df['strategy'].fillna('Discretionary').replace('', 'Discretionary')
        else:
            df['strategy'] = 'Discretionary'
            
        mask = (
            (df['symbol'] == symbol) & 
            (df['asset_class'] == asset_class) & 
            (df['strategy'] == strategy)
        )
        
        if not mask.any():
            return {
                "success": False,
                "message": f"Position not found: {symbol} {asset_class} ({strategy})"
            }
            
        # Remove the row
        df_new = df[~mask].copy()
        
        # Write back
        # Note: We overwrite the whole table to ensure deletion persists
        # We must keep the index/schema consistent
        library.write('portfolio', df_new, prune_previous_versions=True)
        
        # Clear caches so next fetch is fresh
        sm.portfolio_manager.clear_cache()
        
        return {
            "success": True,
            "message": f"Deleted position: {symbol} {asset_class} ({strategy})",
            "data": {
                "remaining_positions": len(df_new)
            }
        }
        
    except Exception as e:
        add_log(f"Error in delete_position endpoint: {e}", "API", "ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to delete position: {str(e)}")

# Function to set strategy manager reference (called by main.py)
def set_strategy_manager(sm):
    """Set the global strategy manager reference"""
    global strategy_manager
    strategy_manager = sm
    add_log("Portfolio routes configured with strategy manager", "API")
