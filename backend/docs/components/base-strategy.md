# BaseStrategy

**Location:** `obj/base_strategy.py`

## Purpose

BaseStrategy is the abstract base class that all trading strategies inherit from. It provides:
- Strategy lifecycle management (start/stop)
- IB connection handling
- Broker initialization
- Order placement wrappers
- Market data retrieval
- Event forwarding to PortfolioManager

## Constructor

```python
BaseStrategy(
    client_id: int,
    strategy_manager: StrategyManager,
    params: Optional[Dict[str, Any]] = None,
    broker_type: str = "live",
    backtest_engine=None,
    strategy_symbol: Optional[str] = None
)
```

| Parameter | Description |
|-----------|-------------|
| `client_id` | Unique IB client ID (1-99) |
| `strategy_manager` | Parent StrategyManager reference |
| `params` | Strategy parameters dict |
| `broker_type` | "live" or "backtest" |
| `backtest_engine` | BacktestEngine instance (if backtest) |
| `strategy_symbol` | Override for strategy symbol |

## Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `strategy_name` | str | Class name (e.g., "TqqqStrategy") |
| `symbol` | str | Strategy identifier (e.g., "TQQQ") |
| `client_id` | int | IB client ID |
| `ib` | IB | Strategy's IB connection |
| `broker` | Broker | LiveBroker or BacktestBroker |
| `params` | dict | Strategy parameters |
| `is_running` | bool | Running state |
| `is_connected` | bool | IB connection state |

### From Params

| Attribute | Default | Description |
|-----------|---------|-------------|
| `universe` | "" | Symbol(s) or ArcticDB library |
| `currency` | "USD" | Base currency |
| `max_position_size` | 1.0 | Max position as fraction of equity |
| `risk_per_trade` | 0.01 | Risk per trade fraction |
| `stop_loss` | 0.07 | Stop loss fraction |
| `trailing_stop_loss` | 0.20 | Trailing stop fraction |
| `profit_target` | 0.35 | Take profit fraction |

## Abstract Methods

Must be implemented by subclasses:

```python
async def initialize_strategy(self):
    """Setup contracts, subscribe to data, etc."""
    pass

async def run_strategy(self):
    """Main trading logic loop."""
    pass
```

## Lifecycle

### Starting

```python
strategy.start_strategy()
```

**Flow:**
1. Set `is_running = True`
2. Create daemon thread
3. In thread: Create event loop
4. Call `_main_strategy_loop()`

### Main Loop

```python
async def _main_strategy_loop(self):
    # 1. Connect to IB (if not injected)
    await self.connect_to_ib()
    
    # 2. Initialize broker
    await self._initialize_broker()
    
    # 3. Call user's initialize
    await self.initialize_strategy()
    
    # 4. Call user's main logic
    await self.run_strategy()
```

### Stopping

```python
strategy.stop_strategy()
```

**Flow:**
1. Set `is_running = False`
2. Schedule cleanup in event loop
3. Wait for pending trades (up to 5 min)
4. Disconnect from IB

## Order Placement

### Primary Method: `place_order()`

```python
trade = await self.place_order(
    contract: Contract,
    quantity: int,      # Positive=BUY, Negative=SELL
    order_type: str = 'MKT',
    *,
    algo: bool = True,
    urgency: str = 'Patient',  # Patient, Normal, Urgent
    orderRef: Optional[str] = None,
    limit: Optional[float] = None,
    useRth: bool = False,
    tif: str = 'DAY',
    transmit: bool = True,
    parentId: int = 0,
)
```

**Features:**
- Qualifies contract automatically
- Supports MKT, LMT, MOC order types
- Adaptive algo with urgency levels
- Attaches fill/status event handlers
- Forwards events to message queue

### Size-Based: `place_order_by_size()`

```python
trade = await self.place_order_by_size(
    contract: Contract,
    size: float,        # Fraction of equity (0.0-1.0)
    side: str = 'BUY',  # 'BUY' or 'SELL'
    order_type: str = 'MKT',
    *,
    limit: Optional[float] = None,
    algo: bool = True,
    urgency: str = 'Patient',
    useRth: bool = False,
)
```

Calculates quantity from `size × equity / price`.

### Helper: `calculate_quantity()`

```python
qty = await self.calculate_quantity(contract, percent_of_equity=0.5)
# Returns integer quantity
```

## Equity Methods

### Total Account Equity

```python
total = await self.get_total_equity()
# Returns NetLiquidation from IB
```

### Strategy Equity

```python
equity = await self.get_equity()
```

**Resolution:**
1. Check `strategy_{symbol}_equity` in account library
2. Fallback: `target_weight × total_equity`
3. Fallback: Broker's `get_equity()`

## Market Data

### Get Data (with ArcticDB cache)

```python
# Single symbol
df = await self.get_data(
    symbols=['AAPL'],
    timeframe='1_min',
    start_date='max',
    end_date='today',
    use_rth=True,
    force_download=False
)

# Multiple symbols
data = await self.get_data(symbols=['AAPL', 'GOOGL'])
# Returns dict: {'AAPL': df, 'GOOGL': df}
```

### Download from IB

```python
df = await self.download_data(
    symbol='AAPL',
    timeframe='1_min',
    start_date='max',
    end_date='today'
)
```

Downloads with full pagination and saves to `market_data/{SYMBOL}_{timeframe}`.

### Get Market Price

```python
price = await self.get_market_price(contract)
```

### Get Positions

```python
positions = await self.get_positions()
# Returns list from IB
```

## Event Handlers

### Fill Handler

```python
def on_fill(self, trade: Trade, fill):
    # Log the fill
    add_log(f"Fill: {fill.execution.side} {fill.execution.shares} @ {fill.execution.price}")
    
    # Forward to message queue
    self.strategy_manager.message_queue.put({
        "type": "fill",
        "strategy": self.symbol,
        "trade": trade,
        "fill": fill,
    })
```

### Status Handler

```python
def on_status_change(self, trade: Trade):
    status = trade.orderStatus.status
    if "Pending" not in status:
        self.strategy_manager.message_queue.put({
            "type": "status_change",
            "strategy": self.symbol,
            "trade": trade,
            "status": status,
        })
```

### Bar Update Hook

```python
def on_bar(self, bars, hasNewBar: bool):
    """Override for bar-driven strategies."""
    pass
```

## Default Parameters (PARAMS)

Importable base parameters:

```python
from obj.base_strategy import PARAMS as BASE_PARAMS

PARAMS = {
    "universe": "",
    "currency": "USD",
    "min_weight": 0.0,
    "max_weight": 1.0,
    "target_weight": 0.0,
    "max_position_size": 1.0,
    "risk_per_trade": 0.01,
    "stop_loss": 0.07,
    "trailing_stop_loss": 0.20,
    "profit_target": 0.35,
}
```

## FX Support

### Get Base Currency

```python
base = await self._get_base_currency()
# Returns from PortfolioManager or 'USD'
```

### Get FX Cache

```python
fx_cache = await self._get_fx_cache(base_currency)
# Returns shared FXCache from PortfolioManager
```

## Status

```python
status = strategy.get_status()
# Returns:
# {
#     "name": "TqqqStrategy",
#     "symbol": "TQQQ",
#     "client_id": 1,
#     "is_running": True,
#     "is_connected": True,
#     "params": {...},
#     "broker_type": "live"
# }
```

## Universe Helpers

```python
symbols = self.get_universe_symbols()
# Parses self.universe:
# - Single symbol: ["AAPL"]
# - Comma-separated: ["AAPL", "GOOGL", "MSFT"]
# - Empty: [self.symbol]
```
