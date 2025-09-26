# PortfolioManager Refactor Plan (Draft)

This document maps the current `backend/core/portfolio_manager.py` to the new ArcticDB architecture and persistence rules. No code changes yet; this is the implementation blueprint.

## Goals
- Align persistence with account-centric libraries (one library per `account_id`).
- Write per-spec symbols within the account library: `orders`, `fills`, `trades`, `portfolio`, `strategy_{strategy_symbol}_equity`, `strategy_{strategy_symbol}_positions`, `account_summary`.
- Enforce write/append/update semantics and index normalization with shared utils.
- Preserve legacy reconciliation behavior (residual handling, market data refresh for Arctic-only entries) while keeping per-strategy attribution.

## Open the Account Library
- In `__init__`: resolve `self.ac`, `self.ib`.
- Determine `self.account_id = ib.managedAccounts()[0]`.
- `self.account_library = self.ac.get_library(self.account_id, create_if_missing=True)`.

## Symbols and Indices (within account library)
- `orders`: time-indexed by `timestamp` (unique with ns offsets). Columns include `order_id`, `order_ref`, `status`, etc.
- `fills`: id-indexed by `fill_id`. Includes `timestamp`, `order_id`, `strategy_symbol`, `symbol`, quantities, prices.
- `trades`: id-indexed by `execution_id` (optional depending on event source; can be populated alongside `fills`).
- `portfolio`: time-indexed by `timestamp` (unique with ns offsets). Columns per row: `symbol`, `asset_class`, `strategy_symbol`, `quantity`, `average_cost`, `market_price`, `market_value`, `market_value_base`, `% of nav`, `currency`, `fx_rate`, `pnl %`.
- `strategy_{strategy_symbol}_equity`: time-indexed by `timestamp`, single `equity` column.
- `strategy_{strategy_symbol}_positions`: time-indexed by `timestamp`. Wide table: one column per instrument with the position size.
- `account_summary`: time-indexed by `timestamp` with `equity`, `pnl`, `cash`, `market_value`.

## Shared Utilities to Use (backend/utils/persistence_utils.py)
- I dont agree with your proposal. TODO: find better more generic utils.

## Method-Level Plan

### __init__
- Keep the new initialization: resolve `ac`, `ib`, `account_id`, `account_library`.
- Optionally call a light defragment/compaction routine for `portfolio` (as currently scaffolded by `_defragment_account_portfolio()`).

### _get_positions_from_ib()
- No persistence. Return a DataFrame of IB positions with base currency conversion.
- Use `FXCache` as already implemented to populate `marketValue_base` and `% of nav`.

### process_fill(strategy_symbol, trade, fill)
1) Extract normalized fill dict (existing `_extract_fill_data`).
2) `_record_fill(fill_data)` — persist to `fills` symbol:
   - Build one-row DataFrame; set id index with `set_id_index(df, 'fill_id')`.
   - First-time symbol: write; otherwise append; update only for corrections of same `fill_id`.
3) Update per-strategy positions:
   - Read last snapshot from `strategy_{strategy_symbol}_positions`.
   - Compute the new per-instrument positions given the fill.
   - Create a new timestamped row (wide) and append to `strategy_{strategy_symbol}_positions` using `normalize_strategy_timeseries_index`.
4) Optionally update `strategy_{strategy_symbol}_equity` with a new timestamp row (if equity attribution available now; otherwise later during reconciliation/account summary update).
5) Do not write to `portfolio` here (keep `portfolio` snapshots in reconciliation) unless we decide to support immediate incremental snapshots. If we do, apply `normalize_portfolio_snapshot_index` and append.

### _record_fill(fill_data)
- Target: `{account_id}` library, symbol `fills`.
- Index: `fill_id` via `set_id_index`.
- Semantics: `write` if first-time, else `append`; `update` for corrections on same id.

### record_status_change(strategy_symbol, trade, status) / _record_order_status(order_data)
- Target: symbol `orders` in account library.
- Build an event row with `timestamp` and order details (`order_id`, `order_ref`, `status`, filled/remaining qty, `avg_fill_price`).
- Use `normalize_orders_index(df)` and append a row per event (`update` only to correct same timestamp event).
- Consumers reconstruct order history by grouping on `order_id` and sorting by index.

### _get_position() and _save_position()
- Replace per-strategy `positions/<STRATEGY>` with strategy-specific symbols:
  - Read last snapshot from `strategy_{strategy_symbol}_positions` and unpivot to produce a single-symbol view when needed.
  - For saving, write a new timestamped wide row:
    - Read last snapshot (wide row) if exists.
    - Update the column for the affected instrument; leave others unchanged.
    - Append the updated row with a fresh `timestamp` using `normalize_strategy_timeseries_index`.

### get_strategy_positions(strategy_symbol)
- Read latest row from `strategy_{strategy_symbol}_positions` and unpivot to JSON-friendly list of `{symbol, quantity, avg_cost?, realized_pnl?, unrealized_pnl?}`. If only quantities are stored in the strategy table, enrich via recent fills/trades or IB query as needed.

### get_consolidated_positions()
- Read latest `portfolio` snapshot at the most recent `timestamp`.
- Aggregate per symbol as needed for UI (sum quantities and P&L across strategies while preserving attribution in rows when desired).

### reconcile_positions()
- Frequency: periodic task (e.g., hourly or on demand).
- Steps (legacy parity):
  1. Load last `portfolio` snapshot if available; otherwise bootstrap from IB.
  2. Fetch current IB positions `df_ib` (no strategy attribution).
  3. For each IB row (symbol, asset class):
     - If no Arctic entries, include IB row as-is in merged output.
     - If strategy entries exist, update them with current market data and recompute qty/avg cost using a function adapted from legacy `update_and_aggregate_data`.
     - If residual exists (IB qty != sum(strategy rows)), compute a residual row using weighted avg cost (adapt legacy `handle_residual`).
  4. Include Arctic-only positions not present in IB by refreshing market data (adapt `update_market_data_for_arcticdb_positions`).
  5. Append the reconciled rows to `portfolio` at a single snapshot `timestamp` (apply ns offsets per row to ensure unique index).
  6. Update `account_summary` (equity, pnl, cash, market_value).

## Persistence Semantics
- Use `write()` only for first-time symbol creation. Use `append()` for new timestamps (or id rows). Use `update()` to correct rows with the same index.
- Enforce index rules using `normalize_*` and `_make_unique_timestamps()` helpers.

## Edge Cases & Tests
- Multiple fills within the same second (unique `fill_id` avoids collisions).
- Orders with rapid status changes (ensure per-event `timestamp` uniqueness; ns offsets as needed).
- Short-to-long flips (average cost reset logic consistent with legacy).
- Multi-strategy same symbol with opposite sides (residual handling in reconciliation).
- Late fills and corrections (ensure `update()` paths work without duplicating rows).

## Migration Notes
- If any legacy `positions/<STRATEGY>` data exists, write a one-time migration to create `strategy_{strategy_symbol}_positions` wide rows from most recent snapshots.
- For any global `portfolio` data, re-key under each `account_id` library as a `portfolio` symbol.
