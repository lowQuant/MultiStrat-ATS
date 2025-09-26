# ArcticDB Persistence Schema and Conventions

This document defines the schemas, indices, and persistence rules for ArcticDB libraries used by MATS.

## Global Conventions

- Index timezone: All timestamps are timezone-aware in UTC.
- Index uniqueness: Indices must be unique per Arctic symbol. If collisions occur, add nanosecond offsets to break ties.
- Write semantics:
  - `write(symbol, df)`: only for first-time creation of a symbol.
  - `append(symbol, df)`: for adding new rows with new timestamps/ids.
  - `update(symbol, df)`: for correcting existing rows at the same timestamps/ids.
- Operational hierarchy:
  - One ArcticDB library per trading account, named by `account_id` (e.g., `DU7654321`).
  - Within each `account_id` library, symbols include: `account_summary`, `portfolio`, `orders`, `fills`, `trades`, `strategy_{strategy_symbol}_equity`, `strategy_{strategy_symbol}_positions`.
  - The legacy `positions/<STRATEGY>` hierarchy is replaced by `strategy_{strategy_symbol}_equity` and `strategy_{strategy_symbol}_positions` symbols inside the `account_id` library.

## Libraries

### fills
- Purpose: Persist all executions (fills) across strategies for one brokerage account.
- Arctic library: `{account_id}`
- Arctic symbol: `fills`
- Index: `fill_id` (string or int, unique)
- Columns (required):
  - `timestamp`: datetime (UTC)
  - `order_id`: int
  - `strategy_symbol`: str
  - `symbol`: str
  - `action`: str (BOT | SLD)
  - `quantity`: float
  - `price`: float
  - `commission`: float
  - `order_ref`: str
  - `perm_id`: int

### orders
- Purpose: Persist order placements and status transitions.
- Arctic library: `{account_id}`
- Arctic symbol: `orders`
- Index: `timestamp` (UTC, unique; add ns offsets to avoid collisions)
- Columns (required):
  - `timestamp`: datetime (UTC)
  - `order_id`: int
  - `perm_id`: int
  - `order_ref`: str
  - `strategy_symbol`: str
  - `symbol`: str
  - `action`: str (BUY | SELL)
  - `quantity`: float
  - `order_type`: str
  - `status`: str
  - `avg_fill_price`: float
  - `filled_quantity`: float
  - `remaining_quantity`: float

### strategy_{strategy_symbol}_equity
- Purpose: Timeseries of equity explicitly allocated to a single strategy.
- Arctic library: `{account_id}`
- Arctic symbol: `strategy_{strategy_symbol}_equity`
- Index: `timestamp` (UTC, unique)
- Columns (required):
  - `equity`: float

### strategy_{strategy_symbol}_positions
- Purpose: Historical portfolio snapshots for a single strategy.
- Arctic library: `{account_id}`
- Arctic symbol: `strategy_{strategy_symbol}_positions`
- Index: `timestamp` (UTC)
- Columns (example): One column per held instrument symbol with position size as value.

### portfolio
- Purpose: Historical snapshots of the entire account's positions (consolidated view).
- Arctic library: `{account_id}`
- Arctic symbol: `portfolio`
- Index: `timestamp` (UTC, unique; add ns offsets per row to maintain uniqueness)
- Columns (required):
  - `symbol`: str
  - `asset_class`: str
  - `strategy_symbol`: str
  - `quantity`: float
  - `average_cost`: float
  - `market_price`: float
  - `market_value`: float
  - `market_value_base`: float
  - `% of nav`: float
  - `currency`: str
  - `fx_rate`: float
  - `pnl %`: float
  

### account_summary
- Purpose: Daily/periodic timeseries of high-level account metrics.
- Arctic library: `{account_id}`
- Arctic symbol: `account_summary`
- Index: `timestamp` (UTC, unique)
- Columns (required):
  - `equity`: float
  - `pnl`: float
  - `cash`: float
  - `market_value`: float

### trades
- Purpose: Comprehensive log of executed trades.
- Arctic library: `{account_id}`
- Arctic symbol: `trades`
- Index: `execution_id` (string, unique)
- Columns (required):
  - `timestamp`: datetime (UTC)
  - `strategy_symbol`: str
  - `symbol`: str
  - `action`: str (BUY/SELL or BOT/SLD)
  - `quantity`: float
  - `price`: float

## Persistence Rules by Symbol (within `{account_id}` library)

- `fills`:
  - Append new fill rows (unique `fill_id`).
  - Use `update()` only to correct a specific `fill_id` row.
- `orders`:
  - Append a new row for each placement/status change event at its event `timestamp`.
  - Use `update()` to correct a specific event row by reusing the exact `timestamp` (index).
  - Note: `order_id` is stored as a column. Reading can group/filter by `order_id` to reconstruct order history.
- `trades`:
  - Append new rows per `execution_id`.
  - Corrections use `update()` on the same `execution_id`.
- `portfolio`:
  - Append all per-symbol rows for a snapshot at the given `timestamp`; if multiple rows share the same timestamp, add ns offsets to maintain a unique index.
  - Use `update()` to correct a specific row by addressing its exact `timestamp` (after any ns offset applied).
- `strategy_{strategy_symbol}_equity`:
  - Append new timestamps; `update()` for corrections.
- `strategy_{strategy_symbol}_positions`:
  - Append new timestamps; `update()` for corrections.
- `account_summary`:
  - Append new timestamps; `update()` for corrections.

## Index Normalization

Before persisting, enforce:
- For time-series symbols (`account_summary`, `orders`, `portfolio`, `strategy_*`):
  - Convert `timestamp` column to tz-aware UTC.
  - Set as index.
  - Ensure uniqueness by adding ns offsets on collisions (this is required for `portfolio` where multiple rows share the same snapshot time).
- For id-indexed symbols (`orders`, `fills`, `trades`):
  - Ensure IDs (`order_id`, `fill_id`, `execution_id`) are unique and set as the index.

## Notes

- Large datasets: If symbol tables grow large, introduce sharding/pagination strategies in follow-up maintenance.
- FX and base currency: Conversions are handled outside of persistence helpers; store both native and base values when available.
