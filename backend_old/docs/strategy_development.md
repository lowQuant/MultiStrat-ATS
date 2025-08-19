# Strategy Development Guide

## Overview

This guide provides comprehensive instructions for developing new trading strategies within the IB Multi-Strategy ATS framework. The system is designed to support multiple concurrent strategies with isolated execution environments and standardized interfaces.

## Strategy Architecture

### 1. Strategy Template Structure

All strategies must follow the standardized template structure found in `strategy_manager/strategies/strategy_template.py`:

```python
import asyncio
from ib_async import *
from broker import connect_to_IB, disconnect_from_IB

class Strategy:
    def __init__(self, client_id, strategy_manager):
        self.client_id = client_id
        self.strategy_manager = strategy_manager
        self.strategy_name = "YourStrategyName"
        
        # Connect to IB with unique client ID
        self.ib = connect_to_IB(clientid=client_id)
        
        # Initialize strategy-specific variables
        self.positions = {}
        self.orders = {}
        self.running = True
        
    async def initialize(self):
        """Initialize strategy - called once at startup"""
        # Setup market data subscriptions
        # Initialize indicators
        # Load historical data if needed
        pass
        
    async def on_market_data(self, ticker):
        """Handle real-time market data updates"""
        # Process incoming market data
        # Update indicators
        # Generate trading signals
        pass
        
    async def on_order_status(self, trade):
        """Handle order status changes"""
        # Process order updates
        # Update position tracking
        pass
        
    async def generate_signals(self):
        """Main strategy logic - generate trading signals"""
        # Implement your trading logic here
        # Return buy/sell signals
        pass
        
    async def execute_trades(self, signals):
        """Execute trades based on signals"""
        # Place orders through TradeManager
        # Update position tracking
        pass
        
    async def run_strategy(self):
        """Main strategy execution loop"""
        await self.initialize()
        
        while self.running:
            try:
                # Generate trading signals
                signals = await self.generate_signals()
                
                # Execute trades if signals present
                if signals:
                    await self.execute_trades(signals)
                    
                # Wait before next iteration
                await asyncio.sleep(1)  # Adjust frequency as needed
                
            except Exception as e:
                print(f"Strategy error: {e}")
                # Handle errors gracefully
                
    def stop(self):
        """Stop the strategy"""
        self.running = False
        disconnect_from_IB(self.ib)

def manage_strategy(client_id, strategy_manager, strategy_loops):
    """Entry point for strategy thread - required function"""
    # Create event loop for this strategy thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    strategy_loops[client_id] = loop
    
    # Create and run strategy instance
    strategy = Strategy(client_id, strategy_manager)
    
    try:
        loop.run_until_complete(strategy.run_strategy())
    except Exception as e:
        print(f"Strategy thread error: {e}")
    finally:
        strategy.stop()
        loop.close()
```

### 2. Required Components

Every strategy must implement:

**Required Class**: `Strategy`
**Required Function**: `manage_strategy(client_id, strategy_manager, strategy_loops)`

**Required Methods in Strategy Class:**
- `__init__(self, client_id, strategy_manager)`
- `run_strategy(self)` - Main async execution loop
- `stop(self)` - Cleanup and shutdown

## Data Access Patterns

### 1. Historical Data Access

```python
# Access historical data through DataManager
async def load_historical_data(self, symbol, days=30):
    data_manager = self.strategy_manager.data_manager
    historical_data = data_manager.get_data_from_arctic('market_data', symbol)
    
    # Filter for recent data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    recent_data = historical_data[start_date:end_date]
    
    return recent_data
```

### 2. Real-Time Data Subscription

```python
# Subscribe to real-time market data
async def setup_market_data(self, symbols):
    for symbol in symbols:
        contract = Stock(symbol, 'SMART', 'USD')
        ticker = self.ib.reqMktData(contract)
        ticker.updateEvent += self.on_market_data
```

### 3. Technical Indicators

```python
# Calculate technical indicators
def calculate_indicators(self, data):
    # Example: Simple Moving Average
    data['SMA_20'] = data['Close'].rolling(window=20).mean()
    data['SMA_50'] = data['Close'].rolling(window=50).mean()
    
    # Example: RSI
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    data['RSI'] = 100 - (100 / (1 + rs))
    
    return data
```

## Order Management

### 1. Order Placement

```python
# Place orders through the TradeManager
async def place_order(self, symbol, action, quantity, order_type='MKT'):
    # Create contract
    contract = Stock(symbol, 'SMART', 'USD')
    
    # Create order
    if order_type == 'MKT':
        order = MarketOrder(action, quantity)
    elif order_type == 'LMT':
        order = LimitOrder(action, quantity, limit_price)
    
    # Place order through TradeManager
    trade = self.strategy_manager.trade_manager.place_order(
        contract, order, self.strategy_name
    )
    
    # Track the order
    self.orders[trade.order.orderId] = trade
    
    return trade
```

