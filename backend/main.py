"""
FastAPI main application for IB Multi-Strategy ATS
Minimal setup for testing IB connection with ib_async
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import argparse

from core.strategy_manager import StrategyManager
from core.arctic_manager import get_ac
from core.log_manager import log_manager, add_log
from routes.strategies import router as strategies_router, set_strategy_manager
from routes.connection import router as connection_router, set_strategy_manager as set_connection_strategy_manager
from routes.test import router as test_router, set_strategy_manager as set_test_strategy_manager
from routes.settings import router as settings_router, set_strategy_manager as set_settings_strategy_manager
from routes.portfolio import router as portfolio_router, set_strategy_manager as set_portfolio_strategy_manager

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
    
    # Initialize a single ArcticDB client and inject it
    ac = get_ac()
    strategy_manager = StrategyManager(arctic_client=ac)
    
    # Inject strategy manager into routes
    set_strategy_manager(strategy_manager)
    set_connection_strategy_manager(strategy_manager)
    set_test_strategy_manager(strategy_manager)
    set_settings_strategy_manager(strategy_manager)
    set_portfolio_strategy_manager(strategy_manager)
    
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
app.include_router(settings_router)
app.include_router(portfolio_router)


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
    parser = argparse.ArgumentParser(description="Run IB Multi-Strategy ATS API server")
    # Support both --reload and -reload as requested
    parser.add_argument("--reload", "-reload", action="store_true", help="Enable auto-reload (development mode)")
    args = parser.parse_args()

    if args.reload:
        # Development mode with auto-reload
        uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, log_level="info",loop="asyncio")
    else:
        # Use the same semantics as: uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
        config = uvicorn.Config(
            "main:app",
            host="127.0.0.1",
            port=8000,
            log_level="info",
            reload=False,
            workers=1,
        )
        server = uvicorn.Server(config)
        server.run()
