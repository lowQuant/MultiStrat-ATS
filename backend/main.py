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
from core.log_manager import log_manager, add_log
from routes.strategies import router as strategies_router, set_strategy_manager
from routes.connection import router as connection_router, set_strategy_manager as set_connection_strategy_manager
from routes.test import router as test_router, set_strategy_manager as set_test_strategy_manager

# Global strategy manager instance
strategy_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    global strategy_manager
    
    # Startup
    print("🚀 Starting IB Multi-Strategy ATS Backend...")
    
    # Setup log streaming for frontend
    # (Removed) setup_log_streaming() — add_log handles WS broadcasting directly
    
    strategy_manager = StrategyManager()
    
    # Inject strategy manager into routes
    set_strategy_manager(strategy_manager)
    set_connection_strategy_manager(strategy_manager)
    set_test_strategy_manager(strategy_manager)
    
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

# Include routers
app.include_router(strategies_router)
app.include_router(connection_router)
app.include_router(test_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "IB Multi-Strategy ATS API", "version": "1.0.0", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": "2024-01-01T00:00:00Z"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time logs"""
    await log_manager.connect(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        log_manager.disconnect(websocket)
    except Exception as e:
        log_manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info")
