import asyncio
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
from ib_async import Contract, Stock, LimitOrder
from obj.base_strategy import BaseStrategy, PARAMS as BASE_PARAMS
from core.log_manager import add_log
from core.arctic_manager import get_ac

# -----------------------------------------------------------------------------
# Strategy Parameters
# -----------------------------------------------------------------------------
PARAMS = {
    **BASE_PARAMS,
    "universe": "us_equities",
    
    # Strategy Specific
    "multiplier": 2.5,           # Limit Price multiplier
    "decline_days": 4,           # Number of consecutive decline days
    
    # Risk / Allocation
    "max_trade_percent_equity": 0.05, # Max allocation per trade
}

class FourDayDeclineStrategy(BaseStrategy):
    """
    Implementation of the 4-Day Decline Limit Order Strategy.
    
    Live Execution Logic:
    1. Reads 'ALL_STOCKS' from ArcticDB (containing the last ~5 days of history).
    2. Identifies the 'Setup Day' (the most recent date in the data).
    3. Checks if the Setup Day completes a 4-day decline streak and meets the EMA condition.
    4. If a signal is found on the Setup Day, calculates the Limit Price based on that day's Close.
    5. Places a LIVE Limit Order for the *next* trading session (or current if pre-market).
    """
    
    def __init__(self, client_id: int, strategy_manager, params: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(client_id=client_id, strategy_manager=strategy_manager, params=params, **kwargs)
        
    async def initialize_strategy(self):
        pass        

import pytz
from datetime import datetime, time

# ... (previous imports)

class FourDayDeclineStrategy(BaseStrategy):
    """
    Implementation of the 4-Day Decline Limit Order Strategy.
    
    Live Execution Logic:
    1. Reads 'ALL_STOCKS' from ArcticDB (containing the last ~5 days of history).
    2. Identifies the 'Setup Day' (the most recent date in the data).
    3. Checks if the Setup Day completes a 4-day decline streak and meets the EMA condition.
    4. If a signal is found on the Setup Day, calculates the Limit Price based on that day's Close.
    5. Places a LIVE Limit Order for the *next* trading session (or current if pre-market).
    6. Monitors for End-of-Day (15:55 ET) to close all positions.
    """
    
    def __init__(self, client_id: int, strategy_manager, params: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(client_id=client_id, strategy_manager=strategy_manager, params=params, **kwargs)
        
    async def initialize_strategy(self):
        pass        

    async def run_strategy(self):
        try:
            # 1. Entry Logic: Scan and Place Orders
            await self.scan_and_place_orders()
            
            # 2. Monitoring Loop for EOD Exit
            add_log("Entry phase complete. Monitoring for EOD exit (15:55 ET)...", self.symbol)
            
            ny_tz = pytz.timezone('America/New_York')
            
            while self.is_running:
                now_ny = datetime.now(ny_tz)
                
                # Check for EOD (15:55 - 16:00)
                if now_ny.time() >= time(15, 55) and now_ny.time() < time(20, 0): # extended check window
                    add_log(f"End of Day detected ({now_ny.strftime('%H:%M')} ET). Closing all positions.", self.symbol)
                    await self.close_all_positions()
                    add_log("Strategy completed for the day.", self.symbol)
                    break
                
                await asyncio.sleep(60)
                
        except Exception as e:
            add_log(f"Strategy run error: {e}", self.symbol, "ERROR")
            import traceback
            add_log(traceback.format_exc(), self.symbol, "ERROR")

    async def scan_and_place_orders(self):
        """
        Execute the daily scan and order placement logic.
        """
        try:
            # 1. Load ALL_STOCKS
            add_log("Reading ALL_STOCKS from ArcticDB...", self.symbol)
            ac = get_ac()
            lib = ac.get_library("us_equities")
            if not lib.has_symbol("ALL_STOCKS"):
                add_log("ALL_STOCKS not found in us_equities.", self.symbol, "ERROR")
                return
                
            df = lib.read("ALL_STOCKS").data
            add_log(f"Loaded data with shape {df.shape}", self.symbol)
            
            # 2. Process Data & Generate Signals
            signals = self._generate_signals(df)
            
            add_log(f"Found {len(signals)} signals for today.", self.symbol)
            
            if signals.empty:
                return

            # 3. Execute Trades
            # We execute concurrently to speed up order placement
            # Get Equity ONCE to avoid spamming IB accountSummary
            equity = await self.get_equity()
            if equity <= 0:
                add_log("Equity not found or zero, using default 100k for sizing", self.symbol, "WARNING")
                equity = 100000.0

            add_log(f"Executing orders with Strategy Equity: {equity}", self.symbol)

            # ---------------------------------------------------------
            # Check for active orders/positions to prevent duplicates
            # ---------------------------------------------------------
            active_symbols = set()
            
            # 1. Check Open Trades (Pending Orders)
            if self.ib:
                # openTrades() returns list of active Trade objects (Order + Contract + Status)
                # If openTrades is not available, we might need to rely on local tracking or portfolio
                try:
                    open_trades = self.ib.openTrades()
                    for t in open_trades:
                        # Check if order belongs to this strategy (by orderRef)
                        if t.order.orderRef == self.symbol:
                            active_symbols.add(t.contract.symbol)
                            add_log(f"Found open order for {t.contract.symbol}, skipping new entry.", self.symbol)
                except Exception as e:
                     add_log(f"Could not check open trades: {e}", self.symbol, "WARNING")

            # 2. Check Active Positions (Held)
            if self.strategy_manager and self.strategy_manager.portfolio_manager:
                try:
                    current_positions = await self.strategy_manager.portfolio_manager.get_strategy_positions(
                        self.symbol, current_only=True, exclude_equity=True
                    )
                    if not current_positions.empty:
                        for _, pos in current_positions.iterrows():
                            # Ensure quantity is not zero
                            if float(pos['quantity']) != 0:
                                active_symbols.add(pos['symbol'])
                                add_log(f"Found existing position in {pos['symbol']}, skipping new entry.", self.symbol)
                except Exception as e:
                    add_log(f"Could not check positions: {e}", self.symbol, "WARNING")

            tasks = []
            for symbol, row in signals.iterrows():
                # Skip if already active
                if symbol in active_symbols:
                    continue

                limit_price = row['Limit_Price_Target']
                close_price = row['Close']
                
                # Calculate Quantity Locally
                # target_amount = equity * allocation_pct
                target_amount = equity * self.params['max_trade_percent_equity']
                
                quantity = 0
                if close_price > 0 and not np.isnan(close_price) and not np.isnan(target_amount):
                    quantity = int(target_amount / close_price)
                
                if quantity > 0:
                    tasks.append(self._execute_order(symbol, limit_price, quantity))
                else:
                    add_log(f"Skipping {symbol}: Quantity 0 (Close={close_price})", self.symbol, "WARNING")
            
            # Execute in chunks of 30 to be safe with rate limits
            chunk_size = 30
            for i in range(0, len(tasks), chunk_size):
                chunk = tasks[i:i+chunk_size]
                await asyncio.gather(*chunk)
                await asyncio.sleep(0.5)
                
        except Exception as e:
            add_log(f"Scan and place orders error: {e}", self.symbol, "ERROR")
            raise

    async def close_all_positions(self):
        """
        Cancel open orders and close all held positions (Market On Close / Market).
        """
        try:
            # 1. Cancel all open orders for this strategy
            if self.ib:
                open_orders = self.ib.openOrders()
                for order in open_orders:
                    if order.orderRef == self.symbol:
                        self.ib.cancelOrder(order)
                add_log("Cancelled all open orders.", self.symbol)
            
            # 2. Get current positions from PortfolioManager
            if self.strategy_manager and self.strategy_manager.portfolio_manager:
                positions = await self.strategy_manager.portfolio_manager.get_strategy_positions(
                    self.symbol, current_only=True, exclude_equity=True
                )
                
                if positions.empty:
                    add_log("No positions to close.", self.symbol)
                    return

                # 3. Close each position
                for _, pos in positions.iterrows():
                    symbol = pos['symbol']
                    quantity = float(pos['quantity'])
                    asset_class = pos['asset_class']
                    
                    if asset_class == 'CASH' or quantity == 0:
                        continue
                        
                    # Create contract
                    contract = Stock(symbol, "SMART", "USD")
                    
                    # Determine action (Opposite of position)
                    action = 'SELL' if quantity > 0 else 'BUY'
                    abs_qty = abs(quantity)
                    
                    add_log(f"Closing {symbol}: {action} {abs_qty} (MKT)", self.symbol)
                    
                    # Place Market Order
                    await self.place_order(
                        contract=contract,
                        quantity=-quantity, # This will determine BUY/SELL automatically in place_order
                        order_type='MKT',
                        algo=False, # Simple market order for closing
                        urgency='Urgent',
                        orderRef=self.symbol,
                        useRth=True
                    )
            else:
                add_log("PortfolioManager not available to fetch positions.", self.symbol, "ERROR")
                
        except Exception as e:
            add_log(f"Error closing positions: {e}", self.symbol, "ERROR")


    def _generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate indicators and return the subset of rows (latest date) that match the signal.
        """
        df = df.copy()
        
        # 1. Normalize Columns / Index
        # Ensure we have 'Symbol' and 'Date'
        # Handle case where Symbol is index or column
        if 'Symbol' not in df.columns and df.index.name in ['Symbol', 'Ticker']:
            df.reset_index(inplace=True)
            
        if 'Date' not in df.columns and isinstance(df.index, pd.DatetimeIndex):
            df.reset_index(inplace=True)
        elif 'Date' not in df.columns and isinstance(df.index, pd.MultiIndex):
            df.reset_index(inplace=True)
            
        # Ensure sorted by Symbol, Date for proper shift calculation
        if 'Symbol' in df.columns and 'Date' in df.columns:
            df.sort_values(['Symbol', 'Date'], inplace=True)
        else:
            add_log("Missing Symbol or Date columns after reset.", self.symbol, "ERROR")
            return pd.DataFrame()
        
        # 2. Calculate Indicators
        
        # Decline Streak
        # Logic: Close < Prev_Close
        df['Prev_Close'] = df.groupby('Symbol')['Close'].shift(1)
        df['Is_Decline'] = df['Close'] < df['Prev_Close']
        
        # Vectorized Streak
        s = df['Is_Decline']
        # Group key increments when value is False (resetting the streak)
        # (~s).cumsum() increments every time s is False. 
        # So all consecutive Trues share the same group ID (the ID of the preceding False + 1)
        # Fix: Pass df['Symbol'] explicitly since 's' is a Series and doesn't have 'Symbol' in index
        df['Decline_Streak'] = s * (s.groupby([df['Symbol'], (~s).cumsum()]).cumcount() + 1)
        
        # Mean 4D Return
        # User provided '1d_ret'
        if '1d_ret' in df.columns:
            # Use pre-calculated returns if available
            df['Mean_4D_Ret'] = df.groupby('Symbol')['1d_ret'].rolling(window=4).mean().reset_index(level=0, drop=True)
        else:
            # Calculate if missing
            df['Daily_Ret'] = df.groupby('Symbol')['Close'].pct_change()
            df['Mean_4D_Ret'] = df.groupby('Symbol')['Daily_Ret'].rolling(window=4).mean().reset_index(level=0, drop=True)

        # 3. Filter for Signals
        # Signal: Close > 200D_EMA AND Decline_Streak == 4
        # User provided '200D_EMA'
        
        if '200D_EMA' not in df.columns:
             add_log("200D_EMA column missing, cannot generate signals", self.symbol, "ERROR")
             return pd.DataFrame()
             
        # Fix: Remove list brackets [] around the Market Cap condition
        condition = (df['Close'] > df['200D_EMA']) & (df['Market Cap'] > 2e9) & (df['Decline_Streak'] == self.params['decline_days'])
        df['Signal'] = condition
        
        # 4. Limit Price
        # Limit = Close * (1 + multiplier * Mean_4D_Ret)
        df['Limit_Price_Target'] = df['Close'] * (1 + (self.params['multiplier'] * df['Mean_4D_Ret']))
        
        # 5. Select Signals for the Latest Date only
        if 'Date' in df.columns:
            latest_date = df['Date'].max()
            add_log(f"Processing signals for date: {latest_date}", self.symbol)
            
            # Filter for latest date AND Signal == True
            signals = df[(df['Date'] == latest_date) & (df['Signal'])].copy()
            
            # Set index to Symbol for easy iteration/lookup if needed
            if 'Symbol' in signals.columns:
                signals.set_index('Symbol', inplace=True)
                
            return signals
        
        return pd.DataFrame()

    async def _execute_order(self, symbol: str, limit_price: float, quantity: int):
        """
        Place the limit order with pre-calculated quantity.
        """
        try:
            contract = Stock(symbol, "SMART", "USD")
            
            # Check for NaN limit price
            if np.isnan(limit_price) or limit_price <= 0:
                add_log(f"Invalid limit price for {symbol}: {limit_price}", self.symbol, "WARNING")
                return

            # Fix Error 110: Round limit price to 2 decimal places
            limit_price = round(limit_price, 2)

            add_log(f"Placing LIMIT BUY for {symbol}: {quantity} shares @ {limit_price:.2f}", self.symbol)
            
            await self.place_order(
                contract=contract,
                quantity=quantity, # BUY
                order_type='LMT',
                limit=limit_price,
                algo=True,
                urgency='Patient',
                useRth=True
            )
        except Exception as e:
            add_log(f"Failed to execute order for {symbol}: {e}", self.symbol, "ERROR")
