"""
Simple backtest engine to:
- Hold historical bars for one or more symbols
- Emit bar updates to subscribed tickers (IB-like mock)
- Simulate fills for simple market/limit orders
- Track cash/positions and compute equity

Deliberately minimal to match the current strategies' needs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .mock_ib import (
    MockHistoricalBar,
    MockPortfolioItem,
    MockRealTimeBar,
)


@dataclass
class Position:
    quantity: float = 0.0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 100_000.0,
        commission_per_share: float = 0.005,
        slippage_bps: float = 0.0,
    ) -> None:
        self.initial_capital = float(initial_capital)
        self.cash = float(initial_capital)
        self.commission_per_share = float(commission_per_share)
        self.slippage_bps = float(slippage_bps)

        # Data and time state
        self._data: Dict[str, pd.DataFrame] = {}
        self._iter_idx: Dict[str, int] = {}
        self._tickers: Dict[str, Any] = {}  # symbol -> MockTicker

        # Portfolio state
        self._positions: Dict[str, Position] = {}

        # Order state
        # Orders scheduled to fill at next bar OPEN per symbol
        self._orders_next_open: Dict[str, List[Any]] = {}
        # Stop orders active until triggered or cancelled: symbol -> List[trade]
        self._stop_orders: Dict[str, List[Any]] = {}
        self._pending_trades: List[Any] = []  # reserved for future use (limits, etc.)
        self._filled_trades: List[Any] = []

        # Cache last price per symbol for portfolio
        self._last_price: Dict[str, float] = {}

    # ---------------------- Data loading and building ----------------------
    def load_data(self, symbol: str, df: pd.DataFrame) -> None:
        df = df.copy()
        # Normalize columns
        rename_map = {c: c.lower() for c in df.columns}
        df.rename(columns=rename_map, inplace=True)
        # Ensure needed cols exist
        required = ["open", "high", "low", "close"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Data for {symbol} missing column: {col}")
        # Ensure sorted by time
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()
        self._data[symbol] = df
        self._iter_idx[symbol] = 0

    def build_historical_bars(
        self, contract: Any, durationStr: str, barSizeSetting: str, useRTH: bool
    ) -> List[MockHistoricalBar]:
        symbol = getattr(contract, "symbol", None) or getattr(contract, "localSymbol", "")
        if symbol not in self._data:
            return []
        df = self._data[symbol]
        bars: List[MockHistoricalBar] = []
        for ts, row in df.iterrows():
            bars.append(
                MockHistoricalBar(
                    date=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                )
            )
        return bars

    # ---------------------- Subscriptions and stepping ----------------------
    def register_ticker(self, contract: Any, ticker: Any, barSize: int, useRTH: bool) -> None:
        symbol = getattr(contract, "symbol", None) or getattr(contract, "localSymbol", "")
        self._tickers[symbol] = ticker
        # Ensure data is present
        if symbol not in self._data:
            raise ValueError(f"No data loaded for symbol {symbol}")

    def step(self) -> bool:
        """Advance one bar for all registered tickers; return False when done."""
        any_advanced = False
        for symbol, ticker in list(self._tickers.items()):
            idx = self._iter_idx.get(symbol, 0)
            df = self._data[symbol]
            if idx >= len(df):
                continue
            ts = df.index[idx]
            row = df.iloc[idx]
            bar = MockRealTimeBar(
                time=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
            )
            # 1) Fill any orders scheduled from prior bar at THIS bar's OPEN
            self._fill_orders_at_open(symbol, bar)
            # 1b) Check and trigger stop orders using this bar's range
            self._check_and_trigger_stops(symbol, bar)
            ticker.bars.append(bar)
            self._last_price[symbol] = bar.close
            # Emit update
            ticker.updateEvent.emit(ticker.bars, True)
            # Move index
            self._iter_idx[symbol] = idx + 1
            any_advanced = True
        return any_advanced

    # ---------------------- Orders and fills ----------------------
    def submit_order(self, trade: Any) -> None:
        """Schedule order to fill at the next bar's OPEN for the symbol."""
        symbol = getattr(trade.contract, "symbol", None) or getattr(trade.contract, "localSymbol", "")
        # Initialize order status
        qty = float(getattr(trade.order, "totalQuantity", 0))
        trade.orderStatus.status = "Submitted"
        trade.orderStatus.filled = 0.0
        trade.orderStatus.remaining = qty
        trade.orderStatus.avgFillPrice = 0.0
        otype = getattr(trade.order, "orderType", "MKT")
        if otype == "STP":
            # Keep active until triggered
            stops = self._stop_orders.setdefault(symbol, [])
            stops.append(trade)
        else:
            # Schedule for next open
            q = self._orders_next_open.setdefault(symbol, [])
            q.append(trade)
        # Emit status
        trade.statusEvent.emit(trade)

    def _fill_orders_at_open(self, symbol: str, bar: MockRealTimeBar) -> None:
        q = self._orders_next_open.get(symbol, [])
        if not q:
            return
        self._orders_next_open[symbol] = []
        for trade in q:
            action = getattr(trade.order, "action", "BUY")
            qty = float(getattr(trade.order, "totalQuantity", 0))
            if qty <= 0:
                continue
            otype = getattr(trade.order, "orderType", "MKT")
            commission = qty * float(self.commission_per_share)
            side = "BOT" if action == "BUY" else "SLD"

            do_fill = False
            fill_price = None
            if otype == "MKT":
                # Market fills at next bar's OPEN with slippage
                slip = bar.open * (self.slippage_bps / 10_000.0)
                fill_price = bar.open + (slip if action == "BUY" else -slip)
                do_fill = True
            elif otype == "LMT":
                lmt_price = getattr(trade.order, "lmtPrice", None)
                if lmt_price is None:
                    continue
                if action == "BUY":
                    # Fill if next bar traded down to or below limit
                    if bar.low <= lmt_price:
                        # If gap down through the limit, you get the better price (open)
                        fill_price = min(bar.open, lmt_price) if bar.open <= lmt_price else lmt_price
                        do_fill = True
                else:  # SELL
                    if bar.high >= lmt_price:
                        # If gap up through the limit, you get the better price (open)
                        fill_price = max(bar.open, lmt_price) if bar.open >= lmt_price else lmt_price
                        do_fill = True
            else:
                # Unsupported order types are ignored in this minimal engine
                continue

            if do_fill and fill_price is not None:
                self._apply_fill(symbol, qty if action == "BUY" else -qty, float(fill_price), commission)
                # Update trade status and emit events
                trade.orderStatus.filled = qty
                trade.orderStatus.remaining = 0.0
                trade.orderStatus.avgFillPrice = float(fill_price)
                trade.orderStatus.status = "Filled"
                from .mock_ib import MockFill
                fill = MockFill(side=side, shares=qty, price=float(fill_price), commission=commission, time=bar.time)
                trade.fills.append(fill)
                trade.fillEvent.emit(trade, fill)
                trade.statusEvent.emit(trade)
                self._filled_trades.append(trade)

    def _check_and_trigger_stops(self, symbol: str, bar: MockRealTimeBar) -> None:
        stops = self._stop_orders.get(symbol, [])
        if not stops:
            return
        remaining: List[Any] = []
        for trade in stops:
            action = getattr(trade.order, "action", "SELL")  # stops typically exit
            qty = float(getattr(trade.order, "totalQuantity", 0))
            stop_price = float(getattr(trade.order, "auxPrice", 0.0))
            if qty <= 0 or stop_price <= 0:
                continue
            triggered = False
            fill_price = None
            commission = qty * float(self.commission_per_share)
            side = "BOT" if action == "BUY" else "SLD"
            if action == "SELL":
                # Long stop: trigger if bar.low <= stop
                if bar.low <= stop_price:
                    # If gapped down through stop -> you get worse price (open if below stop)
                    fill_price = min(bar.open, stop_price)
                    triggered = True
            else:  # BUY stop for short
                if bar.high >= stop_price:
                    fill_price = max(bar.open, stop_price)
                    triggered = True
            if triggered and fill_price is not None:
                self._apply_fill(symbol, -qty if action == "SELL" else qty, float(fill_price), commission)
                trade.orderStatus.filled = qty
                trade.orderStatus.remaining = 0.0
                trade.orderStatus.avgFillPrice = float(fill_price)
                trade.orderStatus.status = "Filled"
                from .mock_ib import MockFill
                fill = MockFill(side=side, shares=qty, price=float(fill_price), commission=commission, time=bar.time)
                trade.fills.append(fill)
                trade.fillEvent.emit(trade, fill)
                trade.statusEvent.emit(trade)
                self._filled_trades.append(trade)
            else:
                remaining.append(trade)
        self._stop_orders[symbol] = remaining

    def force_flatten(self, symbol: str, price: float, time: Any) -> None:
        """Immediately flatten all positions for symbol at given price (used for EOD)."""
        pos = self._positions.get(symbol)
        if not pos or pos.quantity == 0:
            return
        qty = abs(pos.quantity)
        action_sign = -1 if pos.quantity > 0 else 1
        commission = qty * float(self.commission_per_share)
        self._apply_fill(symbol, action_sign * qty, float(price), commission)

    def _apply_fill(self, symbol: str, signed_qty: float, price: float, commission: float) -> None:
        pos = self._positions.get(symbol, Position())
        q0, c0 = pos.quantity, pos.avg_cost
        q1 = q0 + signed_qty
        if q1 == 0:
            # fully closed; realize pnl
            realized = q0 * (price - c0) if q0 > 0 else (-q0) * (c0 - price)
            pos.realized_pnl += realized - commission
            pos.quantity = 0.0
            pos.avg_cost = 0.0
        elif (q0 >= 0 and signed_qty > 0) or (q0 <= 0 and signed_qty < 0):
            # increasing same-side position -> update average cost
            notional = q0 * c0 + signed_qty * price
            pos.quantity = q1
            pos.avg_cost = notional / q1
            pos.realized_pnl -= commission
        else:
            # reducing or flipping -> realize pnl on the portion that closes
            closing = min(abs(q0), abs(signed_qty))
            if q0 > 0:
                realized = closing * (price - c0)
            else:
                realized = closing * (c0 - price)
            pos.realized_pnl += realized - commission
            pos.quantity = q1
            if q1 != 0:
                pos.avg_cost = price  # new side starts at fill price
            else:
                pos.avg_cost = 0.0
        self._positions[symbol] = pos
        # Cash update
        self.cash -= signed_qty * price + commission

    # ---------------------- Reports ----------------------
    def equity(self) -> float:
        total = self.cash
        for symbol, pos in self._positions.items():
            last = self._last_price.get(symbol, pos.avg_cost)
            total += pos.quantity * last
        return float(total)

    def build_portfolio_items(self) -> List[MockPortfolioItem]:
        items: List[MockPortfolioItem] = []
        for symbol, pos in self._positions.items():
            last = self._last_price.get(symbol, pos.avg_cost)
            market_value = pos.quantity * last
            unrealized = pos.quantity * (last - pos.avg_cost)
            items.append(
                MockPortfolioItem(
                    contract=self._mock_contract(symbol),
                    position=pos.quantity,
                    averageCost=pos.avg_cost,
                    marketPrice=last,
                    marketValue=market_value,
                    unrealizedPNL=unrealized,
                    realizedPNL=pos.realized_pnl,
                    account="BACKTEST",
                )
            )
        return items

    @staticmethod
    def _mock_contract(symbol: str):
        class _C:
            def __init__(self, sym: str) -> None:
                self.symbol = sym
                self.secType = "STK"
                self.exchange = "SMART"
                self.currency = "USD"
        return _C(symbol)
