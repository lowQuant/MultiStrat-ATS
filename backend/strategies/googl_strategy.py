"""
GOOGL Strategy - Simple buy one share strategy
"""
import asyncio
from typing import Dict, Any
from ib_async import Stock
from strategies.base_strategy import BaseStrategy
from core.log_manager import add_log


class GOOGLStrategy(BaseStrategy):
    """
    Simple GOOGL strategy that buys one share of GOOGL stock.
    """
    
    def __init__(self, client_id: int, strategy_manager=None):
        super().__init__(
            client_id=client_id,
            strategy_name="GOOGL Buy Strategy",
            symbol="GOOGL",
            strategy_manager=strategy_manager
        )
        self.order_placed = False
    
    def get_default_params(self) -> Dict[str, Any]:
        """Return default parameters for GOOGL strategy"""
        return {
            "symbol": "GOOGL",
            "quantity": 1,
            "order_type": "MKT",  # Market order
            "exchange": "SMART",
            "currency": "USD"
        }
    
    async def initialize_strategy(self):
        """Initialize GOOGL strategy"""
        add_log(f"Initializing GOOGL strategy with params: {self.params}", self.symbol)
        
        # Create the contract
        self.contract = Stock(
            symbol=self.params["symbol"],
            exchange=self.params["exchange"],
            currency=self.params["currency"]
        )
        
        # Qualify the contract
        await self.ib.qualifyContractsAsync(self.contract)
        add_log(f"Contract qualified: {self.contract}", self.symbol)
    
    async def run_strategy(self):
        """
        Main strategy logic - buy one share of GOOGL
        """
        add_log(f"Starting GOOGL strategy execution", self.symbol)
        
        try:
            # Place a market order to buy 1 share
            if not self.order_placed:
                add_log(f"Placing market order: BUY {self.params['quantity']} {self.params['symbol']}", self.symbol)
                
                # Create market order
                from ib_async import MarketOrder
                order = MarketOrder(
                    action="BUY",
                    totalQuantity=self.params["quantity"]
                )
                
                # Place the order
                trade = self.ib.placeOrder(self.contract, order)
                
                # Set up event handlers
                trade.fillEvent += self.on_fill
                trade.statusEvent += self.on_status_change
                
                self.order_placed = True
                add_log(f"Order placed successfully: {trade.order.orderId}", self.symbol)
            
            # Keep the strategy running to monitor the order
            while self.is_running:
                await asyncio.sleep(5)  # Check every 5 seconds
                
                # Log current positions periodically
                positions = self.ib.positions()
                googl_positions = [pos for pos in positions if pos.contract.symbol == "GOOGL"]
                
                if googl_positions:
                    for pos in googl_positions:
                        add_log(f"Current GOOGL position: {pos.position} shares @ avg cost {pos.avgCost}", self.symbol)
                
        except Exception as e:
            add_log(f"Error in strategy execution: {e}", self.symbol, "ERROR")
    
    def on_fill(self, trade, fill):
        """Handle order fill"""
        super().on_fill(trade, fill)
        add_log(f"GOOGL order filled: {fill.execution.shares} shares @ ${fill.execution.price}", self.symbol)
    
    def on_status_change(self, trade):
        """Handle order status changes"""
        super().on_status_change(trade)
        status = trade.orderStatus.status
        add_log(f"GOOGL order status: {status}", self.symbol)
        
        if status == "Filled":
            add_log(f"GOOGL strategy completed successfully!", self.symbol)
