# Strategy Manager Documentation

## Overview

The Strategy Manager is the central orchestrator of the IB Multi-Strategy ATS system. It manages the lifecycle of multiple trading strategies, handles inter-strategy communication, and coordinates with the broker module for trade execution. The system is designed to run multiple strategies simultaneously in isolated threads with unique IB client connections.

## Core Components

### 1. StrategyManager Class (`strategy_manager/strategy_manager.py`)

The main coordinator class that manages all strategy operations.

#### Key Attributes:
```python
class StrategyManager:
    def __init__(self):
        self.clientId = 0                    # Counter for unique IB client IDs
        self.ib_client = None               # Main IB client connection
        self.strategy_threads = []          # List of strategy threads
        self.strategy_loops = {}            # Event loops for each strategy
        self.strategies = []                # Loaded strategy modules
        self.trade_manager = TradeManager() # Trade execution manager
        self.portfolio_manager = PortfolioManager() # Portfolio tracking
        self.data_manager = DataManager()   # Data management
        self.message_queue = queue.Queue()  # Inter-strategy communication
```

#### Key Methods:

**Strategy Lifecycle Management:**
- `load_strategies()`: Dynamically loads active strategies from configuration
- `start_all()`: Starts all loaded strategies in separate threads
- `stop_all()`: Gracefully stops all running strategies
- `disconnect()`: Cleanly disconnects all IB connections

**Message Processing:**
- `process_messages()`: Processes messages from strategy threads
- `handle_message()`: Routes messages based on type (order, fill, status)
- `notify_order_placement()`: Handles order placement notifications
- `handle_fill_event()`: Processes trade fill events

### 2. Strategy Loading Mechanism

The system dynamically loads strategies based on configuration stored in ArcticDB.

#### Loading Process:
1. **Configuration Retrieval**: Fetches active strategies from database
2. **Dynamic Import**: Uses `importlib` to load strategy modules
3. **Validation**: Ensures each strategy has required `Strategy` class and `manage_strategy` function
4. **Instantiation**: Creates strategy instances with unique client IDs

```python
def load_strategies(self):
    strategy_names, self.strategy_df = fetch_strategies()
    active_filenames = set(self.strategy_df[self.strategy_df["active"] == "True"]['filename'])
    
    for file in strategy_files:
        spec = importlib.util.spec_from_file_location(module_name, strategy_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, 'Strategy'):
            self.strategies.append(module)
```

### 3. Threading Architecture

#### Unique Client ID System
Each strategy gets a unique IB client ID to ensure isolated connections:

```python
def start_all(self):
    for strategy_module in self.strategies:
        self.clientId += 1  # Increment for each strategy
        thread = threading.Thread(
            target=strategy_module.manage_strategy, 
            args=(self.clientId, self, self.strategy_loops)
        )
        thread.daemon = True
        thread.start()
```

**Why Unique Client IDs?**
- **Isolation**: Each strategy has independent IB API connection
- **Communication**: Strategies can't interfere with each other's orders
- **Scalability**: System can handle multiple strategies simultaneously
- **Error Handling**: Connection issues in one strategy don't affect others

#### Event Loop Management
Each strategy thread gets its own asyncio event loop:

```python
# In strategy thread
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
strategy_loops[client_id] = loop  # Store for coordination
```

### 4. Message Queue System

The StrategyManager uses a centralized message queue for inter-component communication.

#### Message Types:
- **Order Messages**: Order placement notifications
- **Fill Messages**: Trade execution events
- **Status Messages**: Strategy status changes

#### Message Processing Flow:
```python
def process_messages(self):
    while True:
        message = self.message_queue.get(block=True)
        self.handle_message(message)
        
def handle_message(self, message):
    if message['type'] == 'order':
        self.notify_order_placement(message['strategy'], message['trade'])
    elif message['type'] == 'fill':
        self.handle_fill_event(message['strategy'], message['trade'], message['fill'])
    elif message['type'] == 'status_change':
        self.handle_status_change(message['strategy'], message['trade'], message['status'])
```

