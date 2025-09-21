"""
AAPL EMA Crossover Strategy

This strategy buys AAPL when the close price crosses above the 20-period EMA
and sells when the close price crosses below the 20-period EMA.

Can be run in both live and backtest modes.
"""

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
from ib_async import Stock, MarketOrder, Contract, BarDataList, IB
from obj.base_strategy import BaseStrategy
from core.log_manager import add_log


# Strategy parameters
PARAMS = {
    "symbol": "AAPL",
    "ema_period": 20,
    "bar_size": "1 min",  # Can be "1 min", "5 mins", "1 hour", etc.
    "lookback_days": 5,  # Days of historical data to fetch
    "position_size": 0.95,  # Use 95% of allocated equity per trade
    "max_position": 1000,  # Maximum shares to hold
    "min_price_move": 0.01,  # Minimum price move to trigger signal
}


class AaplEmaStrategy(BaseStrategy):
    """
    AAPL EMA Crossover Strategy
    
    Entry: Close > 20 EMA (bullish crossover)
    Exit: Close < 20 EMA (bearish crossover)
    """
    
    def __init__(self, *args, **kwargs):
        """Initialize the AAPL EMA strategy."""
        super().__init__(*args, **kwargs)
        
        # Override symbol from params if provided (e.g., 'AAPL')
        try:
            if isinstance(self.params, dict) and self.params.get("symbol"):
                self.symbol = str(self.params["symbol"]).upper()
        except Exception:
            pass
        
        # Strategy state
        self.contract = None
        self.bars_df = pd.DataFrame()
        self.current_position = 0
        self.last_signal = None
        self.last_ema = None
        self.last_close = None
        
        # Subscription handles
        self.bars_subscription = None
        
    async def initialize_strategy(self):
        """Initialize strategy-specific data and setup."""
        add_log(f"Initializing AAPL EMA Strategy with params: {self.params}", self.symbol)
        
        # Resolve symbol safely from params or fallback to self.symbol
        sym = str(self.params.get("symbol", self.symbol)).upper()
        # Create contract
        self.contract = Stock(sym, "SMART", "USD")
        
        # Qualify the contract (skip in backtest)
        if self.broker_type != "backtest" and self.ib and self.is_connected:
            await self.ib.qualifyContractsAsync(self.contract)
            add_log(f"Contract qualified: {self.contract}", self.symbol)
        
        # Get initial position if any
        await self._update_current_position()
        
        # Load historical data
        if self.broker_type != "backtest":
            await self._load_historical_data()
        
        # Subscribe to real-time bars if in live mode
        if self.broker_type == "live" and self.ib:
            await self._subscribe_to_bars()
    
    async def _load_historical_data(self):
        """Load historical data for EMA calculation."""
        try:
            if not self.ib or not self.is_connected:
                add_log("Cannot load historical data - IB not connected", self.symbol, "WARNING")
                return
            
            # Calculate end time (now) and duration
            end_time = ""  # Empty string means now
            duration_str = f"{self.params['lookback_days']} D"
            
            add_log(f"Requesting historical data: {duration_str} of {self.params['bar_size']} bars", self.symbol)
            
            # Request historical bars
            bars = await self.ib.reqHistoricalDataAsync(
                self.contract,
                endDateTime=end_time,
                durationStr=duration_str,
                barSizeSetting=self.params['bar_size'],
                whatToShow='TRADES',
                useRTH=False,  # Include extended hours
                formatDate=1
            )
            
            if bars:
                # Convert to DataFrame
                self.bars_df = pd.DataFrame([
                    {
                        'timestamp': bar.date,
                        'open': bar.open,
                        'high': bar.high,
                        'low': bar.low,
                        'close': bar.close,
                        'volume': bar.volume
                    }
                    for bar in bars
                ])
                
                # Calculate EMA
                self._calculate_ema()
                
                add_log(f"Loaded {len(self.bars_df)} historical bars", self.symbol)
                add_log(f"Latest close: {self.bars_df['close'].iloc[-1]:.2f}, "
                       f"Latest EMA: {self.bars_df['ema'].iloc[-1]:.2f}", self.symbol)
            else:
                add_log("No historical data received", self.symbol, "WARNING")
                
        except Exception as e:
            add_log(f"Error loading historical data: {e}", self.symbol, "ERROR")
    
    def _calculate_ema(self):
        """Calculate EMA for the bars DataFrame."""
        if self.bars_df.empty:
            return
        
        # Calculate EMA
        ema_period = self.params['ema_period']
        self.bars_df['ema'] = self.bars_df['close'].ewm(span=ema_period, adjust=False).mean()
        
        # Store latest values
        self.last_ema = self.bars_df['ema'].iloc[-1]
        self.last_close = self.bars_df['close'].iloc[-1]
    
    async def _subscribe_to_bars(self):
        """Subscribe to real-time bar updates."""
        try:
            # Request real-time bars
            self.bars_subscription = self.ib.reqRealTimeBars(
                self.contract,
                5,  # 5-second bars
                'TRADES',
                useRTH=False
            )
            
            # Set up callback for new bars
            self.bars_subscription.updateEvent += self._on_bar_update
            
            add_log("Subscribed to real-time bars", self.symbol)
            
        except Exception as e:
            add_log(f"Error subscribing to bars: {e}", self.symbol, "ERROR")
    
    def _on_bar_update(self, bars: BarDataList, hasNewBar: bool):
        """Handle real-time bar updates."""
        if hasNewBar and bars:
            # Get the latest bar
            latest_bar = bars[-1]
            
            # Add to DataFrame
            new_row = pd.DataFrame([{
                'timestamp': latest_bar.time,
                'open': getattr(latest_bar, 'open_', getattr(latest_bar, 'open', None)),
                'high': getattr(latest_bar, 'high', None),
                'low': getattr(latest_bar, 'low', None),
                'close': getattr(latest_bar, 'close', None),
                'volume': getattr(latest_bar, 'volume', None)
            }])
            
            self.bars_df = pd.concat([self.bars_df, new_row], ignore_index=True)
            
            # Keep only recent data (e.g., last 1000 bars)
            if len(self.bars_df) > 1000:
                self.bars_df = self.bars_df.iloc[-1000:]
            
            # Recalculate EMA
            self._calculate_ema()
            
            # Check for signals - if no running loop (backtest), run synchronously
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._check_signals())
            except RuntimeError:
                # No running loop, execute directly
                try:
                    asyncio.run(self._check_signals())
                except RuntimeError:
                    # If already in a loop context that doesn't expose get_running_loop, fallback to direct await via helper
                    import anyio
                    anyio.run(lambda: self._check_signals())

    # Provide a public handler name expected by BacktestManager wiring
    def handle_realtime_bars(self, bars: BarDataList, hasNewBar: bool):
        self._on_bar_update(bars, hasNewBar)
    
    # Generic backtest/live bar handler name
    def on_bar(self, bars: BarDataList, hasNewBar: bool):
        self._on_bar_update(bars, hasNewBar)
    
    async def run_strategy(self):
        """Main strategy execution loop."""
        add_log("Starting AAPL EMA Strategy main loop", self.symbol)
        
        try:
            while self.is_running:
                # Check signals periodically
                await self._check_signals()
                
                # Update position info
                await self._update_current_position()
                
                # Log status
                if self.last_ema and self.last_close:
                    position_str = f"Position: {self.current_position} shares"
                    price_str = f"Close: ${self.last_close:.2f}, EMA: ${self.last_ema:.2f}"
                    signal_str = f"Signal: {self.last_signal or 'NEUTRAL'}"
                    add_log(f"{position_str} | {price_str} | {signal_str}", self.symbol)
                
                # Wait before next check
                await asyncio.sleep(60)  # Check every minute
                
        except Exception as e:
            add_log(f"Error in strategy loop: {e}", self.symbol, "ERROR")
    
    async def _check_signals(self):
        """Check for entry/exit signals based on EMA crossover."""
        try:
            if self.bars_df.empty or 'ema' not in self.bars_df.columns:
                return
            
            # Need at least 2 bars to check for crossover
            if len(self.bars_df) < 2:
                return
            
            # Get current and previous values
            curr_close = self.bars_df['close'].iloc[-1]
            curr_ema = self.bars_df['ema'].iloc[-1]
            prev_close = self.bars_df['close'].iloc[-2]
            prev_ema = self.bars_df['ema'].iloc[-2]
            
            # Check for bullish crossover (close crosses above EMA)
            bullish_crossover = (prev_close <= prev_ema) and (curr_close > curr_ema)
            
            # Check for bearish crossover (close crosses below EMA)
            bearish_crossover = (prev_close >= prev_ema) and (curr_close < curr_ema)
            
            # Generate signals
            if bullish_crossover and self.current_position <= 0:
                # Buy signal
                self.last_signal = "BUY"
                add_log(f"BUY SIGNAL: Close ({curr_close:.2f}) crossed above EMA ({curr_ema:.2f})", self.symbol)
                await self._enter_position()
                
            elif bearish_crossover and self.current_position > 0:
                # Sell signal
                self.last_signal = "SELL"
                add_log(f"SELL SIGNAL: Close ({curr_close:.2f}) crossed below EMA ({curr_ema:.2f})", self.symbol)
                await self._exit_position()
                
            else:
                # No signal
                self.last_signal = "HOLD"
                
        except Exception as e:
            add_log(f"Error checking signals: {e}", self.symbol, "ERROR")
    
    async def _enter_position(self):
        """Enter a long position in AAPL."""
        try:
            if not self.broker:
                add_log("Broker not initialized", self.symbol, "ERROR")
                return
            
            if self.current_position > 0:
                add_log("Already in position, skipping buy", self.symbol)
                return
            
            # Create buy order
            order = MarketOrder("BUY", 0)  # Quantity will be calculated by broker
            
            # Place order using broker (size as % of equity)
            size = self.params.get("position_size", 0.95)
            
            add_log(f"Placing BUY order with {size*100}% of allocated equity", self.symbol)
            
            trade = await self.broker.place_order(
                contract=self.contract,
                order=order,
                size=size
            )
            
            if trade:
                add_log(f"Buy order placed: {order.totalQuantity} shares", self.symbol)
                self.current_position = order.totalQuantity
            else:
                add_log("Failed to place buy order", self.symbol, "ERROR")
                
        except Exception as e:
            add_log(f"Error entering position: {e}", self.symbol, "ERROR")
    
    async def _exit_position(self):
        """Exit the current long position in AAPL."""
        try:
            if not self.broker:
                add_log("Broker not initialized", self.symbol, "ERROR")
                return
            
            if self.current_position <= 0:
                add_log("No position to exit", self.symbol)
                return
            
            # Create sell order for entire position
            order = MarketOrder("SELL", self.current_position)
            
            add_log(f"Placing SELL order for {self.current_position} shares", self.symbol)
            
            # Place order directly with known quantity
            trade = await self.broker.place_order(
                contract=self.contract,
                order=order,
                size=1.0  # Not used since we specified quantity
            )
            
            if trade:
                add_log(f"Sell order placed: {self.current_position} shares", self.symbol)
                self.current_position = 0
            else:
                add_log("Failed to place sell order", self.symbol, "ERROR")
                
        except Exception as e:
            add_log(f"Error exiting position: {e}", self.symbol, "ERROR")
    
    async def _update_current_position(self):
        """Update current position from broker."""
        try:
            if not self.broker:
                return
            
            positions = await self.broker.get_positions()
            
            # Find AAPL position
            self.current_position = 0
            for pos in positions:
                if pos.contract.symbol == self.params["symbol"]:
                    self.current_position = pos.position
                    break
                    
        except Exception as e:
            add_log(f"Error updating position: {e}", self.symbol, "WARNING")
    
    async def _cleanup(self):
        """Clean up strategy resources."""
        try:
            # Unsubscribe from real-time bars
            if self.bars_subscription:
                self.ib.cancelRealTimeBars(self.bars_subscription)
                add_log("Unsubscribed from real-time bars", self.symbol)
            
            # Save final backtest results if in backtest mode
            if self.broker_type == "backtest" and hasattr(self.broker, 'save_backtest_results'):
                self.broker.save_backtest_results()
                add_log("Backtest results saved", self.symbol)
            
            # Call parent cleanup
            await super()._cleanup()
            
        except Exception as e:
            add_log(f"Error in cleanup: {e}", self.symbol, "ERROR")
    
    def on_bar(self, bars, hasNewBar: bool):
        """
        Handle bar updates for backtesting.
        This method is called by the backtest engine to feed historical data.
        """
        if self.broker_type == "backtest" and hasNewBar:
            # Process bar update for backtest
            self._on_bar_update(bars, hasNewBar)


