"""
Base Strategy class for IB Multi-Strategy ATS
Modernized version based on the old strategy template
"""
import asyncio
import threading
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ib_async import Stock, Contract, Trade
from core.log_manager import add_log
from utils.ib_connection import connect_to_ib, disconnect_from_ib


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    Each strategy runs in its own thread with a unique clientId and isolated event loop.
    Strategies must implement the abstract methods to define their trading logic.
    """
    
    def __init__(self, client_id: int, strategy_name: str, symbol: str, strategy_manager=None):
        """
        Initialize the base strategy.
        
        Args:
            client_id: Unique IB client ID for this strategy
            strategy_name: Human-readable name for the strategy
            symbol: Primary trading symbol for this strategy
            strategy_manager: Reference to the main StrategyManager
        """
        self.client_id = client_id
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.strategy_manager = strategy_manager
        
        # Connection and state
        self.ib = None
        self.is_running = False
        self.is_connected = False
        
        # Strategy parameters (can be overridden by subclasses)
        self.params = self.get_default_params()
        
        # Threading
        self.loop = None
        self.thread = None
        
        add_log(f"Strategy '{self.strategy_name}' initialized for {self.symbol}", self.symbol)
    
    @abstractmethod
    def get_default_params(self) -> Dict[str, Any]:
        """
        Return default parameters for this strategy.
        Subclasses must implement this method.
        
        Returns:
            Dictionary of parameter names and default values
        """
        pass
    
    @abstractmethod
    async def initialize_strategy(self):
        """
        Initialize strategy-specific data and setup.
        Called once after IB connection is established.
        """
        pass
    
    @abstractmethod
    async def run_strategy(self):
        """
        Main strategy execution loop.
        This is where the core trading logic should be implemented.
        """
        pass
    
    async def connect_to_ib(self) -> bool:
        """
        Connect to Interactive Brokers with this strategy's client ID.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.ib = await connect_to_ib(client_id=self.client_id, symbol=self.symbol)
            if self.ib:
                self.is_connected = True
                add_log(f"Connected to IB with clientId={self.client_id}", self.symbol)
                return True
            else:
                add_log(f"Failed to connect to IB", self.symbol, "ERROR")
                return False
        except Exception as e:
            add_log(f"IB connection error: {e}", self.symbol, "ERROR")
            return False
    
    async def disconnect_from_ib(self):
        """Disconnect from Interactive Brokers"""
        if self.ib and self.is_connected:
            await disconnect_from_ib(self.ib, self.symbol)
            self.is_connected = False
    
    def start_strategy(self):
        """
        Start the strategy in its own thread with isolated event loop.
        """
        if self.is_running:
            add_log(f"Strategy already running", self.symbol, "WARNING")
            return
        
        self.is_running = True
        self.thread = threading.Thread(target=self._run_in_thread, daemon=True)
        self.thread.start()
        add_log(f"Strategy thread started", self.symbol)
    
    def stop_strategy(self):
        """
        Stop the strategy and clean up resources.
        """
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.loop and self.loop.is_running():
            # Schedule cleanup in the strategy's event loop
            self.loop.call_soon_threadsafe(self._schedule_cleanup)
        
        add_log(f"Strategy stop requested", self.symbol)
    
    def _run_in_thread(self):
        """
        Run the strategy in its own thread with isolated event loop.
        """
        try:
            # Create new event loop for this thread
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Run the main strategy coroutine
            self.loop.run_until_complete(self._main_strategy_loop())
            
        except Exception as e:
            add_log(f"Strategy thread error: {e}", self.symbol, "ERROR")
        finally:
            # Cleanup
            if self.loop:
                self.loop.close()
            add_log(f"Strategy thread terminated", self.symbol)
    
    async def _main_strategy_loop(self):
        """
        Main strategy execution loop that handles connection and lifecycle.
        """
        try:
            # Connect to IB
            if not await self.connect_to_ib():
                add_log(f"Failed to connect to IB, strategy stopping", self.symbol, "ERROR")
                return
            
            # Initialize strategy
            await self.initialize_strategy()
            add_log(f"Strategy initialized successfully", self.symbol)
            
            # Run main strategy logic
            await self.run_strategy()
            
        except Exception as e:
            add_log(f"Strategy execution error: {e}", self.symbol, "ERROR")
        finally:
            await self._cleanup()
    
    def _schedule_cleanup(self):
        """Schedule cleanup in the event loop"""
        asyncio.create_task(self._cleanup())
    
    async def _cleanup(self):
        """Clean up strategy resources"""
        try:
            await self.disconnect_from_ib()
            self.is_running = False
            add_log(f"Strategy cleanup completed", self.symbol)
        except Exception as e:
            add_log(f"Cleanup error: {e}", self.symbol, "ERROR")
    
    # Event handlers for order management
    def on_fill(self, trade: Trade, fill):
        """
        Handle order fill events.
        Override in subclasses for custom fill handling.
        """
        add_log(f"Fill: {fill.execution.side} {fill.execution.shares} @ {fill.execution.price}", self.symbol)
        
        # Notify strategy manager if available
        if self.strategy_manager:
            self.strategy_manager.handle_fill_event(self.symbol, trade, fill)
    
    def on_status_change(self, trade: Trade):
        """
        Handle order status change events.
        Override in subclasses for custom status handling.
        """
        status = trade.orderStatus.status
        if "Pending" not in status:
            add_log(f"Order status: {status}", self.symbol)
            
            # Notify strategy manager if available
            if self.strategy_manager:
                self.strategy_manager.handle_status_change(self.symbol, trade, status)
    
    def update_params(self, new_params: Dict[str, Any]):
        """
        Update strategy parameters.
        
        Args:
            new_params: Dictionary of parameter updates
        """
        self.params.update(new_params)
        add_log(f"Parameters updated: {new_params}", self.symbol)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current strategy status.
        
        Returns:
            Dictionary containing strategy status information
        """
        return {
            "name": self.strategy_name,
            "symbol": self.symbol,
            "client_id": self.client_id,
            "is_running": self.is_running,
            "is_connected": self.is_connected,
            "params": self.params
        }
