"""
Buy & Hold Strategy

- Buys 100% of available equity in the specified symbol on the first bar
- Holds until the backtest ends (no further trades)
- Works in both live and backtest modes (in live it will buy once on start)

PARAMS example:
{
  "symbol": "AAPL",
  "position_size": 1.0
}
"""
from __future__ import annotations

import asyncio
from typing import Optional
import pandas as pd
from ib_async import Stock, MarketOrder, BarDataList

from obj.base_strategy import BaseStrategy
from core.log_manager import add_log

PARAMS = {
    "symbol": "ORCL",
    "position_size": 1.0,  # 100% of allocated equity
}


class BuyHoldStrategy(BaseStrategy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Use strategy params or default; symbol will also be bound by strategy_symbol
        try:
            if isinstance(self.params, dict) and self.params.get("symbol"):
                self.symbol = str(self.params["symbol"]).upper()
        except Exception:
            pass
        self.contract = None
        self._bought = False

    async def initialize_strategy(self):
        sym = str(self.params.get("symbol", self.symbol)).upper()
        self.contract = Stock(sym, "SMART", "USD")
        # Qualify contract in live; skip in backtest
        if self.broker_type == "live" and self.ib and self.is_connected:
            try:
                await self.ib.qualifyContractsAsync(self.contract)
            except Exception:
                pass
        add_log(f"Strategy 'BuyHoldStrategy' initialized for {sym}", self.symbol)

    # Generic bar handler used by BacktestManager and live bar streams
    def on_bar(self, bars: BarDataList, hasNewBar: bool):
        if not hasNewBar or self._bought is True:
            return
        # Attempt to buy once on first bar
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._buy_once())
        except RuntimeError:
            # No running loop (backtest context) -> run synchronously
            asyncio.run(self._buy_once())

    async def _buy_once(self):
        if self._bought:
            return
        if not self.broker:
            add_log("Broker not initialized; cannot place order", self.symbol, "ERROR")
            return
        try:
            size = float(self.params.get("position_size", 1.0))
            order = MarketOrder("BUY", 0)  # size-based sizing via broker
            add_log(f"[BuyHold] Placing BUY with {size*100:.1f}% of equity", self.symbol)
            trade = await self.broker.place_order(
                contract=self.contract,
                order=order,
                size=size,
            )
            if trade:
                self._bought = True
                add_log("[BuyHold] Initial position established", self.symbol)
        except Exception as e:
            add_log(f"[BuyHold] Failed to place order: {e}", self.symbol, "ERROR")

    # Backward-compatible alias if wired differently
    def handle_realtime_bars(self, bars: BarDataList, hasNewBar: bool):
        self.on_bar(bars, hasNewBar)

    async def run_strategy(self):
        """
        Minimal run loop to satisfy abstract method and allow live usage.
        In backtest, BacktestManager drives bars via on_bar and we return immediately.
        """
        if self.broker_type == "backtest":
            return
        # Live mode: optionally subscribe to bars here in a more complete version.
        # For now, idle loop.
        try:
            while self.is_running:
                await asyncio.sleep(1)
        except Exception as e:
            add_log(f"[BuyHold] run_strategy error: {e}", self.symbol, "ERROR")
