# System Architecture

## Overview

The IB Multi-Strategy ATS follows a modular, thread-safe architecture designed to handle multiple trading strategies simultaneously. The system is built around the concept of isolated strategy execution with centralized coordination.

## Core Architecture Principles

### 1. Thread Isolation
Each trading strategy runs in its own thread with:
- **Dedicated IB Client**: Each strategy gets a unique `clientId` for IB API connection
- **Independent Event Loop**: Strategies have their own asyncio event loops
- **Isolated Error Handling**: Failures in one strategy don't affect others
- **Resource Separation**: Memory and processing resources are isolated per strategy

### 2. Centralized Coordination
The `StrategyManager` acts as the central coordinator:
- **Message Queue**: Handles inter-strategy communication and events
- **Resource Management**: Manages IB connections and system resources
- **Lifecycle Management**: Controls strategy startup, shutdown, and monitoring

### 3. Modular Design
The system is divided into distinct modules:
- **Broker Module**: IB API integration and trading operations
- **Data Module**: Market data and historical data management
- **Strategy Module**: Individual strategy implementations
- **GUI Module**: User interface and system monitoring
- **Portfolio Module**: Position tracking and risk management

## Component Interaction Flow

```
┌─────────────┐    ┌─────────────────┐    ┌─────────────┐
│    GUI      │◄──►│ StrategyManager │◄──►│  Broker     │
│             │    │                 │    │             │
└─────────────┘    └─────────────────┘    └─────────────┘
                            │                      │
                            ▼                      ▼
                   ┌─────────────────┐    ┌─────────────┐
                   │   Strategies    │    │ Data Manager│
                   │   (Threaded)    │    │             │
                   └─────────────────┘    └─────────────┘
```

## Threading Model

### Strategy Threads
Each strategy operates in its own thread:
```python
# From strategy_manager.py
for strategy_module in self.strategies:
    self.clientId += 1  # Unique client ID per strategy
    thread = threading.Thread(
        target=strategy_module.manage_strategy, 
        args=(self.clientId, self, self.strategy_loops)
    )
    thread.daemon = True
    thread.start()
```

### Message Processing Thread
A dedicated thread handles all inter-strategy communication:
```python
# Message queue processing
self.message_processor_thread = threading.Thread(target=self.process_messages)
self.message_processor_thread.daemon = True
self.message_processor_thread.start()
```

## Data Flow Architecture

### 1. Market Data Flow
```
IB API → DataManager → ArcticDB Storage
                    ↓
              Strategy Consumption
```

### 2. Order Flow
```
Strategy → TradeManager → IB API → Market
    ↓           ↓
MessageQueue → PortfolioManager
```

### 3. Event Flow
```
IB Events → StrategyManager → Message Queue → Strategy Handlers
```

## Key Design Patterns

### 1. Observer Pattern
- Strategies observe market data changes
- PortfolioManager observes trade executions
- GUI observes system state changes

### 2. Command Pattern
- Orders are encapsulated as command objects
- Trade operations are queued and executed asynchronously

### 3. Factory Pattern
- Strategy instances are created dynamically from configuration
- IB client connections are factory-created with unique IDs

## Error Handling Strategy

### 1. Isolation
- Strategy errors don't propagate to other strategies
- Connection failures are handled per-strategy

### 2. Recovery
- Automatic reconnection for IB API failures
- Strategy restart capabilities
- Graceful degradation for data feed issues

### 3. Monitoring
- Centralized logging through message queue
- GUI status monitoring
- Error reporting and alerting

## Scalability Considerations

### 1. Resource Management
- Thread pool management for strategy execution
- Connection pooling for IB API clients
- Memory management for historical data

### 2. Performance Optimization
- Asynchronous operations where possible
- Efficient data structures for real-time processing
- Minimal blocking operations in critical paths

### 3. Configuration Management
- Dynamic strategy loading and unloading
- Runtime configuration changes
- Hot-swappable components

## Security Architecture

### 1. API Key Management
- Secure storage of IB credentials
- Environment-based configuration
- No hardcoded sensitive information

### 2. Risk Controls
- Position size limits per strategy
- Maximum drawdown controls
- Emergency stop mechanisms

### 3. Data Protection
- Encrypted data storage where applicable
- Secure communication channels
- Access control for sensitive operations
