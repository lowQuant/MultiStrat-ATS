# Broker Module Documentation

## Overview

The broker module handles all Interactive Brokers API integration, providing a comprehensive interface for trading operations, portfolio management, and risk controls. This module abstracts the complexity of the IB API and provides a clean interface for strategy implementations.

## Module Structure

```
broker/
├── __init__.py              # Module initialization and exports
├── connection.py            # IB API connection management
├── functions.py             # Core trading functions
├── portfoliomanager.py      # Portfolio tracking and management
├── riskmanager.py          # Risk controls and position sizing
├── trade.py                # Trade object definitions
├── trademanager.py         # Trade execution and management
├── utilityfunctions.py     # Utility functions for trading
└── utils.py                # General utilities
```

## Core Components

### 1. Connection Management (`connection.py`)

Handles Interactive Brokers API connections with automatic reconnection and error handling.

**Key Functions:**
- `connect_to_IB(clientid)`: Establishes connection to IB with unique client ID
- `disconnect_from_IB()`: Cleanly disconnects from IB API
- Connection health monitoring and automatic reconnection

**Features:**
- Unique client ID management for multi-strategy support
- Automatic reconnection on connection failures
- Connection status monitoring
- Error handling and logging

### 2. Trade Management (`trademanager.py`)

Central component for managing trade execution and order lifecycle.

**Key Responsibilities:**
- Order placement and modification
- Fill event handling
- Order status tracking
- Communication with StrategyManager via message queue

**Key Methods:**
```python
class TradeManager:
    def __init__(self, ib_client, strategy_manager)
    def place_order(self, contract, order, strategy_symbol)
    def modify_order(self, trade, new_order)
    def cancel_order(self, trade)
    def handle_fill_event(self, trade, fill)
```

**Integration with StrategyManager:**
- Sends order events to message queue
- Notifies portfolio manager of fills
- Provides trade status updates

### 3. Portfolio Management (`portfoliomanager.py`)

Comprehensive portfolio tracking and position management system.

**Key Features:**
- Real-time position tracking
- P&L calculation and monitoring
- Position reconciliation with IB
- ArcticDB integration for position history

**Key Methods:**
```python
class PortfolioManager:
    def __init__(self, ib_client)
    def process_new_trade(self, strategy, trade)
    def match_ib_positions_with_arcticdb(self)
    def get_portfolio_summary(self)
    def calculate_pnl(self)
```

**Data Storage:**
- Positions stored in ArcticDB for persistence
- Real-time position updates
- Historical position tracking
- Strategy-level position attribution

### 4. Risk Management (`riskmanager.py`)

Implements risk controls and position sizing logic.

**Risk Controls:**
- Maximum position size limits
- Drawdown controls
- Exposure limits per strategy
- Emergency stop mechanisms

**Position Sizing:**
- Dynamic position sizing based on volatility
- Risk-adjusted position calculations
- Account equity considerations
- Strategy-specific risk parameters

### 5. Utility Functions (`utilityfunctions.py`)

Collection of utility functions for trading operations.

**Key Utilities:**
- Contract creation helpers
- Order type constructors
- Price calculation utilities
- Market data helpers
- Time and date utilities

### 6. Core Functions (`functions.py`)

Essential trading functions used across the system.

**Key Functions:**
- Market data retrieval
- Order validation
- Contract lookup and creation
- Account information retrieval

## Integration Patterns

### 1. Strategy Integration

Strategies interact with the broker module through well-defined interfaces:

```python
# Example strategy integration
from broker import TradeManager, PortfolioManager
from broker.utilityfunctions import create_stock_contract, create_market_order

# In strategy implementation
trade_manager = TradeManager(ib_client, strategy_manager)
contract = create_stock_contract("AAPL", "SMART", "USD")
order = create_market_order("BUY", 100)
trade_manager.place_order(contract, order, "MyStrategy")
```

### 2. Message Queue Integration

The broker module communicates with the StrategyManager through a message queue system:

```python
# Order placement notification
message = {
    'type': 'order',
    'strategy': strategy_symbol,
    'trade': trade_object
}
strategy_manager.message_queue.put(message)

# Fill event notification
message = {
    'type': 'fill',
    'strategy': strategy_symbol,
    'trade': trade_object,
    'fill': fill_object
}
strategy_manager.message_queue.put(message)
```

### 3. Data Flow

```
Strategy → TradeManager → IB API → Market
    ↓           ↓
MessageQueue → PortfolioManager → ArcticDB
```

## Error Handling

### 1. Connection Errors
- Automatic reconnection attempts
- Graceful degradation during outages
- Error logging and notification

### 2. Order Errors
- Order validation before submission
- Error reporting to strategies
- Automatic retry mechanisms where appropriate

### 3. Data Errors
- Data validation and sanitization
- Fallback data sources
- Error logging and monitoring

## Configuration

### 1. IB Connection Settings
- Host and port configuration
- Client ID management
- Connection timeout settings

### 2. Risk Parameters
- Position size limits
- Exposure controls
- Risk tolerance settings

### 3. Logging Configuration
- Log levels and destinations
- Error notification settings
- Performance monitoring

## Performance Considerations

### 1. Asynchronous Operations
- Non-blocking order placement
- Asynchronous data retrieval
- Event-driven architecture

### 2. Connection Pooling
- Efficient client ID management
- Connection reuse where possible
- Resource optimization

### 3. Data Caching
- Market data caching
- Position data caching
- Performance optimization

## Security Features

### 1. Credential Management
- Secure API key storage
- Environment-based configuration
- No hardcoded credentials

### 2. Access Controls
- Strategy-level permissions
- Operation validation
- Audit logging

### 3. Data Protection
- Encrypted communication where applicable
- Secure data storage
- Privacy controls
