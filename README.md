# MultiStrat-ATS (MATS)

Multi-strategy Automated Trading System. Orchestrate, run, and monitor multiple automated trading strategies concurrently with clean isolation and modern web UI.

This repo modernizes an older IB multi-strategy project with a new FastAPI backend and React/TypeScript frontend, while preserving the proven design: per‑strategy isolation, centralized coordination, and ArcticDB-backed research/portfolio data.

## Stack
- Backend: FastAPI (async), ib_async (preferred fork of ib_insync), ArcticDB, WebSockets
- Frontend: React + TypeScript + Vite + shadcn/ui
- Runtime isolation: per‑strategy threads with their own event loops + centralized message queue

## Architecture Overview

The backend centers around a small set of core modules under `backend/`:

- `core/strategy_manager.py`
  - Owns the master IB connection and strategy lifecycle.
  - Spawns strategies, assigning unique `client_id`s per strategy (thread isolation).
  - Provides a thread-safe `message_queue` consumed by an internal async loop to broadcast logs/updates over WebSockets.
  - Routes messages to async handlers:
    - `notify_order_placement_async()`
    - `handle_fill_event_async()`
    - `handle_status_change_async()`

- `strategies/base_strategy.py`
  - Abstract base for all strategies; each strategy runs in its own thread with its own asyncio event loop and IB session.
  - Handles IB connect/disconnect via `utils/ib_connection.py`.
  - When orders fill or status changes, strategies enqueue messages to `StrategyManager.message_queue` rather than calling manager methods directly.
  - Subclasses implement `initialize_strategy()` and `run_strategy()`.

- `strategies/*_strategy.py`
  - Example strategies (`AAPLStrategy`, `GOOGLStrategy`, `METAStrategy`) demonstrate contract qualification and simple market orders.
  - Event hooks `on_fill()` and `on_status_change()` call `super()` which enqueues events to the manager’s async handlers.

- `core/arctic_manager.py`
  - Provides `initialize_db()` and a lazy accessor `get_ac()` used by the system to connect to ArcticDB under `backend/ArcticDB/`.
  - Designed to mirror the old project’s utils while fitting Async + StrategyManager flows.

- `core/log_manager.py`
  - Centralized logging utility used throughout the backend.
  - Feeds both server logs and WebSocket log streaming to the UI.

- `core/trade_manager.py`
  - Created on successful master IB connection.
  - Will aggregate order/trade routing helpers shared across strategies (extensible for multi-broker in future).

- `routes/`
  - FastAPI endpoints for connection, settings, and strategy control.
  - WebSocket endpoints stream logs and status to the frontend in real time.

- `utils/ib_connection.py` and `utils/settings.py`
  - IB connection helpers for `ib_async` with client id and host/port wiring.
  - Centralized runtime configuration (env, defaults).

### Data Flow (high level)
1. Frontend requests actions (connect, start/stop strategies) via REST.
2. `StrategyManager` starts strategies as separate threads; each strategy creates its own event loop and IB session using its unique `client_id`.
3. Strategies place orders and subscribe to `Trade` events. On fills/status updates they enqueue messages.
4. `StrategyManager` processes the queue with an internal async loop and logs to WebSocket subscribers while updating shared state as needed.

This preserves the old project’s guarantees (isolation, centralized coordination) while being fully async-compatible.

## ArcticDB Plan

We will use ArcticDB to store per‑strategy and consolidated portfolio data with fast, columnar reads:

- Libraries
  - `positions/<STRATEGY>`: latest position snapshots per strategy (by symbol), including qty, avg cost, realized/unrealized P&L.
  - `orders/<STRATEGY>`: submitted orders, statuses, and refs for traceability.
  - `fills/<STRATEGY>`: execution-level detail with timestamps and prices.
  - `portfolio/aggregated`: consolidated views across strategies for UI and risk.

- Write path
  - Strategy events (fills/status) are enqueued; `StrategyManager`/future `PortfolioManager` writes normalized records to ArcticDB.
  - Writes are batched to reduce overhead; schema includes `strategy`, `symbol`, `ts`, `qty`, `avg_cost`, `side`, `order_ref`, etc.

