# MATS - Multi-Strategy Automated Trading System

## Overview

MATS is a Python backend + React frontend system for managing multiple trading strategies through Interactive Brokers. The backend handles strategy execution, position tracking, and data persistence via ArcticDB.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FastAPI Backend                                 │
│  main.py                                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐    ┌──────────────────┐    ┌────────────────────────┐  │
│  │ StrategyManager │───▶│ PortfolioManager │───▶│      ArcticDB          │  │
│  │   (clientId=0)  │    │   (Accounting)   │    │  (Data Persistence)    │  │
│  └────────┬────────┘    └──────────────────┘    └────────────────────────┘  │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────┐                                │
│  │           Active Strategies              │                                │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │                                │
│  │  │Strategy 1│ │Strategy 2│ │Strategy N│ │                                │
│  │  │clientId=1│ │clientId=2│ │clientId=N│ │                                │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ │                                │
│  │       │            │            │        │                                │
│  │       ▼            ▼            ▼        │                                │
│  │  ┌──────────────────────────────────┐   │                                │
│  │  │         LiveBroker / BacktestBroker  │                                │
│  │  └──────────────────────────────────┘   │                                │
│  └─────────────────────────────────────────┘                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │  Interactive      │
                    │  Brokers Gateway  │
                    └───────────────────┘
```

## Directory Structure

```
backend/
├── main.py                 # FastAPI application entry point
├── core/                   # Core system components
│   ├── strategy_manager.py # Strategy lifecycle management
│   ├── portfolio_manager.py# Position tracking & accounting
│   ├── arctic_manager.py   # ArcticDB connection management
│   ├── trade_manager.py    # Trade execution helpers
│   └── log_manager.py      # Logging & WebSocket broadcasting
├── broker/                 # Broker abstraction layer
│   ├── base_broker.py      # Abstract broker interface
│   ├── live_broker.py      # IB live trading implementation
│   └── backtest_broker.py  # Backtesting implementation
├── obj/                    # Core objects
│   └── base_strategy.py    # Abstract strategy base class
├── strategies/             # Strategy implementations
├── utils/                  # Utility modules
│   ├── fx_cache.py         # FX rate caching
│   ├── ib_connection.py    # IB connection helpers
│   ├── strategy_table_helpers.py  # Strategy data operations
│   ├── position_helpers.py # Position calculation helpers
│   └── persistence_utils.py# ArcticDB write utilities
├── routes/                 # FastAPI route handlers
├── jobs/                   # Scheduled jobs
├── backtest/               # Backtesting engine
└── docs/                   # Documentation (you are here)
```

## Documentation Index

| Document | Description |
|----------|-------------|
| [Architecture Overview](architecture/overview.md) | System design and component relationships |
| [ArcticDB Schema](arcticdb/schema.md) | Database structure and accounting system |
| [Strategy Manager](components/strategy-manager.md) | Strategy lifecycle management |
| [Portfolio Manager](components/portfolio-manager.md) | Position tracking and reconciliation |
| [Broker Layer](components/broker.md) | Live/backtest broker abstraction |
| [Base Strategy](components/base-strategy.md) | Strategy implementation guide |
| [Utilities](components/utilities.md) | Helper modules reference |
| [Creating Strategies](guides/creating-strategies.md) | Step-by-step strategy creation guide |

## Quick Start

1. **Start the backend:**
   ```bash
   cd backend
   python main.py
   ```

2. **With auto-reload (development):**
   ```bash
   python main.py --reload
   ```

3. **API available at:** `http://127.0.0.1:8000`

## Key Concepts

### Strategy Lifecycle
1. Strategy metadata stored in `general/strategies` table
2. `StrategyManager.start_strategy(symbol)` loads and runs strategy in dedicated thread
3. Each strategy gets unique IB `clientId` (1-99)
4. Fills/orders flow via `message_queue` to `PortfolioManager` for persistence

### Accounting System (ArcticDB)
- **Global libraries:** `general`, `market_data`, `backtests`
- **Account libraries:** One per IB account (e.g., `DU7654321`)
- **Strategy tables:** `strategy_{symbol}` tracks positions + CASH over time
- See [ArcticDB Schema](arcticdb/schema.md) for complete reference

### Broker Abstraction
- Strategies use `self.broker` for order placement
- Same interface for live trading and backtesting
- Equity allocation via `target_weight` in strategy params
