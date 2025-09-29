# Current Task: Persistence Refactor, Position Matching Parity, and Reconciliation

problem solved! Now do the below:

Next steps:
Build targeted upsert for the portfolio symbol by querying just the affected (symbol, asset_class) rows and applying the appropriate open/close/adjust logic.
Wire the new helper(s) into process_fill() so that fills automatically refresh both the strategy table and the account-level portfolio snapshot.
Provide a short verification checklist once the above is in place.


### Portfolio Current-State Outline (Option 1)
- Drop TTL gates in `PortfolioManager.reconcile_positions()` and persist the latest consolidated view on every run.
- Convert the `portfolio` symbol to use a numeric index, keeping `timestamp` as a normal column for auditing.
- Refactor `_update_consolidated_portfolio()` to accept full `fill_data` and perform targeted upserts for create/increase/decrease/close scenarios.
- Call the consolidated upsert helper from `process_fill()` immediately after strategy-level updates.
- Maintain history at the strategy level via existing per-strategy tables; rely on `fills`/`orders` for event reconstruction.
- Validate with a focused checklist covering open/increase/decrease/close cases and zero-quantity removals.



## Objective
Fix ArcticDB persistence semantics first, align storage structure with the updated design (account‑scoped symbols and timestamp indices), and then implement precise position matching and IB reconciliation adapted from the legacy implementation. Persist reconciled snapshots to the `portfolio` library keyed by `account_id`, and record fills/orders correctly while updating per‑strategy positions and consolidated portfolio views.

## Requirements

### Persistence Refactor (blocking)
- Refactor fills and orders to single libraries keyed by `account_id` as the Arctic symbol; DataFrame index is `timestamp`.
- Use `write()` only for first‑time symbol creation; use `append()` for new timestamped data; use `update()` to correct existing timestamps.
- Normalize indices (timezone‑aware, unique; add nanosecond offsets for duplicates).

### IB Reconciliation
- Periodically fetch IB positions and reconcile with ArcticDB while preserving per‑strategy attribution.
- Persist reconciled snapshots to `portfolio` library keyed by `account_id` (as symbol).

### Fills/Trades Processing
- Process fill events and record to `fills` with execution details (symbol = `account_id`).
- Track orders in `orders` with status transitions (symbol = `account_id`).
- Update `positions/<STRATEGY>` snapshots and consolidated portfolio view.
- Maintain realized/unrealized P&L fields (base currency handling later).

### ArcticDB Schema Integration
- `fills`: Execution details (fill_id, order_ref, symbol, strategy, qty, price, commission, timestamp; symbol in row; symbol = `account_id` at Arctic level)
- `orders`: Order tracking (order_id, perm_id, order_ref, symbol, status, side, qtys, avg_fill_price, timestamp; symbol in row; symbol = `account_id` at Arctic level)
- `positions/<STRATEGY>`: Latest position snapshots (symbol, qty, avg_cost, realized_pnl, unrealized_pnl, last_updated)
- `portfolio`: Reconciled snapshots keyed by `account_id` (Arctic symbol), rows contain symbol, strategy, qty, averageCost, PnL, etc.
- `portfolio/aggregated` (optional for UI consolidation)

### Message Queue Integration
- Subscribe to `StrategyManager.message_queue` events
- Handle `{"type": "fill", "strategy": ..., "trade": ..., "fill": ...}` messages
- Handle `{"type": "status_change", "strategy": ..., "trade": ..., "status": ...}` messages
- Process events asynchronously without blocking strategy execution

## Implementation Steps

### 1. Persistence Refactor (priority)
- [ ] Audit all `lib.write()` and `.write(` usages in `backend/` and replace with `append()` for new timestamps; reserve `write()` for first‑time symbols.
- [ ] Introduce `update()` where we correct existing timestamps (e.g., status corrections, late fills).
- [ ] Create normalization utility for timestamp indices (tz‑aware, unique, ns offsets) and apply before persisting.
- [ ] Refactor `fills` and `orders` to use `account_id` as Arctic symbol; index = `timestamp`.

### 2. Reconciliation with IB (priority)
- [ ] Implement periodic job to fetch IB positions
- [ ] Reconcile with ArcticDB, preserving per‑strategy attribution and handling residuals
- [ ] Persist reconciled snapshots to `portfolio` keyed by `account_id`

### 3. Fills/Trades Processing (priority)
- [ ] Normalize and record fills to `fills` and orders to `orders` (symbol = `account_id`)
- [ ] Update `positions/<STRATEGY>` and consolidated portfolio after each fill/status change
- [ ] Compute/accumulate realized P&L and track unrealized P&L placeholders

### 4. PortfolioManager Skeleton/Integration (supporting)
- [ ] Ensure `PortfolioManager` methods are wired from `StrategyManager` async handlers
- [ ] Batch ArcticDB writes and add basic error handling/logging

## Legacy vs New Matching: Key Differences to Address
- Legacy stores `portfolio` with Arctic symbol = `account_id`, appends snapshots, and computes residual rows when IB qty != sum of strategy rows. New code currently writes per‑strategy positions under `positions/<STRATEGY>` and uses `write()` in several places (risk of overwrite). We will:
  - Preserve per‑strategy attribution in `positions/<STRATEGY>`.
  - Maintain `portfolio` snapshots for reconciliation/risk with Arctic symbol = `account_id`.
  - Port residual handling (`handle_residual`) and market data refresh for Arctic‑only entries.

## Audit Plan (where to begin)
- Search for incorrect persistence patterns:
  - `.write(` in `backend/` and `backend/routes/` (hotspots: `core/portfolio_manager.py::_record_fill`, `::_record_order_status`, `::_save_position`).
  - Replace with `append()` for new timestamped rows; keep `write()` only for first‑time symbol creation.
  - Add `update()` where a correction of an existing timestamp is intended.
- Define Arctic symbols and indices:
  - `fills`, `orders`: symbol = `account_id`, index = `timestamp`.
  - `positions/<STRATEGY>`: symbol = asset symbol; index = `last_updated` or `timestamp`.
  - `portfolio`: symbol = `account_id`, index = `timestamp`.
- Implement a shared index normalization helper.

## Test Plan (edge cases)
- Partial fills arriving out‑of‑order; ensure index normalization and `append()` semantics.
- Short covering to flat then long; avg cost resets as designed (legacy parity).
- Multi‑strategy on same symbol with opposite sides; verify reconciliation preserves attribution and residuals.
- Residual calculation correctness and rounding across currencies (FX handled later).
- Order status corrections (cancel/replace) lead to `update()` not duplicate `append()`.
- Bootstrap path: no Arctic snapshot exists yet; initial write then subsequent appends.

## Technical Considerations

### Thread Safety
- PortfolioManager will be called from StrategyManager's async message processing thread
- ArcticDB operations are thread-safe
- Use async/await patterns for non-blocking operations

### Performance
- Batch ArcticDB writes to reduce I/O overhead
- Cache frequently accessed position data
- Optimize queries for real-time portfolio views

### Attribution Logic
- Maintain per-strategy position attribution even when net broker position is zero
- Handle cases where one strategy is long while another is short the same symbol
- Preserve average cost basis calculations across fills

## Success Criteria
- [ ] Correct append/update semantics for all persistence paths
- [ ] Reconciled snapshots written to `portfolio` keyed by `account_id`
- [ ] Fills and orders recorded to ArcticDB and positions updated correctly
- [ ] Consolidated portfolio reflects per‑strategy attribution
- [ ] StrategyManager forwards events; processing is non‑blocking and robust
- [ ] No breaking changes to existing strategy execution flow
