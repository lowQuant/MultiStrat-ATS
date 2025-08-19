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


class WebSocketHandler(logging.Handler):
    """Streams logs to WebSocket clients"""
    
    def emit(self, record):
        try:
            message = self.format(record)
            component = record.name.split('.')[-1].upper()
            if component == "ROOT":
                component = "SYSTEM"
            
            asyncio.create_task(
                log_manager.broadcast_log(record.levelname, message, component)
            )
        except:
            pass


def setup_log_streaming():
    """Setup WebSocket log streaming - only for explicit add_log calls"""
    handler = WebSocketHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    
    # Only add handler to specific loggers we want to stream
    # NOT to root logger (which captures everything)
    explicit_loggers = [
        "strategy",      # For strategy.* loggers (from add_log)
        "core",          # For core system logs (from add_log)
        "ats"            # For ATS-specific logs
    ]
    
    for logger_name in explicit_loggers:
        logger = logging.getLogger(logger_name)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        # Prevent propagation to root logger
        logger.propagate = False


def add_log(message: str, component: str = None, level: str = "INFO"):
    """Simple logging function - compatible with old add_log"""
    if not component:
        import inspect
        frame = inspect.currentframe().f_back
        if frame and 'self' in frame.f_locals:
            obj = frame.f_locals['self']
            if hasattr(obj, 'strategy_symbol'):
                component = obj.strategy_symbol
            elif hasattr(obj, '__class__'):
                component = obj.__class__.__name__
        
        if not component:
            component = "SYSTEM"
    
    logger = logging.getLogger(f"strategy.{component}" if component not in ["SYSTEM", "StrategyManager"] else "core")
    
    # Log at appropriate level
    level = level.upper()
    if level == "ERROR":
        logger.error(message)
    elif level == "WARNING":
        logger.warning(message)
    elif level == "DEBUG":
        logger.debug(message)
    else:
        logger.info(message)
