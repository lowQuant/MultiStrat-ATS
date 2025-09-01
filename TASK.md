# Current Task: PortfolioManager Implementation

## Objective
Create PortfolioManager skeleton in `backend/core/portfolio_manager.py` with ArcticDB integration points and wire it to StrategyManager for handling async queue events.

## Requirements

### PortfolioManager Core Features
- **Per-strategy position tracking**: Maintain positions grouped by strategy and symbol
- **ArcticDB integration**: Read/write position data with fast columnar operations
- **Fill event handling**: Process trade fills and update positions accordingly
- **Status change handling**: Track order status changes and maintain order history
- **Portfolio consolidation**: Aggregate positions across strategies with attribution
- **P&L calculation**: Compute realized/unrealized P&L per strategy and consolidated

### ArcticDB Schema Integration
- `positions/<STRATEGY>`: Latest position snapshots (symbol, qty, avg_cost, realized_pnl, unrealized_pnl)
- `orders/<STRATEGY>`: Order tracking (order_ref, symbol, side, qty, status, timestamp)
- `fills/<STRATEGY>`: Execution details (fill_id, order_ref, symbol, qty, price, timestamp)
- `portfolio/aggregated`: Consolidated views for UI and risk management

### Message Queue Integration
- Subscribe to StrategyManager.message_queue events
- Handle `{"type": "fill", "strategy": ..., "trade": ..., "fill": ...}` messages
- Handle `{"type": "status_change", "strategy": ..., "trade": ..., "status": ...}` messages
- Process events asynchronously without blocking strategy execution

## Implementation Steps

### 1. PortfolioManager Skeleton
- [ ] Create class with ArcticDB client integration
- [ ] Define methods for position management
- [ ] Implement fill and status change handlers
- [ ] Add portfolio consolidation methods
- [ ] Include P&L calculation framework

### 2. StrategyManager Integration
- [ ] Initialize PortfolioManager in StrategyManager.__init__()
- [ ] Forward message queue events to PortfolioManager
- [ ] Update async message handlers to call PortfolioManager methods
- [ ] Maintain backward compatibility with existing logging

### 3. Data Persistence Layer
- [ ] Position update methods with ArcticDB writes
- [ ] Order tracking with status updates
- [ ] Fill recording with execution details
- [ ] Batch write optimization for performance

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
- [ ] PortfolioManager skeleton created with all required methods
- [ ] StrategyManager successfully initializes and forwards events to PortfolioManager
- [ ] ArcticDB integration points established for all data types
- [ ] Message queue events properly routed and processed
- [ ] No breaking changes to existing strategy execution flow
