"""
Base Strategy class for IB Multi-Strategy ATS
Modernized version based on the old strategy template
"""
import asyncio
import threading
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ib_async import *
from core.log_manager import add_log
from utils.ib_connection import connect_to_ib, disconnect_from_ib
from broker.live_broker import LiveBroker
from broker.backtest_broker import BacktestBroker
import pandas as pd
from utils.ib_historical_downloader import download_ib_historical_paginated
from core.arctic_manager import get_ac

# Default base parameters used by all strategies. Import and extend in individual strategy files:
# from obj.base_strategy import PARAMS as BASE_PARAMS
# PARAMS = {**BASE_PARAMS, **{...overrides...}}
PARAMS = {
    
    "universe": "",  # single symbol or comma-separated list of symbols or arcticdb library, e.g. "us_stocks"
    "currency": "USD",               # strategy base currency for cash tracking

    # Allocation and rebalancing
    "min_weight": 0.0,               # lower bound of portfolio allocation for this strategy
    "max_weight": 1.0,               # upper bound of allocation
    "target_weight": 0.0,            # target allocation; used for rebalancing

    # Position sizing and risk caps
    "max_position_size": 1.0,        # cap as fraction of strategy equity for a single position
    "risk_per_trade": 0.01,          # fraction of strategy equity at risk per trade (for sizing)

    # Exits / risk management
    "stop_loss": 0.07,               # initial stop loss (fractional, e.g., 0.05 = 5%)
    "trailing_stop_loss": 0.20,      # trailing stop as override when profitable
    "profit_target": 0.35,             # close when profit >= take_profit (fractional)


}

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    Each strategy runs in its own thread with a unique clientId and isolated event loop.
    Strategies must implement the abstract methods to define their trading logic.

    **PARAMS Convention**
    Each strategy file should define a global dictionary named `PARAMS` at the module level.
    This dictionary holds the default parameters for the strategy.
    When a strategy is loaded, the `StrategyManager` will first check for parameters in
    ArcticDB. If not found, it will use the `PARAMS` dictionary from the file and
    persist them to the database for future runs.
    Example:
    ```
    # my_strategy.py
    PARAMS = {
        "sma_period": 20,
        "trade_size": 100
    }

    class MyStrategy(BaseStrategy):
        # ... strategy logic ...
    ```
    """
    
    def __init__(self, client_id: int, strategy_manager, params: Optional[Dict[str, Any]] = None, 
                 broker_type: str = "live", backtest_engine=None, strategy_symbol: Optional[str] = None):
        # Infer strategy_name and symbol from class name, but allow explicit override via strategy_symbol
        self.strategy_name = self.__class__.__name__
        inferred_symbol = self.strategy_name.replace("Strategy", "").upper()
        self.symbol = (strategy_symbol or inferred_symbol).upper()
        """
        Initialize the base strategy.

        Args:
            client_id: Unique IB client ID for this strategy.
            strategy_manager: Reference to the main StrategyManager.
            params: Dictionary of strategy parameters loaded by the StrategyManager.
            broker_type: Type of broker to use ('live' or 'backtest')
            backtest_engine: BacktestEngine instance (required if broker_type is 'backtest')
        """
        self.client_id = client_id
        self.strategy_manager = strategy_manager
        
        # Connection and state
        self.ib = None
        self.is_running = False
        self.is_connected = False
        
        # Parameters are provided by StrategyManager from ArcticDB or module PARAMS on first run.
        # BaseStrategy does not read from ArcticDB; if nothing was passed, fall back to module-level PARAMS.
        self.params = params if isinstance(params, dict) and params else dict(PARAMS)
        
        # All weights and other parameters are accessed from self.params (populated by StrategyManager).
        # Do not perform additional ArcticDB reads here; StrategyManager is the single source of params.
        # Universal parameters (safe defaults if absent)
        self.universe: str = str(self.params.get('universe') or '')
        self.currency: str = str(self.params.get('currency', 'USD'))
        self.max_position_size = self.params.get('max_position_size')
        self.risk_per_trade = self.params.get('risk_per_trade')
        self.stop_loss = self.params.get('stop_loss')
        self.trailing_stop_loss = self.params.get('trailing_stop_loss')
        self.profit_target = self.params.get('profit_target')
        
        # Broker initialization
        self.broker_type = broker_type
        self.broker = None
        self.backtest_engine = backtest_engine
        
        # Threading
        self.loop = None
        self.thread = None
        
        # add_log(f"Strategy '{self.strategy_name}' initialized for {self.symbol}", self.symbol)
    
    def on_bar(self, bars, hasNewBar: bool):
        """
        Optional hook to process bar updates.
        Live strategies typically subscribe via IB and receive callbacks.
        Backtests can call this method directly to drive the strategy logic.
        Default implementation is a no-op and can be overridden by subclasses.
        """
        return
    
    
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
        # add_log(f"Strategy thread started", self.symbol)
    
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
            # Connect to IB unless an IB instance has already been injected
            if not (self.ib and self.is_connected):
                if not await self.connect_to_ib():
                    add_log(f"Failed to connect to IB, strategy stopping", self.symbol, "ERROR")
                    return
            else:
                add_log(f"Using injected IB connection (no connect needed)", self.symbol)
            
            # Initialize broker after IB connection is established
            await self._initialize_broker()
            
            # Initialize strategy
            await self.initialize_strategy()
            # add_log(f"Strategy initialized successfully", self.symbol)
            
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
            # Wait for pending trades to complete before disconnecting
            if self.ib and self.is_connected:
                add_log(f"Waiting for pending trades to complete...", self.symbol)
                # Wait up to 300 seconds (5 minutes) for fills/cancels
                # This covers "AtClose" orders waiting for market close
                for _ in range(300):
                    pending = [t for t in self.ib.trades() if not t.isDone()]
                    if not pending:
                        break
                    await asyncio.sleep(1)
                
                # Log any trades still pending after timeout
                pending = [t for t in self.ib.trades() if not t.isDone()]
                if pending:
                    add_log(f"Disconnecting with {len(pending)} pending trades: {[t.contract.symbol for t in pending]}", self.symbol, "WARNING")

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
        
        # Notify strategy manager asynchronously via message queue
        if self.strategy_manager and hasattr(self.strategy_manager, "message_queue"):
            try:
                self.strategy_manager.message_queue.put({
                    "type": "fill",
                    "strategy": self.symbol,
                    "trade": trade,
                    "fill": fill,
                })
            except Exception as e:
                add_log(f"Failed to enqueue fill event: {e}", self.symbol, "ERROR")
    
    def on_status_change(self, trade: Trade):
        """
        Handle order status change events.
        Override in subclasses for custom status handling.
        """
        status = trade.orderStatus.status
        if "Pending" not in status:
            add_log(f"Order status: {status}", self.symbol)
            
            # Notify strategy manager asynchronously via message queue
            if self.strategy_manager and hasattr(self.strategy_manager, "message_queue"):
                try:
                    self.strategy_manager.message_queue.put({
                        "type": "status_change",
                        "strategy": self.symbol,
                        "trade": trade,
                        "status": status,
                    })
                except Exception as e:
                    add_log(f"Failed to enqueue status change: {e}", self.symbol, "ERROR")
    
    def update_params(self, new_params: Dict[str, Any]):
        """
        Update strategy parameters.
        
        Args:
            new_params: Dictionary of parameter updates
        """
        self.params.update(new_params)
        add_log(f"Parameters updated: {new_params}", self.symbol)

    # ---------------------------------------------------------------------
    # Broker wrappers and order entry
    # ---------------------------------------------------------------------
    async def get_total_equity(self) -> float:
        """
        Return total account equity in the IB account's BASE CURRENCY.
        
        Preferred: AccountSummary 'NetLiquidation' (currency given by IB -> treat as base).
        Fallback: Sum of 'EquityWithLoanValue' across currencies converted into base using FXCache.
        """
        try:
            if not (self.ib and self.is_connected):
                return 0.0
            # Preferred: AccountSummary NetLiquidation (capture base currency from entry)
            try:
                account_summary = await self.ib.accountSummaryAsync()
                netliq_entries = [e for e in account_summary if getattr(e, 'tag', None) == 'NetLiquidation']
                if netliq_entries:
                    # Pick the latest entry
                    nl = netliq_entries[-1]
                    return float(nl.value)
                # Fallback path below if NetLiquidation not available
                # Determine base currency from any EquityWithLoanValue entry if possible
                ewl_entries = [e for e in account_summary if getattr(e, 'tag', None) == 'EquityWithLoanValue']
                base = await self._get_base_currency()
                # Convert each currency's equity to base and sum
                if ewl_entries:
                    fx_cache = await self._get_fx_cache(base)
                    total_base = 0.0
                    for e in ewl_entries:
                        cur = getattr(e, 'currency', None) or base
                        val = float(e.value)
                        if cur != base and fx_cache:
                            try:
                                rate = await fx_cache.get_fx_rate(cur, base)
                                val = val / float(rate) if rate else val
                            except Exception:
                                pass
                        total_base += val
                    return float(total_base)
            except Exception:
                pass
            return 0.0
        except Exception as e:
            add_log(f"get_total_equity error: {e}", self.symbol, "ERROR")
            return 0.0

    async def get_equity(self) -> float:
        """
        Return equity allocated to this strategy.

        Priority:
        1) If IB account library has strategy_{symbol}_equity, use its latest value.
        2) Else, read target_weight from general/strategies and multiply by total equity.
        3) Final fallback: delegate to broker if available.
        """
        try:
            # 1) Account-specific strategy equity from ArcticDB
            ac = getattr(self.strategy_manager, 'ac', None) or get_ac()
            account_id = None
            try:
                accounts = self.ib.managedAccounts() if self.ib else []
                if accounts:
                    account_id = accounts[0]
            except Exception:
                account_id = None
            if ac and account_id:
                try:
                    lib = ac.get_library(account_id)
                    symbol_name = f"strategy_{self.symbol}_equity"
                    if lib and lib.has_symbol(symbol_name):
                        df = lib.read(symbol_name).data
                        if isinstance(df, pd.DataFrame) and not df.empty and 'equity' in df.columns:
                            return float(df['equity'].iloc[-1])
                except Exception:
                    pass

            # 2) Fallback: target_weight (from self.params) * total_equity
            try:
                target_weight = float(self.params.get('target_weight', 0.0) or 0.0)
                total_equity = await self.get_total_equity()
                return float((target_weight or 0.0) * (total_equity or 0.0))
            except Exception:
                pass

            # 3) Final fallback: broker delegation if present
            if self.broker and hasattr(self.broker, 'get_equity'):
                return float(await self.broker.get_equity())
            return 0.0
        except Exception as e:
            add_log(f"get_equity error: {e}", self.symbol, "ERROR")
            return 0.0

    async def calculate_quantity(self, contract: Contract, percent_of_equity: float) -> int:
        """Calculate integer share quantity from percent_of_equity and current price."""
        try:
            pct = max(0.0, float(percent_of_equity))
            # Enforce max_position_size cap if configured
            if self.max_position_size is not None:
                try:
                    pct = min(pct, float(self.max_position_size))
                except Exception:
                    pass
            equity = await self.get_equity()
            if equity <= 0:
                return 0
            price = None
            if self.ib and hasattr(self.ib, "reqTickersAsync"):
                ticks = await self.ib.reqTickersAsync(contract)
                if ticks and ticks[0].marketPrice():
                    price = float(ticks[0].marketPrice())
            if not price or price <= 0:
                return 0
            # Convert price to base currency if needed for proper sizing
            try:
                base = await self._get_base_currency()
                contract_ccy = getattr(contract, 'currency', None) or base
                if contract_ccy != base:
                    fx_cache = await self._get_fx_cache(base)
                    if fx_cache:
                        rate = await fx_cache.get_fx_rate(contract_ccy, base)
                        if rate:
                            price = price / float(rate)
            except Exception:
                pass
            quantity = int((equity * pct) / price)
            return max(0, quantity)
        except Exception as e:
            add_log(f"calculate_quantity error: {e}", self.symbol, "ERROR")
            return 0

    async def get_market_price(self, contract: Contract) -> Optional[float]:
        """Get current market price for a qualified contract."""
        try:
            if self.ib and hasattr(self.ib, 'reqTickersAsync'):
                ticks = await self.ib.reqTickersAsync(contract)
                if ticks and ticks[0].marketPrice():
                    return float(ticks[0].marketPrice())
        except Exception:
            pass
        return None

    async def place_order(
        self,
        contract: Contract,
        quantity: int,
        order_type: str = 'MKT',
        *,
        algo: bool = True,
        urgency: str = 'Patient',
        orderRef: Optional[str] = None,
        limit: Optional[float] = None,
        useRth: bool = False,
        tif: str = 'DAY',
        transmit: bool = True,
        parentId: int = 0,
    ) -> Optional[Trade]:
        """
        Place an order directly via IB similar to core.trade_manager.TradeManager.trade.

        - Qualifies the contract
        - Supports Market and Limit orders
        - Supports Adaptive algo with urgency: Patient (default), Normal, Urgent
        - Attaches fill and status event handlers which forward to StrategyManager via message_queue

        Args:
            contract: ib_async.Contract
            quantity: signed integer; >0 BUY, <0 SELL
            order_type: 'LMT', 'MKT', 'MOC'
            algo: use adaptive algo (ignored for MOC)
            urgency: 'Patient' | 'Normal' | 'Urgent'
            orderRef: optional order reference; defaults to strategy symbol
            limit: limit price required for LMT
            useRth: use regular trading hours
            tif: time in force (e.g. 'DAY', 'GTC')
            transmit: whether to transmit the order immediately (default True)
            parentId: ID of parent order for attached orders
        """
        try:
            if not self.ib:
                add_log("IB client not available", self.symbol, "ERROR")
                return None


            await self.ib.qualifyContractsAsync(contract)

            action = 'BUY' if quantity > 0 else 'SELL'
            totalQuantity = int(abs(quantity))

            if order_type == 'LMT':
                if limit is None:
                    raise ValueError("Limit price must be specified for limit orders.")
                order = LimitOrder(action, totalQuantity, float(limit))
            elif order_type == 'MKT':
                order = MarketOrder(action, totalQuantity)
            elif order_type == 'MOC':
                order = Order(orderType='MOC', action=action, totalQuantity=totalQuantity)
            else:
                raise ValueError(f"Unsupported order type: {order_type}")
            
            order.tif = tif
            order.transmit = transmit
            if parentId > 0:
                order.parentId = parentId

            if algo and order_type not in ['MOC']:
                order.algoStrategy = 'Adaptive'
                if urgency == 'Normal':
                    order.algoParams = [TagValue('adaptivePriority', 'Normal')]
                elif urgency == 'Urgent':
                    order.algoParams = [TagValue('adaptivePriority', 'Urgent')]
                else:
                    order.algoParams = [TagValue('adaptivePriority', 'Patient')]

            order.orderRef = orderRef or self.symbol
            order.useRth = useRth

            # Place order (sync call in ib_async)
            trade = self.ib.placeOrder(contract, order)
            await asyncio.sleep(1)

            # Post standardized 'order' message
            if self.strategy_manager and hasattr(self.strategy_manager, 'message_queue'):
                try:
                    self.strategy_manager.message_queue.put({
                        'type': 'order',
                        'strategy': self.symbol,
                        'trade': trade,
                        'contract': contract,
                        'order': order,
                        'info': 'sent from BaseStrategy.place_order'
                    })
                except Exception:
                    pass

            # Attach event handlers to forward to PortfolioManager via StrategyManager
            def _on_fill(tr: Trade, fill):
                try:
                    self.on_fill(tr, fill)
                except Exception:
                    pass

            def _on_status(tr: Trade):
                try:
                    self.on_status_change(tr)
                except Exception:
                    pass

            try:
                trade.fillEvent += _on_fill
                trade.statusEvent += _on_status
            except Exception:
                pass

            return trade
        except Exception as e:
            add_log(f"place_order failed: {e}", self.symbol, "ERROR")
            return None

    async def place_order_by_size(
        self,
        contract: Contract,
        size: float,
        side: str = 'BUY',
        order_type: str = 'MKT',
        *,
        limit: Optional[float] = None,
        algo: bool = True,
        urgency: str = 'Patient',
        useRth: bool = False,
    ) -> Optional[Trade]:
        """
        Convenience to place an order sized by fraction of allocated equity.
        Calculates quantity from current market price and calls place_order().
        """
        try:
            side = side.upper()
            if side not in {'BUY', 'SELL'}:
                raise ValueError("side must be 'BUY' or 'SELL'")
            await self.ib.qualifyContractsAsync(contract)
            price = await self.get_market_price(contract)
            if not price or price <= 0:
                add_log("No market price available to size order", self.symbol, "ERROR")
                return None
            # Enforce max_position_size cap
            pct = float(max(0.0, size))
            if self.max_position_size is not None:
                try:
                    pct = min(pct, float(self.max_position_size))
                except Exception:
                    pass
            equity = await self.get_equity()
            # Convert price to base if needed for sizing
            try:
                base = await self._get_base_currency()
                contract_ccy = getattr(contract, 'currency', None) or base
                if contract_ccy != base:
                    fx_cache = await self._get_fx_cache(base)
                    if fx_cache:
                        rate = await fx_cache.get_fx_rate(contract_ccy, base)
                        if rate:
                            price = price / float(rate)
            except Exception:
                pass
            qty = int((equity * pct) / price)
            if qty <= 0:
                add_log("Calculated quantity is 0; aborting order", self.symbol, "WARNING")
                return None
            signed_qty = qty if side == 'BUY' else -qty
            return await self.place_order(
                contract,
                quantity=signed_qty,
                order_type=order_type,
                algo=algo,
                urgency=urgency,
                orderRef=self.symbol,
                limit=limit,
                useRth=useRth,
            )
        except Exception as e:
            add_log(f"place_order_by_size error: {e}", self.symbol, "ERROR")
            return None

    
    async def _initialize_broker(self):
        """
        Initialize the appropriate broker based on broker_type.
        """
        try:
            # Get ArcticDB client from strategy manager if available
            arctic_client = None
            if hasattr(self.strategy_manager, 'ac'):
                arctic_client = self.strategy_manager.ac
            
            if self.broker_type == "backtest":
                if not self.backtest_engine:
                    raise ValueError("BacktestEngine required for backtest broker")
                self.broker = BacktestBroker(
                    engine=self.backtest_engine,
                    strategy_symbol=self.symbol,
                    arctic_client=arctic_client
                )
                
            else:
                # Default to live broker
                if not self.ib:
                    raise ValueError("IB connection required for live broker")
                self.broker = LiveBroker(
                    ib_client=self.ib,
                    strategy_symbol=self.symbol,
                    arctic_client=arctic_client
                )
                
        except Exception as e:
            add_log(f"Error initializing broker: {e}", self.symbol, "ERROR")
            raise
    
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
            "params": self.params,
            "broker_type": self.broker_type
        }

    # ---------------------------------------------------------------------
    # Market data helpers (ArcticDB + IB fallback)
    # ---------------------------------------------------------------------
    def _normalize_timeframe(self, timeframe: str) -> str:
        """Normalize timeframe aliases to ArcticDB symbol suffix (e.g., '1_min', '1_day')."""
        tf = (timeframe or '').strip().lower().replace(' ', '').replace('-', '_')
        if tf in {"1m", "1min", "minute", "1_min"}:
            return "1_min"
        if tf in {"1h", "60m", "hour", "hourly", "1_hour"}:
            return "1_hour"
        if tf in {"1d", "day", "daily", "1_day"}:
            return "1_day"
        return "1_min"

    def get_universe_symbols(self) -> list:
        """Resolve the strategy universe into a list of ticker symbols."""
        uni = (self.universe or self.params.get('universe') or '').strip()
        if not uni:
            # default to strategy symbol
            return [self.symbol]
        # comma-separated list
        if ',' in uni:
            return [s.strip().upper() for s in uni.split(',') if s.strip()]
        # single token: assume it's a symbol for now
        return [uni.upper()]

    async def download_data(
        self,
        symbol: str,
        timeframe: str = '1_min',
        start_date: str = 'max',
        end_date: str = 'today',
        *,
        use_rth: bool = True,
        what_to_show: str = 'TRADES',
        client_id: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Download historical bars from IB using the paginated downloader with full lookback by default.
        Writes the result into ArcticDB global 'market_data' library using symbol naming '{TICKER}_{TF}'.
        """
        tf_norm = self._normalize_timeframe(timeframe)

        def _progress_cb(pct: float, msg: str):
            try:
                add_log(f"[DL {symbol}] {pct:.1f}% {msg}", self.symbol)
            except Exception:
                pass

        df = await download_ib_historical_paginated(
            symbol=symbol,
            interval={"1_min": "minute", "1_hour": "hour", "1_day": "day"}.get(tf_norm, "minute"),
            start_date=start_date,
            end_date=end_date,
            use_rth=use_rth,
            what_to_show=what_to_show,
            chunk=None,
            client_id=(client_id if client_id is not None else max(9999, self.client_id + 10)),
            progress_cb=_progress_cb,
        )

        try:
            ac = getattr(self.strategy_manager, 'ac', None) or get_ac()
            lib = ac.get_library('market_data')
            sym_name = f"{symbol.upper()}_{tf_norm}"
            if not df.empty:
                lib.write(sym_name, df)
                add_log(f"Saved {len(df)} rows to market_data/{sym_name}", self.symbol)
        except Exception as e:
            add_log(f"ArcticDB write failed for {symbol}: {e}", self.symbol, "ERROR")
        return df

    async def get_data(
        self,
        symbols: Optional[list] = None,
        timeframe: str = '1_min',
        start_date: str = 'max',
        end_date: str = 'today',
        *,
        use_rth: bool = True,
        what_to_show: str = 'TRADES',
        force_download: bool = False,
    ) -> Any:
        """
        Retrieve market data for the given symbols/timeframe from ArcticDB.
        If missing or force_download=True, download from IB (full lookback by default) and persist.

        Returns a single DataFrame for one symbol or a dict[symbol]->DataFrame for multiple.
        """
        tf_norm = self._normalize_timeframe(timeframe)
        tickers = symbols or self.get_universe_symbols()
        ac = getattr(self.strategy_manager, 'ac', None) or get_ac()
        lib = ac.get_library('market_data')
        out: Dict[str, pd.DataFrame] = {}

        for sym in tickers:
            sym_name = f"{sym.upper()}_{tf_norm}"
            df = None
            try:
                if not force_download and lib.has_symbol(sym_name):
                    df = lib.read(sym_name).data
            except Exception:
                df = None
            if df is None or force_download or (isinstance(df, pd.DataFrame) and df.empty):
                df = await self.download_data(
                    symbol=sym,
                    timeframe=tf_norm,
                    start_date=start_date,
                    end_date=end_date,
                    use_rth=use_rth,
                    what_to_show=what_to_show,
                )
            out[sym.upper()] = df if isinstance(df, pd.DataFrame) else pd.DataFrame()

        if len(out) == 1:
            return next(iter(out.values()))
        return out

    async def get_positions(self) -> list:
        """Return current IB positions list (live)."""
        try:
            if self.ib and hasattr(self.ib, 'positions'):
                return self.ib.positions() or []
        except Exception:
            pass
        return []

    async def _get_base_currency(self) -> str:
        """Get the base currency from PortfolioManager (single source of truth)."""
        try:
            if (self.strategy_manager and 
                self.strategy_manager.portfolio_manager and 
                hasattr(self.strategy_manager.portfolio_manager, 'base_currency')):
                return self.strategy_manager.portfolio_manager.base_currency
        except Exception:
            pass
        # Default fallback if PortfolioManager not initialized yet
        return 'USD'

    async def _get_fx_cache(self, base_currency: str):
        """Get the shared FX cache from PortfolioManager, initializing if needed."""
        try:
            if not self.strategy_manager or not self.strategy_manager.portfolio_manager:
                return None
            
            portfolio_manager = self.strategy_manager.portfolio_manager
            
            # Initialize FX cache if it doesn't exist
            if portfolio_manager.fx_cache is None:
                from utils.fx_cache import FXCache
                portfolio_manager.fx_cache = FXCache(self.ib, base_currency)
            
            return portfolio_manager.fx_cache
        except Exception as e:
            add_log(f"Error getting FX cache: {e}", self.symbol, "ERROR")
            return None
