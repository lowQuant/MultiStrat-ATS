# IB Multi-Strategy Automated Trading System (ATS)

## Overview

The IB Multi-Strategy ATS is a comprehensive automated trading system built for Interactive Brokers (IB) that enables simultaneous execution of multiple trading strategies. The system features a modular architecture with separate components for broker connectivity, data management, strategy execution, portfolio management, and a graphical user interface.

## Key Features

- **Multi-Strategy Execution**: Run multiple trading strategies simultaneously with independent IB client connections
- **Thread-Safe Architecture**: Each strategy runs in its own thread with dedicated event loops
- **Real-Time Data Management**: Integration with ArcticDB for historical data storage and yfinance for market data
- **Portfolio Management**: Comprehensive position tracking and risk management
- **GUI Interface**: User-friendly interface for strategy management, portfolio monitoring, and system configuration
- **Broker Integration**: Native Interactive Brokers API integration with automatic reconnection handling
- **Risk Management**: Built-in risk controls and position sizing

## Architecture Overview

The system follows a modular architecture with clear separation of concerns:

```
IB-Multi-Strategy-ATS/
├── main.py                 # Entry point - launches GUI
├── strategy_manager/       # Core strategy management
│   ├── strategy_manager.py # Central strategy coordinator
│   └── strategies/         # Individual strategy implementations
├── broker/                 # IB API integration and trading
├── data_and_research/      # Data management and research tools
├── gui/                    # User interface components
└── docs/                   # Documentation (this folder)
```

## Core Concepts

### Strategy Threading Model
Each strategy runs in its own thread with a dedicated IB client connection (unique clientId). This design ensures:
- Strategies don't interfere with each other
- Independent order management per strategy
- Isolated error handling
- Scalable multi-strategy execution

### Message Queue System
The StrategyManager uses a centralized message queue to handle:
- Order placement notifications
- Fill events
- Status changes
- Cross-strategy communication

### Data Architecture
- **ArcticDB**: High-performance time-series database for historical data storage
- **Real-time feeds**: Direct IB market data integration
- **External data**: yfinance integration for additional market data

## Quick Start

1. **Installation**: Ensure all dependencies are installed (see requirements)
2. **Configuration**: Set up IB TWS/Gateway connection parameters
3. **Strategy Setup**: Configure strategies via the GUI settings panel
4. **Launch**: Run `python main.py` to start the system

## Documentation Structure

This documentation is organized into the following sections:

- [Architecture Overview](architecture.md) - Detailed system architecture
- [Broker Module](broker.md) - IB integration and trading components
- [Strategy Manager](strategy_manager.md) - Strategy execution and management
- [Data Management](data_management.md) - Data handling and storage
- [GUI Components](gui.md) - User interface documentation
- [Strategy Development](strategy_development.md) - Guide for creating new strategies
- [Configuration](configuration.md) - System setup and configuration
- [API Reference](api_reference.md) - Complete API documentation

## System Requirements

- Python 3.8+
- Interactive Brokers TWS or IB Gateway
- ArcticDB for data storage
- Required Python packages (see setup.py)

## Support and Development

This system is designed for algorithmic trading with Interactive Brokers. For questions about strategy development, system configuration, or extending functionality, refer to the detailed documentation in this folder.
