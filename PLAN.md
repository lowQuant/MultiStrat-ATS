# MATS Modernization Plan

## Project Overview
Multi-strategy Automated Trading System (MATS) modernizes an older IB multi-strategy project with:
- **Backend**: FastAPI (async), ib_async, ArcticDB, WebSockets
- **Frontend**: React + TypeScript + Vite + shadcn/ui
- **Architecture**: Per-strategy isolation, centralized coordination, ArcticDB-backed portfolio data

## Development Phases

### Phase 1: Core Backend Setup ✅ COMPLETED
- [x] FastAPI backend with async support
- [x] IB connection utilities (ib_async integration)
- [x] StrategyManager for centralized coordination
- [x] Basic logging and WebSocket streaming
- [x] TradeManager initialization
- [x] ArcticManager for database operations

### Phase 2: Frontend Integration ✅ COMPLETED
- [x] React/TypeScript frontend with shadcn/ui
- [x] TradingDashboard with real-time connection status
- [x] LogViewer with WebSocket log streaming
- [x] IB connect/disconnect functionality
- [x] Clean logging without duplicates

### Phase 3: Strategy Management ✅ COMPLETED
- [x] Strategy creation and lifecycle management
- [x] Individual strategy threads with unique clientIds
- [x] BaseStrategy abstract class with event handling
- [x] Strategy discovery and dynamic loading
- [x] Start/stop individual strategies
- [x] Message queue for async event handling

### Phase 4: Portfolio & Risk Management 🔄 IN PROGRESS
- [ ] **PortfolioManager implementation** (Current Task)
  - [ ] Skeleton with ArcticDB integration points
  - [ ] Methods to handle fills and status changes
  - [ ] Per-strategy position tracking
  - [ ] Consolidated portfolio views
- [ ] Real-time portfolio tracking
- [ ] Position management with attribution
- [ ] Risk controls and limits
- [ ] P&L calculation (realized/unrealized)
- [ ] Portfolio reconciliation with IB positions

### Phase 5: Trading Execution
- [ ] Enhanced order placement and management
- [ ] Trade execution monitoring
- [ ] Fill handling and reporting
- [ ] Order status tracking
- [ ] Multi-broker support preparation

### Phase 6: Analytics & Monitoring
- [ ] Performance analytics
- [ ] Strategy performance comparison
- [ ] Historical data analysis
- [ ] Reporting dashboard
- [ ] Risk metrics and alerts

## ArcticDB Schema Design

### Libraries Structure
- `positions/<STRATEGY>`: Latest position snapshots per strategy
- `orders/<STRATEGY>`: Submitted orders, statuses, and refs
- `fills/<STRATEGY>`: Execution-level detail with timestamps
- `portfolio/aggregated`: Consolidated views across strategies

### Data Flow
1. **Write Path**: Strategy events → StrategyManager queue → PortfolioManager → ArcticDB
2. **Read Path**: Frontend REST queries → Backend ArcticDB queries → Aggregated responses
3. **Attribution**: Per-strategy tracking (one strategy long, another short same symbol)

## Key Technical Decisions

### Thread Isolation
- Each strategy runs in its own thread with unique clientId
- Isolated asyncio event loops per strategy
- Message queue for cross-thread communication

### Async Architecture
- FastAPI handles both sync/async operations
- ib_async (maintained fork) for IB API integration
- WebSocket streaming for real-time updates

### Data Persistence
- ArcticDB for fast columnar reads/writes
- Dynamic schema for flexible position data
- Batch writes to reduce overhead

## Current Status
**Phase 4 - Portfolio Management**: Implementing PortfolioManager skeleton with ArcticDB integration and wiring to StrategyManager message queue.
