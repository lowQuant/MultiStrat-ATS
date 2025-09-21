# Broker Architecture Refactoring Plan

## Current Issues

1. **Duplicate Event Handling**
   - `base_strategy.py`: Has `on_fill()` and `on_status_change()` that push to message_queue
   - `live_broker.py`: Subscribes to `orderStatusEvent` and `fillEvent` 
   - Both are handling the same IB events, causing duplication

2. **Missing Position Reconciliation**
   - Old `portfoliomanager.py` has sophisticated `match_ib_positions_with_arcticdb()` logic
   - This reconciles IB positions with ArcticDB stored positions
   - Current brokers don't implement this critical functionality

3. **Incorrect Backtest Storage**
   - Currently saving to account libraries like `BT_TEST_001`
   - Should save to `backtests` library with proper naming convention
   - Format should be: `{strategy}_{date}_{description}` (e.g., `AAPL_20250918_ema_crossover`)

## Proposed Solution

### 1. Centralized Event Handling

**Remove duplicate subscriptions:**
- LiveBroker should NOT subscribe to IB events directly
- Events flow through base_strategy → message_queue → portfolio_manager
- Portfolio manager handles all persistence

**Event Flow:**
```
IB Events → base_strategy handlers → message_queue → strategy_manager → portfolio_manager
```

### 2. Position Reconciliation

**Integrate position matching logic:**
- Move `match_ib_positions_with_arcticdb()` to portfolio_manager
- Call on startup and periodically during trading
- Handle residuals and unassigned positions properly

### 3. Proper Backtest Storage

**Backtest Results Structure:**
```python
# In backtests library:
symbol = f"{strategy}_{date}_{description}"

# Data stored:
- equity_curve: Timestamped equity values
- trades: All executed trades with P&L
- positions: Position snapshots over time
- metrics: Sharpe, max drawdown, returns, etc.
```

## Implementation Changes

### 1. Update LiveBroker
- Remove event subscriptions
- Focus on order placement and equity management
- Let base_strategy handle events

### 2. Update BacktestBroker
- Save results to `backtests` library, not account libraries
- Use proper naming convention
- Store comprehensive backtest metrics

### 3. Update base_strategy
- Keep event handlers as the single source
- Ensure all events go through message_queue

### 4. Enhance portfolio_manager
- Add position reconciliation from old code
- Handle residual positions
- Update market data for stale positions

## Benefits

1. **No Duplicate Events**: Single path for all order/fill events
2. **Accurate Positions**: Reconciliation ensures ArcticDB matches IB
3. **Proper Backtesting**: Results stored correctly for analysis
4. **Cleaner Architecture**: Clear separation of concerns
