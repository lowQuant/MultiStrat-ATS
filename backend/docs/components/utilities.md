# Utility Modules

**Location:** `utils/`

## Overview

| Module | Purpose |
|--------|---------|
| `fx_cache.py` | FX rate caching with IB/yfinance fallback |
| `ib_connection.py` | IB connection management |
| `strategy_table_helpers.py` | Strategy position/equity operations |
| `position_helpers.py` | Position and fill data extraction |
| `persistence_utils.py` | ArcticDB write utilities |
| `settings.py` | Settings management |
| `market_calendar.py` | Trading calendar utilities |
| `ib_historical_downloader.py` | Historical data download |

---

## FXCache (`fx_cache.py`)

Caches FX rates with TTL and multiple data sources.

### Constructor

```python
FXCache(ib_client, base_currency: str = "USD", ttl_minutes: int = 60)
```

### Get FX Rate

```python
rate = await fx_cache.get_fx_rate(currency, base_currency, ib_client=None)
```

**Data Source Priority:**
1. Cache (if fresh within TTL)
2. IB live/delayed market data
3. yfinance fallback
4. Default 1.0

### Convert DataFrame

```python
df = await fx_cache.convert_marketValue_to_base_async(df, base_currency)
# Adds 'fx_rate' and 'marketValue_base' columns
```

### Cache Management

```python
fx_cache.clear_cache()
fx_cache.clear_cache_if_stale(max_age_minutes=30)
status = fx_cache.get_cache_status()
```

---

## IB Connection (`ib_connection.py`)

### Connect

```python
ib = await connect_to_ib(
    host='127.0.0.1',
    port=7497,
    client_id=0,
    symbol=None,        # For logging
    existing_ib=None    # Reuse if connected
)
```

### Disconnect

```python
await disconnect_from_ib(ib, symbol=None)
```

### Test Connection

```python
result = await test_ib_connection(ib, test_symbol='SPY')
# Returns: {status, host, port, client_id, market_data_available, ...}
```

### Get Next Client ID

```python
client_id = get_next_client_id(existing_connections=[0, 1, 2])
# Returns: 3
```

---

## Strategy Table Helpers (`strategy_table_helpers.py`)

### Hourly Snapshot Task

```python
task = start_hourly_snapshot_task(portfolio_manager)
stop_hourly_snapshot_task(task)
```

Runs at top of each hour:
1. Reconcile positions
2. Write position snapshots per strategy
3. Write EQUITY rows
4. Write account summary

### Initialize Strategy CASH

```python
success = await initialize_strategy_cash(
    portfolio_manager,
    strategy_symbol="TQQQ",
    initial_cash=10000.0,
    currency='USD'
)
```

Creates initial CASH position in `strategy_{symbol}` table.

### Get Strategy Positions

```python
# All current positions (excludes EQUITY)
df = await get_strategy_positions(pm, "TQQQ", current_only=True)

# Specific symbol (returns dict)
pos = await get_strategy_positions(pm, "TQQQ", symbol="AAPL")

# Full history
df = await get_strategy_positions(pm, "TQQQ", current_only=False, days_lookback=30)

# Include equity snapshots
df = await get_strategy_positions(pm, "TQQQ", symbol="EQUITY", exclude_equity=False)
```

### Calculate Strategy Equity

```python
equity = await calculate_strategy_equity(pm, "TQQQ", portfolio_df=None)
# Returns: CASH + sum(position_market_values)
```

If `portfolio_df` provided, uses live market values (Mark-to-Market).
Otherwise, uses avg_cost (Cost Basis).

### Get Equity History

```python
df = await get_strategy_equity_history(pm, "TQQQ", days_lookback=30)
# Columns: equity, realized_pnl, currency
```

### Update Strategy CASH

```python
success = await update_strategy_cash(pm, "TQQQ", fill_data)
```

Called after fills to adjust CASH:
- BUY: Decrease CASH
- SELL: Increase CASH

---

