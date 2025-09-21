import asyncio
from datetime import datetime, time, timedelta
from typing import Dict, Any, Optional, List

from ib_async import MarketOrder, RealTimeBar
from ib_async.contract import Stock

from obj.base_strategy import BaseStrategy
from core.log_manager import add_log


PARAMS = {
    "opening_range_minutes": 5,
    "quantity": 1,  # used if equity unknown (live fallback)
    "risk_percent": 0.01,
    "take_profit_multiple": 10,
    "max_leverage": 4.0,
    "exchange": "SMART",
    "currency": "USD",
}


class TqqqStrategy(BaseStrategy):
    """
    Opening Range Breakout (ORB) for a single asset
    - Symbol: TQQQ
    - Logic: Define opening range as the first 5 minutes of RTH.
             Once the first 5 minutes pass, buy if the next bar trades above the OR high,
             or sell if it trades below the OR low. Fire once, then stop.
    """

    def __init__(self, client_id: int, strategy_manager, params: Optional[Dict[str, Any]] = None):
        super().__init__(client_id=client_id, strategy_manager=strategy_manager, params=params)
        # State
        self.or_high: Optional[float] = None
        self.or_low: Optional[float] = None
        self.triggered: bool = False
        self._sub = None  # realtime subscription handle
        # ORB extensions
        self.current_day: Optional[Any] = None
        self.current_day_open: Optional[float] = None
        self.exit_minute_bar: time = time(15, 59)
        self.early_close_datetimes: List[str] = [
            "2017-07-03 12:59:00",
            "2018-07-03 12:59:00",
            "2018-11-23 12:59:00",
            "2019-12-24 12:59:00",
            "2020-11-27 12:59:00",
            "2020-12-24 12:59:00",
        ]
        # Trade tracking for backtests
        self.open_trade: Optional[Dict[str, Any]] = None
        self.closed_trades: List[Dict[str, Any]] = []


    async def initialize_strategy(self):
        """Fetch today's 1-min bars and compute the 5-min opening range (live only).
        In backtest mode (when a BacktestIB is injected), skip remote calls.
        """
        # Backtest detection: BacktestIB exposes _engine
        if hasattr(self, "ib") and hasattr(self.ib, "_engine"):
            add_log("Backtest mode detected - skipping live data fetch", self.symbol)
            return
        # Pull 1D of 1-minute bars (RTH only); find today's first 5 minutes
        bars = await self.ib.reqHistoricalDataAsync(
            Stock(self.symbol, self.params.get("exchange", "SMART"), self.params.get("currency", "USD")),
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

    # ----- Helpers for backtest mode -----
    def _reset_range(self, day, opening_price: float):
        self.current_day = day
        self.current_day_open = opening_price
        self.or_high = None
        self.or_low = None
        self.triggered = False
        self._or_logged = False  # Reset OR logging flag

    def _estimate_equity(self) -> float:
        # Get equity from broker interface
        try:
            if hasattr(self, "ib") and hasattr(self.ib, "_engine"):
                # Backtest: use engine equity
                return float(self.ib._engine.equity())
            elif hasattr(self, "ib") and hasattr(self.ib, "positions"):
                # Live: calculate from positions + cash (simplified)
                # TODO: Implement proper portfolio value calculation
                return 100_000.0
        except Exception:
            pass
        # Fallback
        return 100_000.0

    def _get_position_size(self, entry_price: float, stop_price: float) -> int:
        per_share_risk = abs(entry_price - stop_price)
        if per_share_risk <= 0:
            return 0
        equity = self._estimate_equity()
        risk_percent = float(self.params.get("risk_percent", 0.01))
        max_leverage = float(self.params.get("max_leverage", 4.0))
        shares_by_risk = (risk_percent * equity) / per_share_risk
        shares_by_leverage = (max_leverage * equity) / max(entry_price, 1e-9)
        return int(max(0, min(shares_by_risk, shares_by_leverage)))

    def _maybe_close_eod(self, t: datetime, last_price: float):
        if not self.open_trade:
            return
        # Exit at 15:59 or early-close timestamps
        current_bar_date = t.date()
        current_bar_date_time = f"{current_bar_date} {t.time()}"
        if t.time() == self.exit_minute_bar or current_bar_date_time in self.early_close_datetimes:
            add_log(f"[{t.date()} {t.time()}] EOD exit @ {last_price:.2f}", self.symbol)
            self._close_position(last_price, t)

    def _close_position(self, exit_price: float, exit_time: datetime):
        if not self.open_trade:
            return
        trade = self.open_trade
        side = trade["side"]
        qty = trade["qty"]
        try:
            # Exit order
            action = "SELL" if side == "long" else "BUY"
            contract = Stock(self.symbol, self.params.get("exchange", "SMART"), self.params.get("currency", "USD"))
            self.ib.placeOrder(contract, MarketOrder(action, int(qty)))
        except Exception:
            pass
        # Compute P&L and record trade
        entry_price = float(trade["entry_price"])
        if side == "long":
            pnl = (exit_price - entry_price) * qty
            ret = (exit_price - entry_price) / max(entry_price, 1e-9)
        else:
            pnl = (entry_price - exit_price) * qty
            ret = (entry_price - exit_price) / max(entry_price, 1e-9)
        record = {
            "trade_id": f"{self.symbol}_{trade['entry_time'].isoformat()}",
            "symbol": self.symbol,
            "side": side,
            "qty": int(qty),
            "entry_time": trade["entry_time"],
            "entry_price": float(entry_price),
            "exit_time": exit_time,
            "exit_price": float(exit_price),
            "pnl": float(pnl),
            "return_pct": float(ret),
            "won": pnl > 0,
        }
        self.closed_trades.append(record)
        self.open_trade = None
        # Don't reset triggered here - let daily reset handle it

    async def run_strategy(self):
        """
        Subscribe to real-time 5-second bars and wait for:
        - If OR not computed yet, compute after 5 minutes worth of 1-min bars becomes available
        - After OR is set, if last_bar.close > ORH -> BUY qty; if < ORL -> SELL qty
        Fire once and stop the strategy.
        """
        # Subscribe to 5-second bars (higher resolution helps detect the first break after OR window)
        self._sub = self.ib.reqRealTimeBars(
            Stock(self.symbol, self.params.get("exchange", "SMART"), self.params.get("currency", "USD")),
            barSize=5,  # 5-second bars
            whatToShow="TRADES",
            useRTH=True
        )

        # Wire instance method as callback
        self._sub.updateEvent += self.handle_realtime_bars

        # Keep strategy alive until stop requested
        await asyncio.Event().wait()

    def _place_order(self, side: str, planned_entry_price: float, stop_loss_price: float, t: datetime, range_size: float):
        try:
            qty = self._get_position_size(planned_entry_price, stop_loss_price)
            if qty <= 0:
                add_log("Calculated position size is 0; skipping order", self.symbol, "WARNING")
                return
            contract = Stock(self.symbol, self.params.get("exchange", "SMART"), self.params.get("currency", "USD"))
            order = MarketOrder(side, int(qty))
            self.ib.placeOrder(contract, order)
            equity = self._estimate_equity()
            add_log(f"[{t.date()} {t.time()}] Placed {side} {qty} {self.symbol} @ {planned_entry_price:.2f} (Equity: ${equity:,.0f}, Risk/share: ${abs(planned_entry_price - stop_loss_price):.2f})", self.symbol)
            # Set TP
            take_profit_multiple = float(self.params.get("take_profit_multiple", 10))
            if side == "BUY":
                tp = planned_entry_price + take_profit_multiple * range_size
                sl = stop_loss_price
                self.open_trade = {
                    "side": "long",
                    "qty": int(qty),
                    "entry_time": t,
                    "entry_price": float(planned_entry_price),
                    "tp": float(tp),
                    "sl": float(sl),
                }
                # Submit protective stop (SELL STP)
                try:
                    from ib_async import Order
                    stp = Order()
                    stp.orderType = 'STP'
                    stp.action = 'SELL'
                    stp.totalQuantity = int(qty)
                    stp.auxPrice = float(sl)
                    self.ib.placeOrder(contract, stp)
                    add_log(f"[{t.date()} {t.time()}] Submitted protective STOP SELL @ {sl:.2f}", self.symbol)
                except Exception:
                    pass
            else:
                tp = planned_entry_price - take_profit_multiple * range_size
                sl = stop_loss_price
                self.open_trade = {
                    "side": "short",
                    "qty": int(qty),
                    "entry_time": t,
                    "entry_price": float(planned_entry_price),
                    "tp": float(tp),
                    "sl": float(sl),
                }
                # Submit protective stop (BUY STP)
                try:
                    from ib_async import Order
                    stp = Order()
                    stp.orderType = 'STP'
                    stp.action = 'BUY'
                    stp.totalQuantity = int(qty)
                    stp.auxPrice = float(sl)
                    self.ib.placeOrder(contract, stp)
                    add_log(f"[{t.date()} {t.time()}] Submitted protective STOP BUY @ {sl:.2f}", self.symbol)
                except Exception:
                    pass
        except Exception as e:
            add_log(f"Order placement failed: {e}", self.symbol, "ERROR")

    # New: expose realtime handler for reuse in backtests and override on_bar
    def handle_realtime_bars(self, bars: List[RealTimeBar], hasNewBar: bool):
        try:
            if not bars:
                return
            last_bar = bars[-1]

            # OR calculation is handled per-day below - no fallback from accumulated bars

            # Get bar timestamp
            t = last_bar.time if hasattr(last_bar, 'time') else None
            if t is None:
                return
            
            # Check for new day and reset
            bar_date = t.date() if hasattr(t, 'date') else None
            if bar_date is not None and bar_date != self.current_day:
                add_log(f"New trading day: {bar_date} (prev: {self.current_day})", self.symbol)
                self._reset_range(bar_date, last_bar.open)
            
            # Define OR window end time
            last_or_minute = time(9, 30 + int(self.params.get("opening_range_minutes", 5)))
            
            # Accumulate OR during the first N minutes (fresh each day)
            if hasattr(t, 'time') and t.time() < last_or_minute:
                # Update OR highs/lows for current day only
                if last_bar.high is not None:
                    self.or_high = max(self.or_high, last_bar.high) if self.or_high is not None else last_bar.high
                if last_bar.low is not None:
                    self.or_low = min(self.or_low, last_bar.low) if self.or_low is not None else last_bar.low
                add_log(f"[{bar_date} {t.time()}] OR building: High={self.or_high:.2f} Low={self.or_low:.2f}", self.symbol)
                return  # Don't trade during OR window

            if self.or_high is None or self.or_low is None:
                return

            # Check breakout conditions after OR window (only once per day)
            if not self.triggered and hasattr(t, 'time') and t.time() >= last_or_minute:
                # Log OR completion only once when we first pass the OR window
                if self.or_high and self.or_low and not hasattr(self, '_or_logged'):
                    add_log(f"[{bar_date}] OR complete: High={self.or_high:.2f} Low={self.or_low:.2f}", self.symbol)
                    self._or_logged = True
                range_size = (self.or_high - self.or_low) if (self.or_high is not None and self.or_low is not None) else None
                if range_size is None or range_size <= 0:
                    return
                
                planned_entry_price = last_bar.close
                if self.current_day_open is not None and planned_entry_price is not None:
                    if planned_entry_price > self.or_high:
                        # Breakout above OR high
                        stop_loss_price = float(self.or_low)
                        self._place_order("BUY", planned_entry_price, stop_loss_price, t, range_size)
                        self.triggered = True
                        add_log(f"[{bar_date} {t.time()}] Long signal: price {planned_entry_price:.2f} > OR high {self.or_high:.2f}", self.symbol)
                    elif planned_entry_price < self.or_low:
                        # Breakdown below OR low
                        stop_loss_price = float(self.or_high)
                        self._place_order("SELL", planned_entry_price, stop_loss_price, t, range_size)
                        self.triggered = True
                        add_log(f"[{bar_date} {t.time()}] Short signal: price {planned_entry_price:.2f} < OR low {self.or_low:.2f}", self.symbol)
                    else:
                        # Price within OR, wait for breakout
                        pass
                return

            # Manage open position: TP/SL and EOD close
            if self.open_trade:
                t = last_bar.time if hasattr(last_bar, 'time') else None
                if t is None:
                    return
                side = self.open_trade["side"]
                tp = float(self.open_trade["tp"])  # target price
                sl = float(self.open_trade["sl"])  # stop price
                # Use bar high/low if available; else close
                bar_high = getattr(last_bar, 'high', None)
                bar_low = getattr(last_bar, 'low', None)
                bar_close = getattr(last_bar, 'close', None)
                if side == "long":
                    if (bar_high is not None and bar_high >= tp) or (bar_low is not None and bar_low <= sl):
                        exit_px = tp if (bar_high is not None and bar_high >= tp) else sl
                        exit_reason = "TP" if exit_px == tp else "SL"
                        add_log(f"[{t.date()} {t.time()}] Exit {side} @ {exit_px:.2f} ({exit_reason})", self.symbol)
                        self._close_position(exit_px, t)
                    else:
                        self._maybe_close_eod(t, bar_close)
                else:
                    if (bar_low is not None and bar_low <= tp) or (bar_high is not None and bar_high >= sl):
                        exit_px = tp if (bar_low is not None and bar_low <= tp) else sl
                        exit_reason = "TP" if exit_px == tp else "SL"
                        add_log(f"[{t.date()} {t.time()}] Exit {side} @ {exit_px:.2f} ({exit_reason})", self.symbol)
                        self._close_position(exit_px, t)
                    else:
                        self._maybe_close_eod(t, bar_close)
        except Exception as e:
            add_log(f"Realtime handler error: {e}", self.symbol, "ERROR")
    def on_bar(self, bars, hasNewBar: bool):
        self.handle_realtime_bars(bars, hasNewBar)