# For backtesting, we need a way to feed historical data
class AaplEmaBacktestStrategy(AaplEmaStrategy):
    """
    Specialized version for backtesting that processes historical bars sequentially.
    """
    
    async def run_strategy(self):
        """Override for backtest mode - process bars sequentially."""
        if self.broker_type != "backtest":
            # Use parent implementation for live mode
            return await super().run_strategy()
        
        add_log("Running AAPL EMA Strategy in BACKTEST mode", self.symbol)
        
        try:
            # Process each bar sequentially
            for i in range(self.params['ema_period'], len(self.bars_df)):
                if not self.is_running:
                    break
                
                # Get subset of data up to current bar
                current_df = self.bars_df.iloc[:i+1].copy()
                
                # Calculate EMA on subset
                current_df['ema'] = current_df['close'].ewm(
                    span=self.params['ema_period'], 
                    adjust=False
                ).mean()
                
                # Update state
                self.last_close = current_df['close'].iloc[-1]
                self.last_ema = current_df['ema'].iloc[-1]
                
                # Check for signals using the subset
                if i > self.params['ema_period']:
                    prev_close = current_df['close'].iloc[-2]
                    prev_ema = current_df['ema'].iloc[-2]
                    
                    # Check crossovers
                    bullish = (prev_close <= prev_ema) and (self.last_close > self.last_ema)
                    bearish = (prev_close >= prev_ema) and (self.last_close < self.last_ema)
                    
                    if bullish and self.current_position <= 0:
                        await self._enter_position()
                    elif bearish and self.current_position > 0:
                        await self._exit_position()
                
                # Record equity curve periodically
                if i % 100 == 0 and hasattr(self.broker, '_backtest_data'):
                    self.broker._backtest_data['equity_curve'].append({
                        'timestamp': current_df.index[-1] if not current_df.empty else pd.Timestamp.now(),
                        'equity': self.broker.engine.equity() if self.broker.engine else 0
                    })
                
                # Small delay to simulate real-time processing
                await asyncio.sleep(0.001)
            
            # Save final results
            if hasattr(self.broker, 'save_backtest_results'):
                self.broker.save_backtest_results()
                add_log("Backtest completed and results saved", self.symbol)
                
        except Exception as e:
            add_log(f"Error in backtest loop: {e}", self.symbol, "ERROR")
