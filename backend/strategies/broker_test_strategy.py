"""
Test Strategy for Broker Abstraction
This strategy demonstrates the use of the new broker abstraction layer.
"""
from ib_async import Stock, MarketOrder, Contract
from obj.base_strategy import BaseStrategy
from core.log_manager import add_log
import asyncio


PARAMS = {
    "test_mode": True,
    "order_size": 0.5,  # Use 50% of allocated equity
    "symbol": "AAPL",
    "test_interval": 10  # seconds between test orders
}


class BrokerTestStrategy(BaseStrategy):
    """
    Test strategy to verify broker abstraction works correctly.
    This strategy places a test order using the broker abstraction.
    """
    
    async def initialize_strategy(self):
        """Initialize the test strategy."""
        add_log(f"Initializing BrokerTestStrategy with params: {self.params}", self.symbol)
        add_log(f"Using broker type: {self.broker_type}", self.symbol)
        
        # Create contract for test trading
        self.contract = Stock(self.params.get("symbol", "AAPL"), "SMART", "USD")
        
    async def run_strategy(self):
        """
        Main strategy logic - demonstrates broker usage.
        """
        add_log(f"Starting BrokerTestStrategy main loop", self.symbol)
        
        try:
            while self.is_running:
                # Get current equity allocation for this strategy
                equity = await self.broker.get_equity()
                add_log(f"Strategy equity: ${equity:,.2f}", self.symbol)
                
                # Get current positions
                positions = await self.broker.get_positions()
                add_log(f"Current positions count: {len(positions)}", self.symbol)
                
                # Only place test orders if test_mode is enabled
                if self.params.get("test_mode", False):
                    await self._place_test_order()
                
                # Wait before next iteration
                await asyncio.sleep(self.params.get("test_interval", 10))
                
        except Exception as e:
            add_log(f"Error in strategy loop: {e}", self.symbol, "ERROR")
            
    async def _place_test_order(self):
        """Place a test order using the broker abstraction."""
        try:
            # Create a market order
            order = MarketOrder("BUY", 0)  # Quantity will be calculated by broker
            
            # Use broker to place order with size as percentage of equity
            size = self.params.get("order_size", 0.5)
            
            add_log(f"Placing test order: BUY {self.params['symbol']} with {size*100}% of allocated equity", self.symbol)
            
            trade = await self.broker.place_order(
                contract=self.contract,
                order=order,
                size=size
            )
            
            if trade:
                add_log(f"Test order placed successfully: {trade}", self.symbol)
            else:
                add_log(f"Test order failed to place", self.symbol, "WARNING")
                
        except Exception as e:
            add_log(f"Error placing test order: {e}", self.symbol, "ERROR")