- Read path
  - Frontend queries REST endpoints for positions and P&L. The backend queries ArcticDB per strategy and returns both per‑strategy and aggregated views.
  - Emphasis on per‑strategy attribution (one strategy can be long while another is short the same symbol) and fast rollups.

- Compatibility
  - Aligned with `ib_async` object models; mapping is straightforward from `Trade`/`Fill` to row-based ArcticDB writes.

## Future: PortfolioManager

A dedicated `PortfolioManager` will maintain a live, aggregated view of positions grouped by strategy and symbol:

- Subscribe to the same queue or a dedicated bus for trade/fill events.
- Update per‑strategy holdings and compute consolidated totals with attribution.
- Enforce risk limits and provide P&L analytics hooks.

### Queue → PortfolioManager flow
- Strategies enqueue `{"type": "fill"|"status_change", ...}` into `StrategyManager.message_queue` (see `strategies/base_strategy.py`).
- `StrategyManager.handle_message_async()` routes to async handlers; these will call into `PortfolioManager` to:
  - Persist normalized fills/orders to ArcticDB libraries per strategy.
  - Recompute per‑strategy positions (qty, average price, P&L) and update consolidated views.

### Near-term priorities
- IB reconciliation
  - Periodically fetch IB positions and reconcile with ArcticDB while preserving per‑strategy attribution.
  - Persist reconciled snapshots to the `portfolio` library keyed by symbol and account id.
- Fills and trades processing
  - Process fills from strategies, record trades/fills to ArcticDB, and update per‑strategy positions and consolidated portfolio.

### Matching positions (legacy logic carried forward)
We will adapt the legacy `match_ib_positions_with_arcticdb()` to the new design. High‑level algorithm:

1. If the account exists in ArcticDB, load the last saved portfolio snapshot; otherwise, fetch IB positions and save them as the initial snapshot.
2. Always fetch current IB positions into `df_ib`.
3. For each IB position row (`symbol`, `asset class`):
   - If no matching entries exist in ArcticDB, append the IB row (new strategy/symbol entry).
   - If matches exist, call an update routine to recalc strategy‑level quantities and average prices; append updated rows.
   - If residuals exist (IB position != sum of Arctic strategy entries), compute and append a residual adjustment row.
4. For ArcticDB positions not present in the current IB set (e.g., net‑zero at broker but strategy attribution retained), refresh market data and keep the strategy rows to preserve attribution.
5. Save merged portfolio back to ArcticDB and persist account P&L.

This preserves per‑strategy attribution even when broker net positions are flat, and keeps average cost updates consistent with fills.

## Setup

### Python environment
We recommend a dedicated Conda env (e.g., `MATS`) and pinned dependencies:

```bash
# create env (example)
conda create -n MATS python=3.11 -y
conda activate MATS

# install backend deps
pip install -r backend/requirements.txt
```

For Interactive Brokers, ensure TWS/IBG is running and API access is enabled (127.0.0.1:7497 by default).

### Frontend
```bash
cd frontend
npm i
npm run dev
```

## Running

```bash
# from repo root
uvicorn backend.main:app --reload
```

The web UI connects via REST/WebSockets for live logs and status. Use the Strategy tab to start/stop strategies.

## Development Notes

- ib_async/eventkit are pinned in `backend/requirements.txt` for compatibility with per‑thread event loops.
- Strategies must not call manager methods directly for fills/status; they should enqueue messages (see `BaseStrategy.on_fill()` and `on_status_change()`).
- The manager runs a dedicated thread and uses an internal asyncio loop to process the queue and broadcast via WebSockets.

## Roadmap (phased)

1) Core Backend Setup — done
   - FastAPI backend, ib_async connection utils, StrategyManager, logging, WebSocket streaming.
2) Frontend Integration — done
   - React/TS UI, real-time connection status, log viewer, connect/disconnect.
3) Strategy Management — in progress
   - Creation, lifecycle, per‑strategy threads with unique clientIds, configurable params.
4) Portfolio & Risk Management — next
   - PortfolioManager with per‑strategy attribution, ArcticDB-backed positions, risk controls, P&L.
5) Trading Execution
   - Full order placement/management, fill handling, reporting.
6) Analytics & Monitoring
   - Performance analytics, strategy comparison, historical data analysis.

## License
MIT
