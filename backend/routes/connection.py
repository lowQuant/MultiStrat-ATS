"""
IB Connection API routes
"""
from fastapi import APIRouter, HTTPException
from core.strategy_manager import StrategyManager
from core.log_manager import log_manager

# Create router for connection endpoints
router = APIRouter(prefix="/api", tags=["connection"])

# This will be injected by main.py
strategy_manager: StrategyManager = None

def set_strategy_manager(sm: StrategyManager):
    """Set the strategy manager instance"""
    global strategy_manager
    strategy_manager = sm


@router.post("/ib-disconnect")
async def disconnect_ib():
    """Disconnect from IB"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    try:
        await strategy_manager.disconnect_all()
        
        # Broadcast disconnection status
        await log_manager.broadcast_connection_status({
            "connected": False,
            "message": "Manually disconnected"
        })
        
        return {"success": True, "message": "Disconnected from IB"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/ib-status")
async def get_ib_status():
    """Get current IB connection status for all clients"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    try:
        status = await strategy_manager.get_connection_status()
        
        # Broadcast connection status for master
        await log_manager.broadcast_connection_status({
            "connected": status["master_connection"]["connected"],
            "host": status["master_connection"]["host"],
            "port": status["master_connection"]["port"],
            "client_id": status["master_connection"]["client_id"]
        })
        
        return {"success": True, "connection_status": status}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/ib-disconnect-client/{client_id}")
async def disconnect_ib_client(client_id: int):
    """Disconnect a specific IB client by client_id"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    try:
        success = await strategy_manager.disconnect_client(client_id)
        if success:
            return {"success": True, "message": f"Client {client_id} disconnected"}
        else:
            return {"success": False, "message": f"Client {client_id} not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/ib-disconnect-all")
async def disconnect_all_ib():
    """Disconnect all IB connections (master + all strategies)"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    try:
        await strategy_manager.disconnect_all()
        
        # Broadcast disconnection status
        await log_manager.broadcast_connection_status({
            "connected": False,
            "message": "All connections disconnected"
        })
        
        return {"success": True, "message": "All IB connections disconnected"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/ib-connect")
async def connect_ib():
    """Manually connect to IB"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    try:
        success = await strategy_manager.connect_to_ib()
        
        if success:
            # Broadcast connection status
            await log_manager.broadcast_connection_status({
                "connected": True,
                "host": strategy_manager.host,
                "port": strategy_manager.port,
                "client_id": strategy_manager.clientId,
                "message": "Manually connected"
            })
            
            return {"success": True, "message": "Connected to IB successfully"}
        else:
            return {"success": False, "message": "Failed to connect to IB"}
    except Exception as e:
        return {"success": False, "error": str(e)}