### 2. Position Management

```python
# Track positions
def update_position(self, symbol, quantity, price):
    if symbol not in self.positions:
        self.positions[symbol] = {
            'quantity': 0,
            'avg_price': 0,
            'unrealized_pnl': 0
        }
    
    # Update position
    current_qty = self.positions[symbol]['quantity']
    current_avg = self.positions[symbol]['avg_price']
    
    # Calculate new average price
    if current_qty + quantity != 0:
        new_avg = ((current_qty * current_avg) + (quantity * price)) / (current_qty + quantity)
        self.positions[symbol]['avg_price'] = new_avg
    
    self.positions[symbol]['quantity'] += quantity
```

## Strategy Examples

### 1. Simple Moving Average Crossover

```python
class MovingAverageCrossover(Strategy):
    def __init__(self, client_id, strategy_manager):
        super().__init__(client_id, strategy_manager)
        self.strategy_name = "MA_Crossover"
        self.symbols = ['AAPL', 'MSFT', 'GOOGL']
        self.short_window = 20
        self.long_window = 50
        
    async def generate_signals(self):
        signals = []
        
        for symbol in self.symbols:
            # Get recent data
            data = await self.load_historical_data(symbol, days=60)
            
            # Calculate moving averages
            data['SMA_short'] = data['Close'].rolling(self.short_window).mean()
            data['SMA_long'] = data['Close'].rolling(self.long_window).mean()
            
            # Generate signals
            if len(data) >= 2:
                current = data.iloc[-1]
                previous = data.iloc[-2]
                
                # Bullish crossover
                if (current['SMA_short'] > current['SMA_long'] and 
                    previous['SMA_short'] <= previous['SMA_long']):
                    signals.append({'symbol': symbol, 'action': 'BUY', 'quantity': 100})
                
                # Bearish crossover
                elif (current['SMA_short'] < current['SMA_long'] and 
                      previous['SMA_short'] >= previous['SMA_long']):
                    signals.append({'symbol': symbol, 'action': 'SELL', 'quantity': 100})
        
        return signals
```

### 2. Mean Reversion Strategy

```python
class MeanReversionStrategy(Strategy):
    def __init__(self, client_id, strategy_manager):
        super().__init__(client_id, strategy_manager)
        self.strategy_name = "Mean_Reversion"
        self.symbol = 'SPY'
        self.lookback_period = 20
        self.std_threshold = 2.0
        
    async def generate_signals(self):
        # Get recent data
        data = await self.load_historical_data(self.symbol, days=30)
        
        # Calculate mean and standard deviation
        data['SMA'] = data['Close'].rolling(self.lookback_period).mean()
        data['STD'] = data['Close'].rolling(self.lookback_period).std()
        data['Z_Score'] = (data['Close'] - data['SMA']) / data['STD']
        
        current = data.iloc[-1]
        signals = []
        
        # Mean reversion signals
        if current['Z_Score'] > self.std_threshold:
            # Price too high, sell signal
            signals.append({'symbol': self.symbol, 'action': 'SELL', 'quantity': 100})
        elif current['Z_Score'] < -self.std_threshold:
            # Price too low, buy signal
            signals.append({'symbol': self.symbol, 'action': 'BUY', 'quantity': 100})
            
        return signals
```

## Risk Management Integration

### 1. Position Sizing

```python
def calculate_position_size(self, symbol, signal_strength, account_equity):
    """Calculate position size based on risk management rules"""
    
    # Get volatility
    data = self.load_historical_data(symbol, days=30)
    volatility = data['Close'].pct_change().std() * np.sqrt(252)  # Annualized
    
    # Risk per trade (e.g., 1% of account)
    risk_per_trade = 0.01
    risk_amount = account_equity * risk_per_trade
    
    # Position size based on volatility
    position_size = int(risk_amount / (volatility * data['Close'].iloc[-1]))
    
    # Apply signal strength
    position_size = int(position_size * signal_strength)
    
    # Apply maximum position limits
    max_position = int(account_equity * 0.1 / data['Close'].iloc[-1])  # Max 10% of account
    position_size = min(position_size, max_position)
    
    return position_size
```

### 2. Stop Loss Implementation

```python
async def set_stop_loss(self, symbol, entry_price, action, stop_percentage=0.02):
    """Set stop loss order"""
    
    if action == 'BUY':
        stop_price = entry_price * (1 - stop_percentage)
        stop_action = 'SELL'
    else:
        stop_price = entry_price * (1 + stop_percentage)
        stop_action = 'BUY'
    
    # Create stop order
    contract = Stock(symbol, 'SMART', 'USD')
    stop_order = StopOrder(stop_action, self.positions[symbol]['quantity'], stop_price)
    
    # Place stop order
    trade = self.strategy_manager.trade_manager.place_order(
        contract, stop_order, f"{self.strategy_name}_STOP"
    )
    
    return trade
```

## Configuration and Parameters

