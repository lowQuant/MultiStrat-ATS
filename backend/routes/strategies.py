"""
Strategies API routes
"""
from fastapi import APIRouter, HTTPException
from core.strategy_manager import StrategyManager

# Create router for strategies endpoints
router = APIRouter(prefix="/api/strategies", tags=["strategies"])

# This will be injected by main.py
strategy_manager: StrategyManager = None

def set_strategy_manager(sm: StrategyManager):
    """Set the strategy manager instance"""
    global strategy_manager
    strategy_manager = sm


@router.get("")
async def get_strategies(active_only: bool = False):
    """Get strategies and their status. For now, active_only is accepted but not used."""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    discovered = strategy_manager.discover_strategies()
    status = strategy_manager.get_strategy_status()
    
    return {
        "discovered_strategies": discovered,
        "strategy_status": status,
        "active_only": active_only
    }


@router.post("/{strategy_name}/start")
async def start_strategy(strategy_name: str):
    """Start a specific strategy"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    success = strategy_manager.start_strategy(strategy_name.upper())
    
    if success:
        return {"success": True, "message": f"Strategy {strategy_name} started successfully"}
    else:
        raise HTTPException(status_code=400, detail=f"Failed to start strategy {strategy_name}")


@router.post("/{strategy_name}/stop")
async def stop_strategy(strategy_name: str):
    """Stop a specific strategy"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    success = strategy_manager.stop_strategy(strategy_name.upper())
    
    if success:
        return {"success": True, "message": f"Strategy {strategy_name} stopped successfully"}
    else:
        raise HTTPException(status_code=400, detail=f"Failed to stop strategy {strategy_name}")


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
