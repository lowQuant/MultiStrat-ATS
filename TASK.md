# Current Task: IB Reconciliation and Fills/Trades Processing

## Objective
Implement periodic reconciliation with IB and a robust fills/trades processing pipeline. Persist reconciled snapshots to the `portfolio` library keyed by symbol and account id, and record fills/orders while updating per‑strategy positions and consolidated portfolio views.

## Requirements

### IB Reconciliation
- Periodically fetch IB positions and reconcile with ArcticDB while preserving per‑strategy attribution.
- Persist reconciled snapshots to `portfolio` library keyed by symbol and account id.

### Fills/Trades Processing
- Process fill events and record to `fills/<STRATEGY>` with execution details.
- Track orders in `orders/<STRATEGY>` and status transitions.
- Update `positions/<STRATEGY>` snapshots and consolidated portfolio view.
- Maintain realized/unrealized P&L fields (base currency handling later).

### ArcticDB Schema Integration
- `positions/<STRATEGY>`: Latest position snapshots (symbol, qty, avg_cost, realized_pnl, unrealized_pnl)
- `orders/<STRATEGY>`: Order tracking (order_ref, symbol, side, qty, status, timestamp)
- `fills/<STRATEGY>`: Execution details (fill_id, order_ref, symbol, qty, price, timestamp)
- `portfolio` (reconciled snapshots keyed by symbol + account id)
- `portfolio/aggregated` (optional for UI consolidation)

### Message Queue Integration
- Subscribe to `StrategyManager.message_queue` events
- Handle `{"type": "fill", "strategy": ..., "trade": ..., "fill": ...}` messages
- Handle `{"type": "status_change", "strategy": ..., "trade": ..., "status": ...}` messages
- Process events asynchronously without blocking strategy execution

## Implementation Steps

### 1. Reconciliation with IB (priority)
- [ ] Implement periodic job to fetch IB positions
- [ ] Reconcile with ArcticDB, preserving per‑strategy attribution and handling residuals
- [ ] Persist reconciled snapshots to `portfolio` keyed by symbol and account id

### 2. Fills/Trades Processing (priority)
- [ ] Normalize and record fills to `fills/<STRATEGY>` and orders to `orders/<STRATEGY>`
- [ ] Update `positions/<STRATEGY>` and consolidated portfolio after each fill/status change
- [ ] Compute/accumulate realized P&L and track unrealized P&L placeholders

### 3. PortfolioManager Skeleton/Integration (supporting)
- [ ] Ensure `PortfolioManager` methods are wired from `StrategyManager` async handlers
- [ ] Batch ArcticDB writes and add basic error handling/logging

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
- [ ] Reconciled snapshots written to `portfolio` keyed by symbol and account id
- [ ] Fills and orders recorded to ArcticDB and positions updated correctly
- [ ] Consolidated portfolio reflects per‑strategy attribution
- [ ] StrategyManager forwards events; processing is non‑blocking and robust
- [ ] No breaking changes to existing strategy execution flow