### 1. Strategy Configuration

```python
# Strategy parameters should be configurable
class ConfigurableStrategy(Strategy):
    def __init__(self, client_id, strategy_manager):
        super().__init__(client_id, strategy_manager)
        
        # Load configuration from database
        self.config = self.load_strategy_config()
        
        # Set parameters from config
        self.symbols = self.config.get('symbols', ['SPY'])
        self.lookback_period = self.config.get('lookback_period', 20)
        self.risk_per_trade = self.config.get('risk_per_trade', 0.01)
        
    def load_strategy_config(self):
        """Load strategy configuration from ArcticDB"""
        try:
            data_manager = self.strategy_manager.data_manager
            config_data = data_manager.get_data_from_arctic('strategies', self.strategy_name)
            return config_data.iloc[-1].to_dict()  # Get latest config
        except:
            return {}  # Return empty config if none exists
```

### 2. Parameter Optimization

```python
def optimize_parameters(self, symbol, start_date, end_date):
    """Optimize strategy parameters using historical data"""
    
    best_params = {}
    best_performance = -float('inf')
    
    # Parameter ranges to test
    short_windows = range(10, 30, 5)
    long_windows = range(40, 80, 10)
    
    for short_window in short_windows:
        for long_window in long_windows:
            if short_window >= long_window:
                continue
                
            # Backtest with these parameters
            performance = self.backtest_parameters(
                symbol, start_date, end_date, short_window, long_window
            )
            
            if performance > best_performance:
                best_performance = performance
                best_params = {
                    'short_window': short_window,
                    'long_window': long_window
                }
    
    return best_params, best_performance
```

## Testing and Validation

### 1. Backtesting Framework

```python
def backtest_strategy(self, start_date, end_date, initial_capital=100000):
    """Backtest the strategy over historical data"""
    
    # Load historical data
    data = self.load_historical_data_range(start_date, end_date)
    
    # Initialize backtesting variables
    capital = initial_capital
    positions = {}
    trades = []
    
    # Run strategy over historical data
    for i in range(len(data)):
        current_data = data.iloc[:i+1]
        
        # Generate signals based on current data
        signals = self.generate_signals_backtest(current_data)
        
        # Execute trades
        for signal in signals:
            trade_result = self.execute_backtest_trade(
                signal, current_data.iloc[-1], capital, positions
            )
            trades.append(trade_result)
            capital = trade_result['remaining_capital']
    
    # Calculate performance metrics
    performance = self.calculate_performance_metrics(trades, initial_capital)
    return performance
```

### 2. Paper Trading

```python
class PaperTradingStrategy(Strategy):
    """Strategy wrapper for paper trading"""
    
    def __init__(self, client_id, strategy_manager):
        super().__init__(client_id, strategy_manager)
        self.paper_trading = True
        self.paper_capital = 100000
        self.paper_positions = {}
        
    async def execute_trades(self, signals):
        """Override to execute paper trades instead of real trades"""
        
        if self.paper_trading:
            for signal in signals:
                self.execute_paper_trade(signal)
        else:
            # Execute real trades
            await super().execute_trades(signals)
    
    def execute_paper_trade(self, signal):
        """Execute a paper trade"""
        # Simulate trade execution
        # Update paper positions
        # Track paper P&L
        pass
```

## Deployment and Monitoring

### 1. Strategy Registration

To deploy a new strategy:

1. **Create Strategy File**: Place in `strategy_manager/strategies/`
2. **Register in Database**: Add to strategy configuration
3. **Activate Strategy**: Enable through GUI settings
4. **Monitor Performance**: Track through portfolio window

### 2. Performance Monitoring

```python
def log_strategy_performance(self):
    """Log strategy performance metrics"""
    
    performance_data = {
        'timestamp': datetime.now(),
        'strategy_name': self.strategy_name,
        'total_pnl': self.calculate_total_pnl(),
        'positions': len(self.positions),
        'active_orders': len(self.orders),
        'win_rate': self.calculate_win_rate(),
        'sharpe_ratio': self.calculate_sharpe_ratio()
    }
    
    # Send to message queue for logging
    message = {
        'type': 'performance',
        'strategy': self.strategy_name,
        'data': performance_data
    }
    self.strategy_manager.message_queue.put(message)
```

## Best Practices

### 1. Error Handling

- Always use try-catch blocks in main loops
- Implement graceful degradation for data failures
- Log all errors with sufficient detail
- Implement circuit breakers for repeated failures

### 2. Resource Management

- Properly close IB connections on shutdown
- Clean up event loop resources
- Monitor memory usage for data-intensive strategies
- Implement proper cleanup in stop() method

### 3. Testing

- Always backtest strategies before live deployment
- Use paper trading for initial validation
- Implement comprehensive unit tests
- Monitor strategy performance continuously

### 4. Documentation

- Document all strategy parameters
- Provide clear descriptions of strategy logic
- Include performance expectations
- Document risk characteristics