## Position Helpers (`position_helpers.py`)

### Create Position Dict

```python
position = create_position_dict(portfolio_manager, ib_portfolio_item)
```

Converts IB portfolio item to standardized dict with:
- symbol, asset_class, position, side
- averageCost, marketPrice, marketValue
- currency, exchange, fx_rate
- multiplier (for futures/options)

### Extract Fill Data

```python
fill_data = extract_fill_data(strategy, trade, fill)
# Returns:
# {
#     'strategy', 'symbol', 'asset_class', 'exchange', 'currency',
#     'fill_id', 'order_ref', 'side', 'quantity', 'price',
#     'commission', 'timestamp', 'order_id', 'perm_id'
# }
```

### Extract Order Data

```python
order_data = extract_order_data(strategy, trade, status)
# Returns:
# {
#     'strategy', 'symbol', 'asset_class', 'exchange', 'currency',
#     'order_id', 'perm_id', 'order_ref', 'order_type', 'side',
#     'total_quantity', 'filled_quantity', 'remaining_quantity',
#     'avg_fill_price', 'status', 'timestamp'
# }
```

### Calculate Average Cost

```python
new_avg = calculate_avg_cost(
    existing_qty=100,
    existing_avg_cost=50.0,
    delta_qty=50,       # Positive=buy, Negative=sell
    trade_price=55.0
)
```

**Logic:**
- Opening from flat → trade_price
- Adding same direction → weighted average
- Partial reduction → unchanged
- Full close → 0.0
- Reversal → trade_price

### Create Portfolio Row from Fill

```python
row = await create_portfolio_row_from_fill(pm, trade, fill, strategy, ib)
```

---

## Persistence Utils (`persistence_utils.py`)

### Normalize Timestamp Index

```python
df = normalize_timestamp_index(
    df,
    index_col='timestamp',
    tz='UTC',
    ensure_unique=True,
    add_ns_offsets_on_collision=True
)
```

**Operations:**
1. Convert to datetime
2. Localize/convert to UTC
3. Set as index
4. Add nanoseconds for uniqueness
5. Round numeric columns
6. Sort by index

---

## Settings Manager (`settings.py`)

### Constructor

```python
settings_manager = SettingsManager(arctic_client)
```

### Load Settings

```python
settings = settings_manager.load_settings()
# Returns dict with IB, S3, and other settings
```

### Save Settings

```python
success = settings_manager.save_settings({
    'ib_port': '7497',
    'ib_host': '127.0.0.1',
    's3_db_management': 'False',
    ...
})
```

### Default Settings

```python
{
    'ib_port': '7497',
    'ib_host': '127.0.0.1',
    's3_db_management': 'False',
    'aws_access_id': '',
    'aws_access_key': '',
    'bucket_name': '',
    'region': '',
    'auto_start_tws': 'False',
    'username': '',
    'password': ''
}
```

---

## Historical Downloader (`ib_historical_downloader.py`)

### Paginated Download

```python
df = await download_ib_historical_paginated(
    symbol='AAPL',
    interval='minute',      # minute, hour, day
    start_date='max',       # 'max' for full lookback
    end_date='today',
    use_rth=True,
    what_to_show='TRADES',
    chunk=None,             # Auto chunk size
    client_id=9999,
    progress_cb=None        # Callback(pct, msg)
)
```

Downloads maximum available history with automatic pagination to respect IB limits.

---

## Arctic Manager (`core/arctic_manager.py`)

### Get Client

```python
ac = get_ac(db_path=None)
```

**Initialization:**
1. Create local LMDB connection
2. Check settings for S3 configuration
3. If S3 enabled, connect to S3 bucket
4. Create required libraries (general, market_data, etc.)

### Test S3 Connection

```python
success = test_aws_s3_connection(
    aws_access_id,
    aws_access_key,
    bucket_name,
    region
)
```

### Defragment Portfolio

```python
defragment_account_portfolio(library, symbol="portfolio")
```
