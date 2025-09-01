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
        add_log(f"Error in /portfolio/positions endpoint: {e}", "API", "ERROR")
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
        add_log(f"Error in /portfolio/summary endpoint: {e}", "API", "ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve portfolio summary: {str(e)}")

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

# Function to set strategy manager reference (called by main.py)
def set_strategy_manager(sm):
    """Set the global strategy manager reference"""
    global strategy_manager
    strategy_manager = sm
    add_log("Portfolio routes configured with strategy manager", "API")