## Strategy Development Framework

### 1. Strategy Template Structure

All strategies must follow a standard template structure:

```python
# strategy_manager/strategies/strategy_template.py
class Strategy:
    def __init__(self, client_id, strategy_manager):
        self.client_id = client_id
        self.strategy_manager = strategy_manager
        self.ib_client = connect_to_IB(clientid=client_id)
        
    async def run_strategy(self):
        # Strategy logic implementation
        pass
        
def manage_strategy(client_id, strategy_manager, strategy_loops):
    # Entry point for strategy thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    strategy_loops[client_id] = loop
    
    strategy = Strategy(client_id, strategy_manager)
    loop.run_until_complete(strategy.run_strategy())
```

### 2. Strategy Integration Points

**Data Access:**
```python
# Access market data through DataManager
data = self.strategy_manager.data_manager.get_data_from_arctic('market_data', 'AAPL')
```

**Order Placement:**
```python
# Place orders through TradeManager
self.strategy_manager.trade_manager.place_order(contract, order, self.strategy_name)
```

**Portfolio Information:**
```python
# Access portfolio data
positions = self.strategy_manager.portfolio_manager.get_positions()
```

### 3. Available Strategies

The system includes several pre-built strategies in `strategy_manager/strategies/`:

- **LTMT.py**: Long-term momentum strategy
- **PEA_OSS.py**: Put-call ratio oscillator strategy
- **S2.py**: Statistical arbitrage strategy
- **SVIX.py**: VIX-based volatility strategy
- **short_rsi_thrust.py**: RSI-based short strategy
- **short_vix.py**: VIX shorting strategy
- **cnr.py**: Contrarian strategy
- **sie.py**: Sector rotation strategy
- **smag7.py**: Moving average strategy
- **vow.py**: Volume-weighted strategy

## Configuration Management

### 1. Strategy Configuration

Strategies are configured through the GUI and stored in ArcticDB:

```python
# Configuration stored in 'strategies' library
strategy_config = {
    'filename': 'LTMT.py',
    'active': 'True',
    'parameters': {...}
}
```

### 2. Runtime Configuration

The system supports runtime configuration changes:
- Enable/disable strategies without restart
- Modify strategy parameters
- Add new strategies dynamically

## Error Handling and Recovery

### 1. Strategy-Level Error Handling
- Each strategy runs in isolation
- Strategy failures don't affect other strategies
- Automatic error logging and notification

### 2. Connection Recovery
- Automatic IB connection recovery per strategy
- Graceful handling of network interruptions
- Strategy restart capabilities

### 3. System-Level Recovery
- Graceful shutdown procedures
- State persistence across restarts
- Recovery from system failures

## Performance Monitoring

### 1. Strategy Performance Tracking
- Individual strategy P&L tracking
- Performance metrics calculation
- Benchmark comparisons

### 2. System Performance
- Thread monitoring and management
- Resource usage tracking
- Connection health monitoring

### 3. Logging and Alerting
- Comprehensive logging system
- Real-time alerts for critical events
- Performance reporting

## Integration with Other Modules

### 1. Broker Module Integration
- Direct integration with TradeManager
- Portfolio synchronization
- Risk management coordination

### 2. Data Module Integration
- Market data access through DataManager
- Historical data retrieval
- Real-time data feeds

### 3. GUI Integration
- Strategy status display
- Performance monitoring
- Configuration management interface

## Best Practices for Strategy Development

### 1. Thread Safety
- Use thread-safe data structures
- Avoid shared mutable state
- Proper synchronization mechanisms

### 2. Resource Management
- Proper cleanup in strategy shutdown
- Memory management for large datasets
- Connection resource management

### 3. Error Handling
- Comprehensive exception handling
- Graceful degradation strategies
- Proper error logging and reporting
