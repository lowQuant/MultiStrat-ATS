"""
IB-like mock components for backtesting that match the minimal surface
area used by strategies in this repo (ib_async-style events & objects).
"""
from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import dataclass
import pandas as pd
from typing import Any, Callable, List, Optional


class Event:
    """Lightweight event emitter compatible with `+=` / `-=` handlers."""

    def __init__(self) -> None:
        self._handlers: List[Callable] = []

    def __iadd__(self, handler: Callable):  # event += handler
        if handler not in self._handlers:
            self._handlers.append(handler)
        return self

    def __isub__(self, handler: Callable):  # event -= handler
        try:
            self._handlers.remove(handler)
        except ValueError:
            pass
        return self

    def emit(self, *args, **kwargs) -> None:
        for h in list(self._handlers):
            try:
                h(*args, **kwargs)
            except Exception:
                # Swallow handler exceptions to avoid breaking the loop
                pass


@dataclass
class MockRealTimeBar:
    time: Any  # datetime-like
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class MockHistoricalBar:
    date: Any  # datetime-like
    open: float
    high: float
    low: float
    close: float
    volume: float

    # Some code looks for `time` too; provide alias
    @property
    def time(self) -> Any:
        return self.date


class MockTicker:
    """Container that exposes `updateEvent` and a growing list of bars."""

    def __init__(self) -> None:
        self.updateEvent: Event = Event()
        self.bars: List[MockRealTimeBar] = []


class MockOrderStatus:
    def __init__(self) -> None:
        self.status: str = "Submitted"
        self.filled: float = 0.0
        self.remaining: float = 0.0
        self.avgFillPrice: float = 0.0


class MockExecution:
    def __init__(self, side: str, shares: float, price: float, time: Any = None) -> None:
        self.execId: str = uuid.uuid4().hex
        self.side: str = side  # 'BOT' or 'SLD'
        self.shares: float = shares
        self.price: float = price
        self.time: Any = time


class MockCommissionReport:
    def __init__(self, commission: float) -> None:
        self.commission: float = commission


@dataclass
class MockPortfolioItem:
    contract: Any
    position: float
    averageCost: float
    marketPrice: float
    marketValue: float
    unrealizedPNL: float
    realizedPNL: float
    account: str


class MockFill:
    def __init__(self, side: str, shares: float, price: float, commission: float, time: Any = None) -> None:
        self.execution = MockExecution(side=side, shares=shares, price=price, time=time)
        self.commissionReport = MockCommissionReport(commission=commission)


class MockTrade:
    def __init__(self, contract: Any, order: Any) -> None:
        self.contract = contract
        self.order = order
        self.orderStatus = MockOrderStatus()
        self.fills: List[MockFill] = []
        self.fillEvent: Event = Event()
        self.statusEvent: Event = Event()

    def isDone(self) -> bool:
        return self.orderStatus.status in {"Filled", "Cancelled", "ApiCancelled", "Inactive"}


class BacktestIB:
    """
    Minimal IB client mock. Delegates market state and fills to a `BacktestEngine`.
    Only implements methods used by strategies in this repo.
    """

    def __init__(self, engine: "BacktestEngine", broker: Any = None) -> None:
        self._engine = engine
        self._connected = True
        # Optional BacktestBroker to mirror order/fill records for UI
        self._broker = broker

    def isConnected(self) -> bool:
        return self._connected

    async def connectAsync(self, host: str, port: int, clientId: int):  # parity method, no-op
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    async def qualifyContractsAsync(self, contract: Any):  # strategies call this; no-op for backtests
        return

    async def reqHistoricalDataAsync(
        self,
        contract: Any,
        endDateTime: str,
        durationStr: str,
        barSizeSetting: str,
        whatToShow: str,
        useRTH: bool,
        keepUpToDate: bool,
    ) -> List[MockHistoricalBar]:
        return self._engine.build_historical_bars(contract, durationStr, barSizeSetting, useRTH)

    def reqRealTimeBars(self, contract: Any, barSize: int, whatToShow: str, useRTH: bool) -> MockTicker:
        ticker = MockTicker()
        self._engine.register_ticker(contract, ticker, barSize=barSize, useRTH=useRTH)
        return ticker

    def placeOrder(self, contract: Any, order: Any) -> MockTrade:
        trade = MockTrade(contract, order)
        # Enqueue order; engine will attempt fills on next bar step
        self._engine.submit_order(trade)
        # If a BacktestBroker is wired, mirror order and fills to its _backtest_data
        if getattr(self, "_broker", None) is not None and hasattr(self._broker, "_backtest_data"):
            try:
                # Record order immediately
                self._broker._backtest_data['orders'].append({
                    'timestamp': pd.Timestamp.now(),
                    'symbol': getattr(contract, 'symbol', ''),
                    'action': getattr(order, 'action', ''),
                    'quantity': getattr(order, 'totalQuantity', 0),
                    'order_type': getattr(order, 'orderType', ''),
                })
            except Exception:
                pass

            def _on_fill(tr, fill):
                try:
                    ts = pd.Timestamp(fill.execution.time) if hasattr(fill.execution, 'time') else pd.Timestamp.now()
                    qty = tr.orderStatus.filled
                    price = tr.orderStatus.avgFillPrice
                    action = tr.order.action
                    self._broker._backtest_data['fills'].append({
                        'timestamp': ts,
                        'symbol': tr.contract.symbol,
                        'action': action,
                        'quantity': qty,
                        'price': price,
                        'order_type': tr.order.orderType,
                        'entry_time': ts,
                        'entry_price': price,
                        'qty': qty,
                        'side': action,
                    })
                except Exception:
                    pass

            trade.fillEvent += _on_fill

        return trade

    # Optional: portfolio view if needed by other components during backtest
    def portfolio(self):
        return self._engine.build_portfolio_items()
