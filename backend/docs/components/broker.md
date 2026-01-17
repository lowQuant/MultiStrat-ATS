# Broker Abstraction Layer

**Location:** `broker/`

## Purpose

The broker abstraction provides a unified interface for trading, allowing strategies to run identically in live trading and backtesting environments.

## Class Hierarchy

```
Broker (ABC)                    # broker/base_broker.py
├── LiveBroker                  # broker/live_broker.py
└── BacktestBroker              # broker/backtest_broker.py
```

---

## Broker (Abstract Base Class)

**Location:** `broker/base_broker.py`

### Constructor

```python
Broker(strategy_symbol: str, arctic_client=None)
```

| Parameter | Description |
|-----------|-------------|
| `strategy_symbol` | Strategy identifier (e.g., "TQQQ") |
| `arctic_client` | Optional ArcticDB client |

### Equity Management

The broker handles strategy equity allocation with a two-tier approach:

```python
equity = await broker.get_equity()
```

**Resolution Order:**
1. **Explicit allocation:** Check `strategy_{symbol}` table for equity value
2. **Weight-based:** `target_weight × total_equity` from `general/strategies`
3. **Fallback:** Total account equity

### Abstract Methods

| Method | Description |
|--------|-------------|
| `_get_total_equity()` | Get total account equity (impl-specific) |
| `place_order(contract, order, size, stop_price)` | Place an order |
| `get_positions()` | Get current positions |

---

## LiveBroker

**Location:** `broker/live_broker.py`

### Constructor

```python
LiveBroker(ib_client: IB, strategy_symbol: str, arctic_client=None)
```

### Initialization

On creation:
1. Gets account ID from `ib.managedAccounts()`
2. Creates account library if needed
3. Initializes account symbols (account_summary, portfolio, orders, fills, strategy_{symbol})

### Key Methods

#### `place_order()`

```python
trade = await broker.place_order(
    contract=Stock("AAPL", "SMART", "USD"),
    order=MarketOrder("BUY", 0),  # Quantity calculated from size
    size=0.5,  # 50% of allocated equity
    stop_price=None
)
```

**Flow:**
1. Get strategy equity via `get_equity()`
2. Request current market price
3. Calculate quantity: `(equity × size) / price`
4. Set `order.totalQuantity`
5. Place order via `ib.placeOrder()`
6. Return Trade object

#### `get_positions()`

```python
positions = await broker.get_positions()
# Returns List[Position] from IB
```

#### `_get_total_equity()`

Fetches `NetLiquidation` from IB account values:

```python
account_values = await self.ib.accountValuesAsync()
# Find 'NetLiquidation' with currency 'USD'
```

### Persistence Methods

Available for manual use (normally handled via message queue):

```python
await broker._persist_order(trade)
await broker._persist_order_status(trade)
await broker._persist_fill(trade, fill)
await broker._update_strategy_positions()
```

---

## BacktestBroker

**Location:** `broker/backtest_broker.py`

### Constructor

```python
BacktestBroker(
    engine: BacktestEngine,
    strategy_symbol: str,
    arctic_client=None,
    backtest_name=None
)
```

### Backtest Naming

Default: `{strategy_symbol}_{timestamp}` (e.g., `TQQQ_20250917_143022`)

### Key Methods

#### `place_order()`

```python
trade = await broker.place_order(contract, order, size)
```

**Flow:**
1. Use provided quantity OR calculate from equity/size
2. Create `MockTrade` object
3. Submit to `BacktestEngine`
4. Register fill/status event handlers
5. Record in `_backtest_data`

#### `get_positions()`

```python
positions = await broker.get_positions()
# Returns List[Position] from BacktestEngine
```

#### `_get_total_equity()`

```python
return self.engine.equity()
```

### Backtest Data Storage

Internal tracking before persistence:

```python
self._backtest_data = {
    'equity_curve': [],
    'trades': [],
    'positions': [],
    'orders': [],
    'fills': []
}
```

#### Save Results

```python
broker.save_backtest_results()
```

Writes to `backtests` library:
- `{name}_equity` - Equity curve
- `{name}_trades` - Trade log
- `{name}_positions` - Position snapshots
- `{name}_metrics` - Performance metrics

---

## Usage in Strategies

Strategies don't interact with brokers directly for orders. Instead, use `BaseStrategy` wrappers:

```python
class MyStrategy(BaseStrategy):
    async def run_strategy(self):
        # Recommended: Use BaseStrategy.place_order()
        trade = await self.place_order(
            contract=self.contract,
            quantity=100,  # Positive = BUY, Negative = SELL
            order_type='MKT'
        )
        
        # Or size-based:
        trade = await self.place_order_by_size(
            contract=self.contract,
            size=0.5,  # 50% of equity
            side='BUY'
        )
```

### Broker Initialization

Handled automatically by `BaseStrategy._initialize_broker()`:

```python
async def _initialize_broker(self):
    if self.broker_type == "backtest":
        self.broker = BacktestBroker(
            engine=self.backtest_engine,
            strategy_symbol=self.symbol,
            arctic_client=arctic_client
        )
    else:
        self.broker = LiveBroker(
            ib_client=self.ib,
            strategy_symbol=self.symbol,
            arctic_client=arctic_client
        )
```

---

## Equity Calculation Deep Dive

### From `general/strategies` Table

```python
async def _calculate_equity_from_weight(self) -> float:
    lib = self.arctic_client.get_library('general')
    strat_df = lib.read('strategies').data
    strat_row = strat_df[strat_df['strategy_symbol'] == self.strategy_symbol]
    
    # Try params JSON first
    params = json.loads(strat_row['params'])
    target_weight = params.get('target_weight')
    
    # Fallback to column
    if target_weight is None:
        target_weight = strat_row['target_weight']
    
    total_equity = await self._get_total_equity()
    return total_equity * target_weight
```

### From Strategy Table

```python
async def _get_strategy_equity_from_arctic(self) -> Optional[float]:
    symbol = f'strategy_{self.strategy_symbol}'
    if self._account_library.has_symbol(symbol):
        data = self._account_library.read(symbol).data
        if 'equity' in data.columns:
            return float(data['equity'].iloc[-1])
    return None
```
