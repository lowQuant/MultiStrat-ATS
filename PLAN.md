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
  - [ ] ArcticDB persistence refactor (append/update semantics, account-scoped symbols)
  - [ ] Methods to handle fills and status changes
  - [ ] Per-strategy position tracking with precise attribution
  - [ ] Consolidated portfolio views
- [ ] Real-time portfolio tracking
- [ ] Position management with attribution
- [ ] Risk controls and limits
- [ ] P&L calculation (realized/unrealized)
- [ ] Portfolio reconciliation with IB positions

#### Next Focus (Priority)
- [ ] Persistence correctness first (blocking)
  - Audit all ArcticDB writes to replace `write()` with `append()` where adding new timestamped rows and introduce `update()` where correcting existing timestamps.
  - Adopt account-scoped symbols: for `fills` and `orders`, the Arctic symbol is the brokerage `account_id`; the DataFrame index is `timestamp`.
  - Ensure strict index hygiene (unique, monotonic where required; nanosecond offsetting for duplicates).
- [ ] Reconciliation with IB
  - Periodically fetch IB positions and reconcile with ArcticDB while preserving strategy attribution.
  - Persist reconciled snapshots to `portfolio` library keyed by `account_id` (as symbol) with per-row symbol/strategy columns.
- [ ] Fills and trades processing
  - Process fills from strategies, record trades/fills in ArcticDB under a single `fills` library (symbol = `account_id`).
  - Record order status transitions under a single `orders` library (symbol = `account_id`).
  - Update per-strategy positions and consolidated portfolio accordingly.

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
- `fills`: All fills across strategies; Arctic symbol = `account_id`; index = `timestamp`.
- `orders`: All orders across strategies; Arctic symbol = `account_id`; index = `timestamp`.
- `positions/<STRATEGY>`: Latest per-strategy position snapshots (maintained for attribution and faster lookups).
- `portfolio`: Reconciled snapshots keyed by `account_id` (as symbol); rows contain symbol, strategy, qty, averageCost, PnL, etc.
- `portfolio/aggregated` (optional): Consolidated views across strategies for UI.

Note: If libraries grow too large, we can shard by year in tidy-up scripts (e.g., `account_id_YYYY` symbols). Not required initially.

### Data Flow
1. **Write Path**: Strategy events → StrategyManager queue → PortfolioManager → ArcticDB
   - Fills → `fills` (symbol = `account_id`) using `append()` for new timestamps; `update()` for corrections.
   - Orders → `orders` (symbol = `account_id`) using `append()` for new timestamps; `update()` for corrections.
   - Positions → `positions/<STRATEGY>` with `append()` of snapshots; `update()` for corrections.
   - Reconciled portfolio → `portfolio` (symbol = `account_id`) via `append()` per reconciliation run.
2. **Read Path**: Frontend REST queries → Backend ArcticDB queries → Aggregated responses.
3. **Attribution**: Per-strategy tracking preserved even when broker net is flat.

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
- Strict use of `write()` only for first-time creation of a symbol; otherwise `append()` for new timestamps and `update()` for corrections
- Account-scoped symbols for `fills` and `orders` to simplify ingestion and querying
- Unique timestamp index enforced; when ingesting multiple rows for same ts, add ns offsets
- Batch writes to reduce overhead

## Current Status
**Phase 4 - Portfolio Management**: Implementing PortfolioManager with corrected ArcticDB persistence (append/update), account-scoped `fills`/`orders`, and wiring to StrategyManager message queue. Next: parity with legacy reconciliation logic and edge-case tests.

## Migration and Audit Checklist (blocking before coding reconciliation)
- [ ] Identify all usages of `lib.write()` in `backend/` and replace with `append()` for new timestamped rows; reserve `write()` for first-time symbol creation only.
- [ ] Introduce `update()` where we correct existing timestamps (e.g., order status retractions, fill corrections).
- [ ] Refactor `fills` and `orders` to single libraries with Arctic symbol = `account_id`; DataFrame indexed by `timestamp`.
- [ ] Ensure `positions/<STRATEGY>` snapshots are appended, not overwritten; add `last_updated` as column if needed.
- [ ] Add index normalization utility to guarantee unique, timezone-aware timestamps with ns offsetting.
- [ ] Add lightweight read paths for UI aggregation and pagination.

## Reconciliation Algorithm (legacy parity, adapted)
1. Load latest Arctic snapshot for `account_id` from `portfolio`; if missing, bootstrap from IB.
2. Fetch current IB positions as `df_ib` (no strategy attribution).
3. For each IB row (symbol, asset class):
   - If no Arctic entries for symbol, append the IB row into `df_merged`.
   - If Arctic entries exist, update strategy rows with current market data and recompute qty/avg cost; append updated rows.
   - If residual exists (IB qty != sum of strategy rows), compute residual row with weighted avg cost and append.
4. For Arctic positions absent in the IB set (e.g., net-zero but attribution retained), refresh market data and keep rows.
5. Append reconciled `df_merged` to `portfolio` (symbol = `account_id`). Persist PnL to `pnl`.

## Edge Cases to Validate
- Partial fills and multiple fills per second (index collisions)
- Short-to-long flips (avg cost reset behavior)
- Multi-strategy same symbol, opposite sides
- Residual handling and rounding
- Cancel/replace order flows and status corrections (use `update()`)
- Late fills/out-of-order events
