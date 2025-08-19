"""
FastAPI main application for IB Multi-Strategy ATS
Minimal setup for testing IB connection with ib_async
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging

from core.strategy_manager import StrategyManager
from core.log_manager import setup_log_streaming, log_manager, add_log

# Global strategy manager instance
strategy_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    global strategy_manager
    
    # Startup
    print("🚀 Starting IB Multi-Strategy ATS Backend...")
    
    # Setup log streaming for frontend
    setup_log_streaming()
    
    strategy_manager = StrategyManager()
    
    yield
    
    # Shutdown
    print("🛑 Shutting down IB Multi-Strategy ATS Backend...")
    if strategy_manager:
        await strategy_manager.cleanup()


# Create FastAPI app
app = FastAPI(
    title="IB Multi-Strategy ATS API",
    description="FastAPI backend for Interactive Brokers Multi-Strategy Automated Trading System",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "IB Multi-Strategy ATS API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": "2024-01-01T00:00:00Z"}


@app.post("/api/test-logs")
async def test_logs():
    """Generate test logs for frontend testing"""
    add_log("This is an error message", "TESTCOMPONENT", "ERROR")
    add_log("This is an info message", "TESTCOMPONENT", "INFO")
    add_log("This is a warning message", "TESTCOMPONENT", "WARNING")
    add_log("Strategy-specific log message", "AAPL", "INFO")
    add_log("StrategyManager system log", "StrategyManager", "INFO")
    
    return {"message": "Test logs generated successfully"}


@app.get("/api/strategies")
async def get_strategies():
    """Get all available strategies and their status"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    discovered = strategy_manager.discover_strategies()
    status = strategy_manager.get_strategy_status()
    
    return {
        "discovered_strategies": discovered,
        "strategy_status": status
    }


@app.post("/api/strategies/{strategy_name}/start")
async def start_strategy(strategy_name: str):
    """Start a specific strategy"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    success = strategy_manager.start_strategy(strategy_name.upper())
    
    if success:
        return {"success": True, "message": f"Strategy {strategy_name} started successfully"}
    else:
        raise HTTPException(status_code=400, detail=f"Failed to start strategy {strategy_name}")


@app.post("/api/strategies/{strategy_name}/stop")
async def stop_strategy(strategy_name: str):
    """Stop a specific strategy"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    success = strategy_manager.stop_strategy(strategy_name.upper())
    
    if success:
        return {"success": True, "message": f"Strategy {strategy_name} stopped successfully"}
    else:
        raise HTTPException(status_code=400, detail=f"Failed to stop strategy {strategy_name}")


@app.post("/api/strategies/start-all")
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


@app.post("/api/strategies/stop-all")
async def stop_all_strategies():
    """Stop all running strategies"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    strategy_manager.stop_all_strategies()
    
    return {"success": True, "message": "All strategies stopped"}


@app.post("/api/ib-disconnect")
async def disconnect_ib():
    """Disconnect from IB"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    try:
        # add_log("Disconnecting from IB...", "StrategyManager")  # Removed - utility handles logging
        await strategy_manager.disconnect()
        
        # Broadcast disconnection status
        await log_manager.broadcast_connection_status({
            "connected": False,
            "message": "Manually disconnected"
        })
        
        return {"success": True, "message": "Disconnected from IB"}
    except Exception as e:
        # add_log(f"Failed to disconnect from IB: {str(e)}", "StrategyManager", "ERROR")  # Removed - utility handles logging
        return {"success": False, "error": str(e)}


@app.get("/api/ib-test")
async def test_ib_connection():
    """Test IB connection - critical for Phase 1"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    # Check if already connected
    if strategy_manager.is_connected:
        # add_log("IB already connected", "StrategyManager")  # Removed - keep main.py clean
        result = {
            "status": "connected",
            "host": strategy_manager.host,
            "port": strategy_manager.port,
            "client_id": strategy_manager.clientId,
            "connection_type": "master"
        }
        
        await log_manager.broadcast_connection_status({
            "connected": True,
            "host": result["host"],
            "port": result["port"],
            "client_id": result["client_id"]
        })
        
        return {"success": True, "connection_details": result}
    
    try:
        # add_log("Testing IB connection...", "StrategyManager")  # Removed - utility handles logging
        result = await strategy_manager.test_connection()
        # add_log("IB connection successful", "StrategyManager")  # Removed - utility handles logging
        
        # Broadcast connection status
        await log_manager.broadcast_connection_status({
            "connected": True,
            "host": result["host"],
            "port": result["port"],
            "client_id": result["client_id"]
        })
        
        return {"success": True, "connection_details": result}
    except Exception as e:
        # add_log(f"IB connection failed: {str(e)}", "StrategyManager", "ERROR")  # Removed - utility handles logging
        
        # Broadcast disconnection status
        await log_manager.broadcast_connection_status({
            "connected": False,
            "error": str(e)
        })
        
        raise HTTPException(status_code=500, detail=f"IB connection failed: {str(e)}")


@app.get("/api/status")
async def get_system_status():
    """Get current system and IB connection status"""
    if strategy_manager and strategy_manager.is_connected:
        status = {
            "system": "operational",
            "ib_connection": {
                "connected": True,
                "host": strategy_manager.host,
                "port": strategy_manager.port,
                "client_id": strategy_manager.clientId
            }
        }
    else:
        status = {
            "system": "degraded",
            "ib_connection": {
                "connected": False,
                "message": "IB Workstation/Gateway not connected"
            }
        }
    
    return status


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time logs"""
    await log_manager.connect(websocket)
    # add_log("Frontend connected to log stream")  # Removed - causes duplicate logs with multiple connections
    
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            # Echo back for now
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        log_manager.disconnect(websocket)
        # add_log("Frontend disconnected from log stream")  # Removed - keep main.py clean
    except Exception as e:
        # add_log(f"WebSocket error: {e}", level="ERROR")  # Removed - keep main.py clean
        log_manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
