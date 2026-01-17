import math
import asyncio
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List
from ib_async import Contract, Stock, LimitOrder
from obj.base_strategy import BaseStrategy, PARAMS as BASE_PARAMS
from core.log_manager import add_log
from core.arctic_manager import get_ac
from utils.fx_cache import FXCache
import pytz
from datetime import datetime, time

# -----------------------------------------------------------------------------
# Strategy Parameters
# -----------------------------------------------------------------------------
PARAMS = {
    **BASE_PARAMS,
    "universe": "japanese_equities", # Symbol in market_data library
    
    # Strategy Specific
    "multiplier": 2.5,           # Limit Price multiplier
    "decline_days": 4,           # Number of consecutive decline days
    "min_market_cap_jpy": 300e9, # ~2B USD in JPY
    
    # Risk / Allocation
    "max_trade_percent_equity": 0.05, # Max allocation per trade
}

async def get_signals(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Standalone function to generate signals for Japanese stocks.
    - Connects to ArcticDB 'market_data' / 'japanese_equities' if df is None.
    - Calculates indicators (Decline Streak, Mean 4D Ret).
    - Filters for 'Signal'.
    - Adds EUR conversion columns.
    """
    # 1. Load Data
    if df is None:
        try:
            ac = get_ac()
            lib = ac.get_library("market_data")
            if not lib.has_symbol("japanese_equities"):
                print("japanese_equities not found in market_data.")
                return pd.DataFrame()
            df = lib.read("japanese_equities").data
        except Exception as e:
            print(f"Error loading data: {e}")
            return pd.DataFrame()

    df = df.copy()
    df['Symbol'] = df["Symbol"].str.rstrip('.T')

    # 2. Normalize Columns / Index
    if 'Symbol' not in df.columns and df.index.name in ['Symbol', 'Ticker']:
        df.reset_index(inplace=True)
    if 'Date' not in df.columns and isinstance(df.index, pd.DatetimeIndex):
        df.reset_index(inplace=True)
    elif 'Date' not in df.columns and isinstance(df.index, pd.MultiIndex):
        df.reset_index(inplace=True)

    if 'Symbol' not in df.columns or 'Date' not in df.columns:
        print("Missing Symbol or Date columns.")
        return pd.DataFrame()

    df.sort_values(['Symbol', 'Date'], inplace=True)

    # 3. Calculate Indicators
    # Decline Streak
    df['Prev_Close'] = df.groupby('Symbol')['Close'].shift(1)
    df['Is_Decline'] = df['Close'] < df['Prev_Close']
    
    s = df['Is_Decline']
    df['Decline_Streak'] = s * (s.groupby([df['Symbol'], (~s).cumsum()]).cumcount() + 1)

    # Mean 4D Return
    if '1d_ret' in df.columns:
        df['Mean_4D_Ret'] = df.groupby('Symbol')['1d_ret'].rolling(window=4).mean().reset_index(level=0, drop=True)
    else:
        df['Daily_Ret'] = df.groupby('Symbol')['Close'].pct_change()
        df['Mean_4D_Ret'] = df.groupby('Symbol')['Daily_Ret'].rolling(window=4).mean().reset_index(level=0, drop=True)

    # 4. Filter for Signals
    # Check required columns
    required_cols = ['Close', '200D_EMA', 'Market Cap', 'Decline_Streak']
    for col in required_cols:
        if col not in df.columns:
            print(f"Missing column {col}")
            return pd.DataFrame()

    # Signal Condition
    # Note: Market Cap check uses min_market_cap_jpy (default 300B)
    condition = (
        (df['Close'] > df['200D_EMA']) & 
        (df['Market Cap'] > PARAMS['min_market_cap_jpy']) & 
        (df['Decline_Streak'] == PARAMS['decline_days'])
    )
    df['Signal'] = condition

    # 5. Limit Price Target (JPY)
    df['Limit_Price_Target'] = df['Close'] * (1 + (PARAMS['multiplier'] * df['Mean_4D_Ret']))

    # 6. Filter for Latest Date
    if 'Date' in df.columns:
        latest_date = df['Date'].max()
        signals = df[(df['Date'] == latest_date) & (df['Signal'])].copy()
    else:
        signals = pd.DataFrame()

    if signals.empty:
        return signals

    # 7. Currency Conversion (JPY -> EUR)
    # Get Rate: Amount of JPY per 1 EUR (EURJPY)
    # We want to convert JPY Price to EUR Price.
    # Price_EUR = Price_JPY / EURJPY
    try:
        # Use FXCache without IB client (will fall back to yfinance or default)
        fx_cache = FXCache(ib_client=None) 
        # We need EURJPY rate (how many JPY for 1 EUR)
        # get_fx_rate("JPY", "EUR") returns JPY/EUR (~160.0)
        eurjpy = await fx_cache.get_fx_rate("JPY", "EUR")
        
        signals['FX_Rate_EURJPY'] = eurjpy
        signals['Close_EUR'] = signals['Close'] / eurjpy
        signals['Limit_Price_EUR'] = signals['Limit_Price_Target'] / eurjpy
        
    except Exception as e:
        print(f"Currency conversion failed: {e}")
        signals['FX_Rate_EURJPY'] = np.nan
        signals['Close_EUR'] = np.nan
        signals['Limit_Price_EUR'] = np.nan

    if 'Symbol' in signals.columns:
        signals.set_index('Symbol', inplace=True)

    return signals


class FourDayDeclineJapanStrategy(BaseStrategy):
    """
    Implementation of the 4-Day Decline Strategy for Japanese Equities.
    
    - Universe: 'market_data/japanese_equities'
    - 100-lot rounding for orders.
    - Currency conversion checks.
    """
    
    def __init__(self, client_id: int, strategy_manager, params: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(client_id=client_id, strategy_manager=strategy_manager, params=params, **kwargs)
        # Override params if needed
        self.params = {**PARAMS, **(params or {})}
        
    async def initialize_strategy(self):
        pass        

    async def run_strategy(self):
        try:
            # 1. Entry Logic
            await self.scan_and_place_orders()
            
            # 2. Monitoring Loop
            add_log("Entry phase complete. Monitoring...", self.symbol)
            
            while self.is_running:
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
            add_log("Generating signals...", self.symbol)
            
            # Call standalone get_signals
            signals = await get_signals(df=None)
            
            add_log(f"Found {len(signals)} signals.", self.symbol)
            
            if signals.empty:
                return

            # Get Equity (in Account Currency, likely EUR or USD)
            equity = await self.get_equity()
            if equity <= 0:
                equity = 100000.0 # Fallback
                
            # Get EURJPY rate for sizing
            fx_cache = FXCache(self.ib)
            eurjpy = await fx_cache.get_fx_rate("JPY", "EUR") # JPY per EUR
            
            # Assume Account is EUR
            equity_jpy = equity * eurjpy
            
            add_log(f"Equity: {equity} (Assumed EUR) -> {equity_jpy:.2f} JPY (Rate: {eurjpy:.2f})", self.symbol)

            # Check active orders/positions
            active_symbols = set()
            if self.ib:
                try:
                    open_trades = self.ib.openTrades()
                    for t in open_trades:
                        if t.order.orderRef == self.symbol:
                            active_symbols.add(t.contract.symbol)
                except Exception:
                    pass

            if self.strategy_manager and self.strategy_manager.portfolio_manager:
                try:
                    current_positions = await self.strategy_manager.portfolio_manager.get_strategy_positions(
                        self.symbol, current_only=True, exclude_equity=True
                    )
                    if not current_positions.empty:
                        for _, pos in current_positions.iterrows():
                            if float(pos['quantity']) != 0:
                                active_symbols.add(pos['symbol'])
                except Exception:
                    pass

            tasks = []
            for symbol, row in signals.iterrows():
                if symbol in active_symbols:
                    continue

                limit_price = row['Limit_Price_Target']
                
                # Sizing in JPY
                target_amount_jpy = equity_jpy * self.params['max_trade_percent_equity']
                
                quantity = 0
                if limit_price > 0:
                    raw_qty = target_amount_jpy / limit_price
                    # Round to nearest 100
                    quantity = int(round(raw_qty / 100) * 100)
                
                if quantity > 0:
                    tasks.append(self._execute_order(symbol, limit_price, quantity))
                else:
                    add_log(f"Skipping {symbol}: Quantity {quantity} (Target JPY {target_amount_jpy:.0f})", self.symbol)
            
            # Execute
            chunk_size = 30
            for i in range(0, len(tasks), chunk_size):
                chunk = tasks[i:i+chunk_size]
                await asyncio.gather(*chunk)
                await asyncio.sleep(0.5)
                
        except Exception as e:
            add_log(f"Scan error: {e}", self.symbol, "ERROR")
            raise

    async def _execute_order(self, symbol: str, limit_price: float, quantity: int):
        try:
            # Japanese stocks on SMART (auto-route to TSEJ if needed)
            contract = Stock(symbol, "SMART", "JPY")
            
            # Apply TSE Tick Size Rules (Round Down)
            limit_price = self._round_to_tick_size(limit_price)

            add_log(f"Placing PARENT LIMIT BUY for {symbol}: {quantity} shares @ {limit_price:.2f} JPY (GTC)", self.symbol)
            
            # 1. Place Parent Limit Buy (GTC, Transmit=False)
            parent_trade = await self.place_order(
                contract=contract,
                quantity=quantity,
                order_type='LMT',
                limit=limit_price,
                algo=True,
                urgency='Patient',
                useRth=True,
                tif='GTC',
                transmit=False
            )
            
            if not parent_trade:
                add_log(f"Failed to create parent order for {symbol}", self.symbol, "ERROR")
                return

            parent_id = parent_trade.order.orderId
            add_log(f"Parent Order ID: {parent_id}. Attaching Child Sell MOC...", self.symbol)

            # 2. Place Child Sell MOC (DAY, Transmit=True, ParentId=parent_id)
            # Triggers transmission of both orders
            child_trade = await self.place_order(
                contract=contract,
                quantity=-quantity, # SELL
                order_type='MOC',
                algo=False,
                useRth=True,
                tif='DAY', 
                transmit=True,
                parentId=parent_id
            )
            
            add_log(f"Placed Child Sell MOC for {symbol} (ParentId={parent_id})", self.symbol)

        except Exception as e:
            add_log(f"Failed to execute order for {symbol}: {e}", self.symbol, "ERROR")

    def _round_to_tick_size(self, price: float) -> float:
        """
        Round price DOWN to the nearest valid TSE tick size.
        """
        if price <= 3000:
            tick = 1.0
        elif price <= 5000:
            tick = 5.0
        elif price <= 30000:
            tick = 10.0
        elif price <= 50000:
            tick = 50.0
        elif price <= 300000:
            tick = 100.0
        else:
            tick = 500.0 # Simplified for very high prices
            
        return math.floor(price / tick) * tick