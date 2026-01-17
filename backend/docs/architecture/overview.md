# Architecture Overview

## System Design

MATS follows a modular architecture with clear separation of concerns:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           React Frontend                                    │
│                    (http://localhost:5173)                                  │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ HTTP/WebSocket
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend (main.py)                           │
│                      (http://127.0.0.1:8000)                                │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Routes Layer                                                              │
│   ┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐     │
│   │strategies│portfolio │connection│ settings │ arctic   │ backtest │     │
│   └────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬─────┘     │
│        │          │          │          │          │          │            │
│        └──────────┴──────────┴──────────┼──────────┴──────────┘            │
│                                         ▼                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                      StrategyManager                                 │  │
│   │  - Master IB connection (clientId=0)                                │  │
│   │  - Strategy lifecycle (start/stop)                                  │  │
│   │  - Message queue processing                                         │  │
│   │  - TradeManager & PortfolioManager ownership                        │  │
│   └───────────────────────────┬─────────────────────────────────────────┘  │
│                               │                                             │
│         ┌─────────────────────┼─────────────────────┐                      │
│         ▼                     ▼                     ▼                      │
│   ┌───────────┐       ┌───────────────┐     ┌────────────┐                │
│   │TradeManager│      │PortfolioManager│     │  Strategies │               │
│   └───────────┘       │               │     │  (threads)  │               │
│                       │ - Fills       │     └──────┬──────┘               │
│                       │ - Orders      │            │                       │
│                       │ - Positions   │            ▼                       │
│                       │ - Reconcile   │     ┌────────────┐                │
│                       └───────┬───────┘     │LiveBroker/ │                │
│                               │             │BacktestBrkr│                │
│                               ▼             └──────┬─────┘                │
│                       ┌───────────────┐            │                       │
│                       │   ArcticDB    │◀───────────┘                       │
│                       └───────────────┘                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                          ┌───────────────────┐
                          │  IB Gateway/TWS   │
                          │   (port 7497)     │
                          └───────────────────┘
```

## Core Components

### 1. StrategyManager (`core/strategy_manager.py`)

The central orchestrator that:
- Maintains master IB connection (`clientId=0`)
- Owns `PortfolioManager` and `TradeManager` instances
- Manages strategy lifecycle (load, start, stop)
- Processes message queue for fill/order events
- Reads strategy metadata from `general/strategies` table

**Key Attributes:**
- `ib_client` - Master IB connection
- `message_queue_ib_client` - Separate IB connection for message thread (`clientId=99`)
- `active_strategies` - Dict of running strategy instances
- `portfolio_manager` - Shared PortfolioManager instance
- `ac` - ArcticDB client

### 2. PortfolioManager (`core/portfolio_manager.py`)

Handles all accounting and position tracking:
- Processes fills and updates positions
- Records order status changes
- Reconciles IB positions with strategy attribution
- Manages hourly position snapshots
- Calculates strategy equity

**Key Features:**
- 60-second memory cache for positions
- FX conversion via `FXCache`
- Residual handling for unattributed positions ("Discretionary")

### 3. BaseStrategy (`obj/base_strategy.py`)

Abstract base class all strategies inherit:
- Runs in dedicated thread with own event loop
- Gets unique IB `clientId` (1-99)
- Initializes appropriate broker (Live/Backtest)
- Provides order placement wrappers
- Handles market data retrieval

**Key Methods:**
- `initialize_strategy()` - Setup (abstract)
- `run_strategy()` - Main logic (abstract)
- `place_order()` - Order with event handlers
- `get_equity()` - Strategy allocation
- `get_data()` - Market data from ArcticDB/IB

### 4. Broker Layer (`broker/`)

Unified interface for live and backtest execution:

| Class | Purpose |
|-------|---------|
| `Broker` (ABC) | Defines interface + equity logic |
| `LiveBroker` | IB execution via `ib_async` |
| `BacktestBroker` | Simulated execution |

**Equity Resolution:**
1. Check `strategy_{symbol}` table for explicit equity
2. Fallback: `target_weight × total_equity`

## Data Flow

### Order Placement Flow
```
Strategy.place_order()
    │
    ├── Qualify contract
    ├── Create Order object
    ├── ib.placeOrder()
    │
    ├── Attach fillEvent handler ──▶ on_fill()
    │                                    │
    │                                    ▼
    └── Attach statusEvent handler   message_queue.put()
                                         │
                                         ▼
                              StrategyManager.process_messages()
                                         │
                                         ▼
                              PortfolioManager.process_fill()
                                         │
                              ┌──────────┴──────────┐
                              ▼                     ▼
                        _record_fill()    _update_position_from_fill()
                              │                     │
                              ▼                     ▼
                        ArcticDB/fills    strategy_{symbol} table
```

### Position Reconciliation Flow
```
reconcile_positions()
    │
    ├── _get_positions_from_ib()  ──▶ Raw IB positions (no strategy)
    │
    ├── _load_last_portfolio_snapshot() ──▶ Last Arctic state (with strategy)
    │
    ├── Merge: Update Arctic entries with fresh IB market data
    │
    ├── Handle residuals (IB qty ≠ sum of strategy attributions)
    │
    ├── Aggregate duplicate rows
    │
    └── Write to {account_id}/portfolio
```

## IB Connection Architecture

Multiple IB connections with distinct `clientId` values:

| clientId | Owner | Purpose |
|----------|-------|---------|
| 0 | StrategyManager | Master connection, routes, portfolio queries |
| 99 | Message Queue Thread | Fill/order persistence in separate thread |
| 1-98 | Strategies | One per running strategy |

## Threading Model

```
Main Thread (FastAPI/uvicorn)
    │
    ├── StrategyManager
    │       │
    │       └── Message Processor Thread (daemon)
    │               └── Own event loop + IB client (clientId=99)
    │
    └── Strategy Threads (one per active strategy)
            └── Own event loop + IB client (clientId=N)
```

Each strategy runs in isolation with:
- Dedicated `asyncio` event loop
- Own IB connection
- Access to shared `StrategyManager` for message queue and ArcticDB
