"""
Backtest Broker implementation.

Provides simulated trading capabilities for backtesting,
with ArcticDB integration for equity management.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import pandas as pd
import asyncio
from ib_async import Contract, Order, Trade, Position

from .base_broker import Broker
from backtest.backtest_engine import BacktestEngine
from backtest.mock_ib import MockTrade
from core.log_manager import add_log
from core.arctic_manager import get_ac

class BacktestBroker(Broker):
    """
    A broker implementation that simulates trades using the BacktestEngine.
    Inherits equity management logic from the base Broker class.
    """

    def __init__(self, engine: BacktestEngine, strategy_symbol: str, arctic_client=None, backtest_name=None):
        """
        Initializes the BacktestBroker.

        Args:
            engine: The backtesting engine instance.
            strategy_symbol: The symbol of the strategy using this broker.
            arctic_client: Optional ArcticDB client for data access.
            backtest_name: Name for the backtest run (defaults to strategy_{date})
        """
        # Initialize base class with strategy symbol and Arctic client
        arctic_client = arctic_client or get_ac()
        super().__init__(strategy_symbol, arctic_client)
        
        self.engine = engine
        
        # Generate backtest name for the backtests library
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if backtest_name:
            self.backtest_name = backtest_name
        else:
            self.backtest_name = f"{strategy_symbol}_{timestamp}"
        
        # For backtests, we use the 'backtests' library, not account libraries
        self._backtests_library = None
        self._backtest_data = {
            'equity_curve': [],
            'trades': [],
            'positions': [],
            'orders': [],
            'fills': []
        }
        
        # Initialize backtests library
        asyncio.create_task(self._initialize_backtest())

    async def _initialize_backtest(self):
        """Initialize backtests library."""
        try:
            if self.arctic_client:
                from arcticdb import LibraryOptions
                library_options = LibraryOptions(dynamic_schema=True)
                
                # Use the global 'backtests' library
                if 'backtests' not in self.arctic_client.list_libraries():
                    self._backtests_library = self.arctic_client.get_library(
                        'backtests',
                        create_if_missing=True,
                        library_options=library_options
                    )
                    add_log(f"Created backtests library", self.strategy_symbol)
                else:
                    self._backtests_library = self.arctic_client.get_library('backtests')
                    
                add_log(f"Initialized backtest: {self.backtest_name}", self.strategy_symbol)
        except Exception as e:
            add_log(f"Error initializing backtest: {e}", self.strategy_symbol, "ERROR")
    
    def save_backtest_results(self):
        """Save backtest results to the backtests library."""
        if not self._backtests_library:
            return
            
        try:
            # Save equity curve
            if self._backtest_data['equity_curve']:
                equity_df = pd.DataFrame(self._backtest_data['equity_curve'])
                symbol = f"{self.backtest_name}_equity"
                self._backtests_library.write(symbol, equity_df)
                add_log(f"Saved equity curve: {symbol}", self.strategy_symbol)
            
            # Save trades
            if self._backtest_data['trades']:
                trades_df = pd.DataFrame(self._backtest_data['trades'])
                symbol = f"{self.backtest_name}_trades"
                self._backtests_library.write(symbol, trades_df)
                add_log(f"Saved trades: {symbol}", self.strategy_symbol)
            
            # Save final positions
            if self._backtest_data['positions']:
                positions_df = pd.DataFrame(self._backtest_data['positions'])
                symbol = f"{self.backtest_name}_positions"
                self._backtests_library.write(symbol, positions_df)
                add_log(f"Saved positions: {symbol}", self.strategy_symbol)
            
            # Calculate and save metrics
            metrics = self._calculate_backtest_metrics()
            metrics_df = pd.DataFrame([metrics])
            symbol = f"{self.backtest_name}_metrics"
            self._backtests_library.write(symbol, metrics_df)
            add_log(f"Saved metrics: {symbol}", self.strategy_symbol)
            
        except Exception as e:
            add_log(f"Error saving backtest results: {e}", self.strategy_symbol, "ERROR")
    
    def _calculate_backtest_metrics(self) -> dict:
        """Calculate backtest performance metrics."""
        metrics = {
            'backtest_name': self.backtest_name,
            'strategy': self.strategy_symbol,
            'start_date': datetime.now(),  # Would be set at start
            'end_date': datetime.now(),
            'total_trades': len(self._backtest_data['trades']),
            'total_orders': len(self._backtest_data['orders']),
            'total_fills': len(self._backtest_data['fills']),
            'final_equity': self.engine.equity() if self.engine else 0,
            # Add more metrics as needed: Sharpe, max drawdown, etc.
        }
        return metrics
    
    async def _get_strategy_equity_from_arctic(self) -> Optional[float]:
        """Override for backtest - we don't use explicit equity in backtests."""
        # In backtests, equity is managed by the engine
        return None
    
    async def _get_total_equity(self) -> float:
        """
        Implementation-specific method to get total portfolio equity from backtest engine.
        This is used by the base class equity calculation logic.
        
        Returns:
            Total simulated portfolio equity
        """
        return self.engine.equity()

    async def place_order(
        self, 
        contract: Contract, 
        order: Order, 
        size: float, 
        stop_price: Optional[float] = None
    ) -> Optional[Trade]:
        """
        Places a simulated order with the backtest engine.
        """
        try:
            # Determine quantity: if strategy provided a quantity (>0), respect it; otherwise size-based.
            provided_qty = float(getattr(order, 'totalQuantity', 0) or 0)
            if provided_qty > 0:
                quantity = int(provided_qty)
            else:
                # Use the base class get_equity() which handles strategy-specific allocation
                equity = await self.get_equity()
                if equity <= 0:
                    add_log("Cannot place order with zero or negative equity.", self.strategy_symbol, "ERROR")
                    return None
                current_price = self.engine._last_price.get(contract.symbol)
                if not current_price:
                    add_log(f"Could not get last price for {contract.symbol} to calculate quantity.", self.strategy_symbol, "ERROR")
                    return None
                dollar_amount = equity * size
                quantity = int(dollar_amount / current_price)
                if quantity <= 0:
                    add_log(f"Calculated quantity is {quantity}. Order not placed.", self.strategy_symbol, "WARNING")
                    return None
                order.totalQuantity = quantity

            if stop_price is not None and order.orderType in ['STP', 'STP LMT']:
                order.auxPrice = stop_price

            # Create a mock trade object for the engine
            trade = MockTrade(contract, order)
            
            self.engine.submit_order(trade)
            add_log(f"[Backtest] Placed order: {order.action} {order.totalQuantity} {contract.symbol}", self.strategy_symbol)
            
            # Record order for backtest results
            self._backtest_data['orders'].append({
                'timestamp': pd.Timestamp.now(),
                'symbol': contract.symbol,
                'action': order.action,
                'quantity': order.totalQuantity,
                'order_type': order.orderType
            })
            
            # Register event listeners to capture fills when engine processes the next bar
            def _on_fill(tr, fill):
                try:
                    ts = pd.Timestamp(fill.execution.time) if hasattr(fill.execution, 'time') else pd.Timestamp.now()
                    qty = tr.orderStatus.filled
                    price = tr.orderStatus.avgFillPrice
                    action = tr.order.action
                    add_log(f"[Backtest] Filled: {action} {qty} {tr.contract.symbol} @ {price}", self.strategy_symbol)
                    # Store both generic and UI-expected fields
                    self._backtest_data['fills'].append({
                        'timestamp': ts,
                        'symbol': tr.contract.symbol,
                        'action': action,
                        'quantity': qty,
                        'price': price,
                        'order_type': tr.order.orderType,
                        # Fields expected by /backtest/trades consumer
                        'entry_time': ts,
                        'entry_price': price,
                        'qty': qty,
                        'side': action,  # UI accepts string; can be 'BUY'/'SELL'
                    })
                except Exception:
                    pass

            def _on_status(tr):
                # Optional: could record status transitions here if desired
                return

            trade.fillEvent += _on_fill
            trade.statusEvent += _on_status

            return trade

        except Exception as e:
            add_log(f"Error placing backtest order for {self.strategy_symbol}: {e}", self.strategy_symbol, "ERROR")
            return None

    async def get_positions(self) -> List[Position]:
        """
        Retrieves simulated positions from the backtest engine.
        """
        portfolio_items = self.engine.build_portfolio_items()
        positions = []
        for item in portfolio_items:
            pos = Position(
                account=item.account,
                contract=item.contract,
                position=item.position,
                avgCost=item.averageCost
            )
            positions.append(pos)
        return positions
    
    def record_trade(self, symbol: str, action: str, quantity: int, price: float, pnl: float = 0):
        """Record a completed trade for backtest results."""
        self._backtest_data['trades'].append({
            'timestamp': pd.Timestamp.now(),
            'symbol': symbol,
            'action': action,
            'quantity': quantity,
            'price': price,
            'pnl': pnl
        })
    
    def record_position_snapshot(self):
        """Record current positions snapshot."""
        positions = self.engine.build_portfolio_items() if self.engine else []
        snapshot = []
        for item in positions:
            snapshot.append({
                'symbol': item.contract.symbol,
                'position': item.position,
                'avg_cost': item.averageCost,
                'market_value': item.marketValue
            })
        if snapshot:
            self._backtest_data['positions'].append({
                'timestamp': pd.Timestamp.now(),
                'positions': snapshot
            })
