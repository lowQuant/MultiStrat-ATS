"""
Live Broker implementation using ib_async.

Provides live trading capabilities through Interactive Brokers,
with ArcticDB integration for equity management.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import pandas as pd
import asyncio
from ib_async import IB, Contract, Order, Trade, Position, MarketOrder, Fill, OrderStatus

from .base_broker import Broker
from core.log_manager import add_log
from core.arctic_manager import get_ac

class LiveBroker(Broker):
    """
    A broker implementation that connects to Interactive Brokers for live trading.
    Inherits equity management logic from the base Broker class.
    """

    def __init__(self, ib_client: IB, strategy_symbol: str, arctic_client=None):
        """
        Initializes the LiveBroker.

        Args:
            ib_client: An authenticated and connected ib_async.IB instance.
            strategy_symbol: The symbol of the strategy using this broker.
            arctic_client: Optional ArcticDB client for data access.
        """
        # Initialize base class with strategy symbol and Arctic client
        arctic_client = arctic_client or get_ac()
        super().__init__(strategy_symbol, arctic_client)
        
        self.ib = ib_client
        self.account_id = None
        self._account_library = None
        
        # NOTE: We do NOT subscribe to events here to avoid duplication
        # Events are handled by base_strategy and forwarded via message_queue
        
        # Initialize account ID and library
        asyncio.create_task(self._initialize_account())

    async def _initialize_account(self):
        """Initialize account ID and create account library if needed."""
        try:
            # Get managed accounts
            accounts = self.ib.managedAccounts()
            if accounts:
                self.account_id = accounts[0]
                # Account ID logged only on first connection, not per strategy
                
                # Create account library if it doesn't exist
                if self.arctic_client and self.account_id:
                    from arcticdb import LibraryOptions
                    library_options = LibraryOptions(dynamic_schema=True)
                    
                    if self.account_id not in self.arctic_client.list_libraries():
                        self._account_library = self.arctic_client.get_library(
                            self.account_id,
                            create_if_missing=True,
                            library_options=library_options
                        )
                        add_log(f"Created account library: {self.account_id}", self.strategy_symbol)
                    else:
                        self._account_library = self.arctic_client.get_library(self.account_id)
                        
                    # Initialize required symbols in account library
                    await self._initialize_account_symbols()
        except Exception as e:
            add_log(f"Error initializing account: {e}", self.strategy_symbol, "ERROR")
    
    async def _initialize_account_symbols(self):
        """Initialize required symbols in the account library."""
        if not self._account_library:
            return
            
        symbols_to_init = [
            'account_summary', 'portfolio', 'orders', 'fills',
            f'strategy_{self.strategy_symbol}'
        ]
        
        for symbol in symbols_to_init:
            try:
                if not self._account_library.has_symbol(symbol):
                    # Initialize with empty DataFrame
                    if symbol == 'account_summary':
                        df = pd.DataFrame(columns=['equity', 'pnl', 'cash', 'market_value'])
                    elif symbol == 'portfolio':
                        df = pd.DataFrame(columns=['symbol', 'position', 'average_cost', 'market_price', 'market_value'])
                    elif symbol in ['orders', 'fills']:
                        df = pd.DataFrame()
                    else:
                        df = pd.DataFrame()
                    
                    # Write initial empty DataFrame
                    self._account_library.write(symbol, df)
                    add_log(f"Initialized symbol: {symbol} in {self.account_id}", self.strategy_symbol)
            except Exception as e:
                add_log(f"Error initializing symbol {symbol}: {e}", self.strategy_symbol, "WARNING")
    
    async def _get_strategy_equity_from_arctic(self) -> Optional[float]:
        """Override to read from account-specific library."""
        # TODO: when is this used? where is the difference to same method in base_broker?
        #       is this used at all?
        # if so, we need to do the query more efficiently, else it might take too long.
        
        if not self._account_library:
            return None
            
        try:
            symbol = f'strategy_{self.strategy_symbol}'
            if self._account_library.has_symbol(symbol):
                data = self._account_library.read(symbol).data
                if isinstance(data, pd.DataFrame) and not data.empty and 'equity' in data.columns:
                    return float(data['equity'].iloc[-1])
        except Exception as e:
            add_log(f"Error reading strategy equity: {e}", self.strategy_symbol, "WARNING")
        return None
    
    async def _get_total_equity(self) -> float:
        """
        Implementation-specific method to get total account equity from IB.
        This is used by the base class equity calculation logic.
        
        Returns:
            Total account equity (NetLiquidation value)
        """
        try:
            account_values = await self.ib.accountValuesAsync()
            for av in account_values:
                if av.tag == 'NetLiquidation' and av.currency == 'USD':
                    return float(av.value)
            add_log(f"Could not find 'NetLiquidation' in USD for {self.strategy_symbol}", self.strategy_symbol, "WARNING")
            return 0.0
        except Exception as e:
            add_log(f"Error getting total equity for {self.strategy_symbol}: {e}", self.strategy_symbol, "ERROR")
            return 0.0

    async def place_order(
        self, 
        contract: Contract, 
        order: Order, 
        size: float, 
        stop_price: Optional[float] = None
    ) -> Optional[Trade]:
        """
        Places an order, calculating quantity based on a percentage of equity.
        
        Note: The 'size' parameter is used to calculate the order quantity.
        For a simple market order, it's based on a percentage of total equity.
        For more complex orders, this logic may need to be adapted.
        """
        try:
            # Use the base class get_equity() which handles strategy-specific allocation
            equity = await self.get_equity()
            if equity <= 0:
                add_log("Cannot place order with zero or negative equity.", self.strategy_symbol, "ERROR")
                return None

            # Get the current price to estimate quantity
            tickers = await self.ib.reqTickersAsync(contract)
            if not tickers or not tickers[0].marketPrice():
                add_log(f"Could not get market price for {contract.symbol} to calculate quantity.", self.strategy_symbol, "ERROR")
                return None

            current_price = tickers[0].marketPrice()
            
            # Calculate quantity based on size (percentage of equity)
            dollar_amount = equity * size
            quantity = int(dollar_amount / current_price)

            if quantity <= 0:
                add_log(f"Calculated quantity is {quantity}. Order not placed.", self.strategy_symbol, "WARNING")
                return None

            order.totalQuantity = quantity

            # If it's a stop order, set the stop price
            if stop_price is not None and order.orderType in ['STP', 'STP LMT']:
                order.auxPrice = stop_price

            add_log(f"Placing order: {order.action} {order.totalQuantity} {contract.symbol}", self.strategy_symbol)
            trade = self.ib.placeOrder(contract, order)
            
            # Order persistence will happen via event flow:
            # IB event → base_strategy.on_status_change → message_queue → portfolio_manager
            
            return trade
        except Exception as e:
            add_log(f"Error placing order for {self.strategy_symbol}: {e}", self.strategy_symbol, "ERROR")
            return None

    async def get_positions(self) -> List[Position]:
        """
        Retrieves a list of all current positions for the account.
        """
        try:
            # ib_async exposes synchronous positions(); wrap in immediate return for async method
            positions = self.ib.positions()
            return positions or []
        except Exception as e:
            add_log(f"Error getting positions for {self.strategy_symbol}: {e}", self.strategy_symbol, "ERROR")
            return []
    
    # Event handlers removed - handled by base_strategy to avoid duplication
    # Persistence methods below can be called by portfolio_manager when needed
    
    async def _persist_order(self, trade: Trade):
        """Persist order to ArcticDB."""
        if not self._account_library or not trade:
            return
            
        try:
            # Create order record
            order_data = {
                'timestamp': pd.Timestamp.now(),
                'order_id': trade.order.orderId,
                'strategy_symbol': self.strategy_symbol,
                'symbol': trade.contract.symbol,
                'action': trade.order.action,
                'quantity': trade.order.totalQuantity,
                'order_type': trade.order.orderType,
                'status': trade.orderStatus.status if trade.orderStatus else 'Submitted'
            }
            
            # Append to orders symbol
            new_df = pd.DataFrame([order_data])
            if self._account_library.has_symbol('orders'):
                existing = self._account_library.read('orders').data
                updated = pd.concat([existing, new_df], ignore_index=True)
                # Use write instead of update to avoid index issues
                self._account_library.write('orders', updated)
            else:
                self._account_library.write('orders', new_df)
                
            add_log(f"Persisted order {trade.order.orderId} to ArcticDB", self.strategy_symbol)
        except Exception as e:
            add_log(f"Error persisting order: {e}", self.strategy_symbol, "ERROR")
    
    async def _persist_order_status(self, trade: Trade):
        """Update order status in ArcticDB."""
        if not self._account_library or not trade:
            return
            
        try:
            if self._account_library.has_symbol('orders'):
                df = self._account_library.read('orders').data
                # Update status for this order
                mask = df['order_id'] == trade.order.orderId
                if mask.any():
                    df.loc[mask, 'status'] = trade.orderStatus.status
                    df.loc[mask, 'timestamp'] = pd.Timestamp.now()
                    # Use write instead of update to avoid index issues
                    self._account_library.write('orders', df)
        except Exception as e:
            add_log(f"Error updating order status: {e}", self.strategy_symbol, "WARNING")
    
    async def _persist_fill(self, trade: Trade, fill: Fill):
        """Persist fill to ArcticDB."""
        if not self._account_library or not fill:
            return
            
        try:
            # Create fill record
            fill_data = {
                'timestamp': pd.Timestamp(fill.time),
                'fill_id': f"{trade.order.orderId}_{fill.execution.execId}",
                'order_id': trade.order.orderId,
                'strategy_symbol': self.strategy_symbol,
                'symbol': fill.contract.symbol,
                'action': fill.execution.side,
                'quantity': fill.execution.shares,
                'price': fill.execution.price
            }
            
            # Append to fills symbol
            new_df = pd.DataFrame([fill_data])
            if self._account_library.has_symbol('fills'):
                existing = self._account_library.read('fills').data
                updated = pd.concat([existing, new_df], ignore_index=True)
                # Use write instead of update to avoid index issues
                self._account_library.write('fills', updated)
            else:
                self._account_library.write('fills', new_df)
                
            add_log(f"Persisted fill for order {trade.order.orderId} to ArcticDB", self.strategy_symbol)
            
            # Update strategy positions
            await self._update_strategy_positions()
        except Exception as e:
            add_log(f"Error persisting fill: {e}", self.strategy_symbol, "ERROR")
    
    async def _update_strategy_positions(self):
        """Update strategy positions in ArcticDB."""
        if not self._account_library:
            return
            
        try:
            # Get current positions
            positions = await self.get_positions()
            
            # Create position data
            position_data = {}
            for pos in positions:
                if pos.position != 0:  # Only include non-zero positions
                    position_data[pos.contract.symbol] = {
                        'position': pos.position,
                        'average_cost': pos.avgCost,
                        'market_value': pos.position * pos.avgCost  # Will be updated with market price
                    }
            
            # Create DataFrame with timestamp index
            df = pd.DataFrame(position_data).T
            df['timestamp'] = pd.Timestamp.now()
            df = df.set_index('timestamp')
            
            # Append to strategy positions
            symbol = f'strategy_{self.strategy_symbol}_positions'
            if self._account_library.has_symbol(symbol):
                existing = self._account_library.read(symbol).data
                updated = pd.concat([existing, df])
                # Use write instead of update to avoid index issues
                self._account_library.write(symbol, updated)
            else:
                self._account_library.write(symbol, df)
                
        except Exception as e:
            add_log(f"Error updating strategy positions: {e}", self.strategy_symbol, "WARNING")
