import asyncio
from datetime import datetime, time, timedelta
from typing import Dict, Any, Optional, List

from ib_async import MarketOrder, RealTimeBar
from ib_async.contract import Stock

from strategies.base_strategy import BaseStrategy
from core.log_manager import add_log


class OpeningRangeBreakoutStrategy(BaseStrategy):
    """
    Opening Range Breakout (ORB) for a single asset
    - Symbol: TQQQ
    - Logic: Define opening range as the first 5 minutes of RTH.
             Once the first 5 minutes pass, buy if the next bar trades above the OR high,
             or sell if it trades below the OR low. Fire once, then stop.
    """

    def __init__(self, client_id: int, strategy_manager=None):
        super().__init__(client_id=client_id, strategy_name="Opening Range Breakout", symbol="TQQQ", strategy_manager=strategy_manager)
        # State
        self.or_high: Optional[float] = None
        self.or_low: Optional[float] = None
        self.triggered: bool = False
        self._sub = None  # realtime subscription handle

    def get_default_params(self) -> Dict[str, Any]:
        return {
            "opening_range_minutes": 5,
            "quantity": 1,
            "exchange": "SMART",
            "currency": "USD"
        }

    async def initialize_strategy(self):
        """Fetch today's 1-min bars and compute the 5-min opening range."""
        # Pull 1D of 1-minute bars (RTH only); find today's first 5 minutes
        bars = await self.ib.reqHistoricalDataAsync(
            Stock(self.symbol, self.params["exchange"], self.params["currency"]),
            endDateTime="",
            durationStr="1 D",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=True,
            keepUpToDate=False
        )

        if not bars:
            add_log("No historical bars returned for ORB initialization", self.symbol, "ERROR")
            return

        # Determine today's date in bar timestamps and collect first 5 1-min bars from RTH open
        # Bars may carry timezone-aware datetimes; normalize to date
        # RTH open assumed 09:30 local exchange time; we identify the first 5 bars of the session by continuity
        today = None
        for b in bars:
            # first bar is most recent or oldest depending on ib_async; we will just collect today's bars
            dt_b = b.date if hasattr(b, 'date') else getattr(b, 'time', None)
            if dt_b is None:
                continue
            d = dt_b.date() if hasattr(dt_b, 'date') else None
            if d is not None:
                today = d
                break
        if today is None:
            today = datetime.utcnow().date()

        todays = [b for b in bars if (getattr(b, 'date', None) and getattr(b.date, 'date', lambda: None)() == today) or (getattr(b, 'time', None) and getattr(b.time, 'date', lambda: None)() == today)]
        if len(todays) < 6:
            # If we don't have enough 1-min bars yet, leave OR unset; realtime will fill
            add_log("Not enough 1-min bars yet to compute opening range; will compute once enough data arrives", self.symbol)
            return

        opening_range_bars = todays[: self.params["opening_range_minutes"]]
        self.or_high = max(b.high for b in opening_range_bars if b.high is not None)
        self.or_low = min(b.low for b in opening_range_bars if b.low is not None)
        add_log(f"Opening Range set: High={self.or_high:.2f} Low={self.or_low:.2f}", self.symbol)

    async def run_strategy(self):
        """
        Subscribe to real-time 5-second bars and wait for:
        - If OR not computed yet, compute after 5 minutes worth of 1-min bars becomes available
        - After OR is set, if last_bar.close > ORH -> BUY qty; if < ORL -> SELL qty
        Fire once and stop the strategy.
        """
        # Subscribe to 5-second bars (higher resolution helps detect the first break after OR window)
        ticker = self.ib.reqRealTimeBars(
            Stock(self.symbol, self.params["exchange"], self.params["currency"]),
            barSize=5,  # 5-second bars
            whatToShow="TRADES",
            useRTH=True
        )

        def on_bar(bars: List[RealTimeBar], hasNewBar: bool):
            try:
                if not bars:
                    return
                last_bar = bars[-1]

                # Compute OR lazily if not ready and we've accumulated >= 5 minutes since session start
                if self.or_high is None or self.or_low is None:
                    # Attempt to compute OR from last 5 minutes of 1-min bars from open
                    # Fallback: approximate from 60 of the 5-second bars since we started (first 5 minutes)
                    if len(bars) >= (self.params["opening_range_minutes"] * (60 // 5)):
                        recent = bars[: self.params["opening_range_minutes"] * (60 // 5)]
                        highs = [b.high for b in recent if b.high is not None]
                        lows = [b.low for b in recent if b.low is not None]
                        if highs and lows:
                            self.or_high = max(highs)
                            self.or_low = min(lows)
                            add_log(f"(Approx) Opening Range set from realtime: High={self.or_high:.2f} Low={self.or_low:.2f}", self.symbol)

                if self.or_high is None or self.or_low is None:
                    return

                # Check breakout conditions
                if not self.triggered:
                    if last_bar.close is not None and self.or_high is not None and last_bar.close > self.or_high:
                        self.triggered = True
                        add_log(f"BREAKOUT UP @ {last_bar.time} Close={last_bar.close:.2f} > ORH {self.or_high:.2f}", self.symbol)
                        self._place_order("BUY")
                        ticker.updateEvent -= on_bar
                        # stop after a small delay to allow order callbacks
                        asyncio.get_event_loop().call_later(1.0, self.stop_strategy)
                        return
                    if last_bar.close is not None and self.or_low is not None and last_bar.close < self.or_low:
                        self.triggered = True
                        add_log(f"BREAKOUT DOWN @ {last_bar.time} Close={last_bar.close:.2f} < ORL {self.or_low:.2f}", self.symbol)
                        self._place_order("SELL")
                        ticker.updateEvent -= on_bar
                        asyncio.get_event_loop().call_later(1.0, self.stop_strategy)
                        return
            except Exception as e:
                add_log(f"Realtime handler error: {e}", self.symbol, "ERROR")

        ticker.updateEvent += on_bar

        # Keep strategy alive until stop requested
        await asyncio.Event().wait()

    def _place_order(self, side: str):
        try:
            contract = Stock(self.symbol, self.params["exchange"], self.params["currency"])
            order = MarketOrder(side, int(self.params["quantity"]))
            trade = self.ib.placeOrder(contract, order)
            add_log(f"Placed {side} {self.params['quantity']} {self.symbol} (Market)", self.symbol)
        except Exception as e:
            add_log(f"Order placement failed: {e}", self.symbol, "ERROR")
