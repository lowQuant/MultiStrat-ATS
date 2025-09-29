import asyncio
from typing import Optional, Dict, Any

from ib_async import Stock
from obj.base_strategy import BaseStrategy, PARAMS as BASE_PARAMS
from core.log_manager import add_log

# Extend base params for a simple template
PARAMS = {
    **BASE_PARAMS,
    # Universe can be a single symbol or comma-separated list
    "universe": "SIE",
    # Allocation guidance (can be overridden in ArcticDB general/strategies)
    "target_weight": 0.10,
    "min_weight": 0.0,
    "max_weight": 1.0,
    # Risk controls
    "max_position_size": 0.25,
    "risk_per_trade": 0.01,
    "stop_loss": 0.03,
    "trailing_stop_loss": 0.10,
    "profit_target": 0.20,
}


class TemplateStrategy(BaseStrategy):
    """
    A minimal live strategy template using BaseStrategy wrappers only.
    - Demonstrates warmup via get_data()
    - Demonstrates contract qualification
    - Shows how to place a sized order without calling broker directly
    """

    def __init__(self, client_id: int, strategy_manager, params: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(client_id=client_id, strategy_manager=strategy_manager, params=params, **kwargs)
        self.contract = None

    async def initialize_strategy(self):
        # Resolve primary symbol and qualify contract
        symbol = self.get_universe_symbols()[0]
        self.contract = Stock(symbol, "SMART", "EUR")
        await self.ib.qualifyContractsAsync(self.contract)

        # Warmup: load 1-min bars from ArcticDB or download full lookback if missing
        #df = await self.get_data(symbols=[symbol], timeframe="1_min", start_date="max", end_date="today", use_rth=True)
        #add_log(f"Warmup data loaded: rows={len(df) if hasattr(df, 'index') else 'n/a'}", self.symbol)

    async def run_strategy(self):
        # Example loop: idle and await external signals (e.g., UI) or event-driven logic
        # Template strategy running - replace this with your logic
        
        # Example: Place an order with status change callbacks
        trade = await self.place_order(self.contract, quantity=1, order_type='MKT', useRth=False)
        
        # Set up event handlers for order status changes
        if trade:
            trade.fillEvent += self.on_fill
            trade.statusEvent += self.on_status_change
        
        while self.is_running:
            await asyncio.sleep(1)
            # await self.place_order_by_size(self.contract, size=0.05, side='BUY', order_type='MKT', useRth=True)

    def on_fill(self, trade, fill):
        """Handle order fill events"""
        super().on_fill(trade, fill)
    
    def on_status_change(self, trade):
        """Handle order status changes"""
        super().on_status_change(trade)
        status = trade.orderStatus.status
        
        if status == "Filled":
            add_log(f"Template strategy order completed!", self.symbol)
