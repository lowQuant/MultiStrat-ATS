# PortfolioManager

**Location:** `core/portfolio_manager.py`

## Purpose

The PortfolioManager handles all accounting and position tracking:
- Processes fills and updates strategy positions
- Records order status changes
- Reconciles IB positions with strategy attribution
- Manages hourly position/equity snapshots
- Calculates strategy equity

## Initialization

Created by StrategyManager during startup:

```python
self.portfolio_manager = PortfolioManager(self)
```

On initialization:
- Gets ArcticDB client from StrategyManager
- Gets IB client reference
- Creates account library (`{account_id}`)
- Runs defragmentation on portfolio symbol

## Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `strategy_manager` | StrategyManager | Parent manager reference |
| `ac` | Arctic | ArcticDB client |
| `ib` | IB | Main IB client reference |
| `message_queue_ib` | IB | Message thread IB client |
| `account_id` | str | IB account ID |
| `account_library` | Library | Account-specific ArcticDB library |
| `base_currency` | str | Account base currency |
| `fx_cache` | FXCache | FX rate cache |
| `total_equity` | float | Latest total equity |

## Fill Processing

### Main Entry Point

```python
await portfolio_manager.process_fill(strategy_symbol, trade, fill)
```

**Flow:**
1. Extract fill data from IB objects
2. Record fill to `fills` table
3. Update position in `strategy_{symbol}` table
4. Update CASH position
5. Update consolidated `portfolio` table

### Position Update Logic

```python
await self._update_position_from_fill(strategy, fill_data)
```

**For new positions:**
- Create entry with fill quantity and price as avg_cost

**For existing positions:**
- **Adding to position:** Weighted average cost
- **Reducing position:** Keep avg_cost, calculate realized P&L
- **Reversing position:** New avg_cost = fill price

### CASH Updates

After each fill, CASH is updated:
```python
await update_strategy_cash(self, strategy, fill_data)
```

- **BUY:** CASH -= (quantity × price + commission)
- **SELL:** CASH += (quantity × price - commission)

## Position Reconciliation

### Purpose

Merge IB's current positions with strategy attribution from ArcticDB.

```python
df = await portfolio_manager.reconcile_positions(force_refresh=False)
```

### Caching

- 60-second memory cache
- `force_refresh=True` bypasses cache

### Reconciliation Flow

1. **Fetch IB positions** (no strategy attribution)
2. **Load last Arctic snapshot** (has strategy attribution)
3. **Merge:** For each IB position:
   - If exists in Arctic → Update with fresh market data
   - If not → Add as unattributed
4. **Handle residuals:** If IB qty ≠ sum of strategy quantities
   - Create "Discretionary" row for difference
5. **Arctic-only positions:** Positions in Arctic but not in IB
   - Create balancing Discretionary row if needed
6. **Aggregate:** Combine duplicate strategy rows
7. **Write** to `portfolio` symbol

### Residual Handling

When IB quantity doesn't match sum of strategy attributions:

```python
residual_qty = ib_qty - sum(strategy_quantities)
# If residual_qty != 0, create Discretionary row
```

## Strategy Position Queries

### Get Strategy Positions

```python
# All current positions
df = await pm.get_strategy_positions("TQQQ", current_only=True)

# Specific symbol
pos = await pm.get_strategy_positions("TQQQ", symbol="AAPL")

# Full history
df = await pm.get_strategy_positions("TQQQ", current_only=False, days_lookback=30)

# Include equity snapshots
df = await pm.get_strategy_positions("TQQQ", exclude_equity=False)
```

### Calculate Strategy Equity

```python
equity = await pm.calculate_strategy_equity("TQQQ")
# Returns: CASH + sum(position_values)
```

### Get Equity History

```python
df = await pm.get_strategy_equity_history("TQQQ", days_lookback=30)
# Returns: timestamp, equity, realized_pnl, currency
```

## Hourly Snapshots

Background task saves strategy state every hour:

### Start/Stop

```python
portfolio_manager.start_hourly_snapshots()
portfolio_manager.stop_hourly_snapshots()
```

### What Gets Saved

For each active strategy:
1. **Position snapshot** → `strategy_{symbol}` table
2. **EQUITY row** → `strategy_{symbol}` table (Mark-to-Market value)
3. **Account summary** → `account_summary` table

## Order Status Tracking

```python
await portfolio_manager.record_status_change(strategy, trade, status)
```

Records each status change event to `orders` table with:
- Order details (ID, ref, type)
- Fill progress (filled/remaining qty)
- Current status

## Frontend API

### Get Positions for Display

```python
df = await portfolio_manager.get_ib_positions_for_frontend()
```

Returns formatted DataFrame with:
- Sorted by side (Long first) then symbol
- Numeric columns as floats
- Strategy defaults to "Discretionary"

### Get Portfolio Summary

```python
summary = await portfolio_manager.get_portfolio_summary()
# Returns:
# {
#     'total_positions': 5,
#     'total_realized_pnl': 1234.56,
#     'total_unrealized_pnl': 567.89,
#     'total_pnl': 1802.45,
#     'positions': [...],
#     'timestamp': datetime
# }
```

## Cache Management

```python
portfolio_manager.clear_cache()
```

Clears:
- `_position_cache` - Strategy/symbol position cache
- `_positions_memory_cache` - Reconciled positions cache

## IB Connection Update

When IB reconnects:

```python
portfolio_manager.update_ib_connection(ib_client)
```

Updates:
- `self.ib` reference
- `self.account_id`
- `self.account_library`
- Reinitializes FX cache

## Key Helper Imports

From `utils/strategy_table_helpers.py`:
- `get_strategy_positions()` - Position queries
- `calculate_strategy_equity()` - Equity calculation
- `get_strategy_equity_history()` - Equity timeseries
- `update_strategy_cash()` - CASH updates
- `initialize_strategy_cash()` - Initial CASH setup

From `utils/position_helpers.py`:
- `create_position_dict()` - IB item → dict
- `extract_fill_data()` - Fill → dict
- `extract_order_data()` - Order → dict
- `calculate_avg_cost()` - Average cost logic
