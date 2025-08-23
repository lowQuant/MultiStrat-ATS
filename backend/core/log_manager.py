"""
Minimal logging system for IB Multi-Strategy ATS
Real-time log streaming via WebSocket
"""
import asyncio
import json
import logging
from typing import Set
from fastapi import WebSocket
from datetime import datetime


class LogManager:
    """Manages WebSocket connections for real-time log streaming"""
    
    def __init__(self):
        self.connections: Set[WebSocket] = set()
        self.last_message_hash = None  # Track last message to prevent duplicates
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.add(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.connections.discard(websocket)
    
    async def broadcast_log(self, level: str, message: str, component: str):
        """Broadcast log to all connected clients"""
        if not self.connections:
            return
            
        # Create message hash to prevent duplicates
        import hashlib
        message_content = f"{level}:{component}:{message}"
        message_hash = hashlib.md5(message_content.encode()).hexdigest()
        
        # Skip if this is a duplicate of the last message
        if message_hash == self.last_message_hash:
            return
            
        self.last_message_hash = message_hash
            
        data = {
            "type": "log",
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "component": component,
            "message": message
        }
        
        message_json = json.dumps(data)
        disconnected = set()
        
        for conn in self.connections:
            try:
                await conn.send_text(message_json)
            except:
                disconnected.add(conn)
        
        for conn in disconnected:
            self.disconnect(conn)
    
    async def broadcast_connection_status(self, status: dict):
        """Broadcast connection status to all clients"""
        data = {
            "type": "connection_status",
            "timestamp": datetime.now().isoformat(),
            **status
        }
        
        message_json = json.dumps(data)
        disconnected = set()
        
        for conn in self.connections:
            try:
                await conn.send_text(message_json)
            except:
                disconnected.add(conn)
        
        for conn in disconnected:
            self.disconnect(conn)


# Global instance
log_manager = LogManager()

# Module-level logger used by add_log; attach a console handler for Python console output
logger = logging.getLogger("core")
logger.setLevel(logging.INFO)
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    _console_handler = logging.StreamHandler()
    _console_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
    logger.addHandler(_console_handler)
    # Prevent double logging via root
    logger.propagate = False


def add_log(message: str, component: str = "CORE", level: str = "INFO"):
    """Add a log message with timestamp and broadcast to WebSocket clients"""
    # Try to broadcast over WS only if we're in a running event loop
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(log_manager.broadcast_log(level, message, component))
    except RuntimeError:
        # No running loop in this thread (e.g., strategy worker thread) -> skip WS broadcast
        pass
    
    # Log at appropriate level
    level = level.upper()
    console_msg = f"[{component}] {message}"
    if level == "ERROR":
        logger.error(console_msg)
    elif level == "WARNING":
        logger.warning(console_msg)
    elif level == "DEBUG":
        logger.debug(console_msg)
    else:
        logger.info(console_msg)
