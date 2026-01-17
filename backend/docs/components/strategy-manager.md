# StrategyManager

**Location:** `core/strategy_manager.py`

## Purpose

The StrategyManager is the central orchestrator of the MATS system. It:
- Maintains the master IB connection
- Manages strategy lifecycle (load, start, stop)
- Owns PortfolioManager and TradeManager
- Processes fill/order events via message queue

## Initialization

```python
strategy_manager = StrategyManager(arctic_client=ac)
```

On initialization:
1. Creates/gets ArcticDB client
2. Initializes PortfolioManager
3. Starts message processor thread
4. Connects to IB (`clientId=0`)

## Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `ib_client` | IB | Master IB connection (clientId=0) |
| `message_queue_ib_client` | IB | Message thread IB (clientId=99) |
| `ac` | Arctic | ArcticDB client |
| `lib` | Library | Reference to `general` library |
| `active_strategies` | dict | Running strategy instances |
| `portfolio_manager` | PortfolioManager | Accounting manager |
| `trade_manager` | TradeManager | Trade execution helper |
| `message_queue` | Queue | Event queue for fills/orders |
| `next_client_id` | int | Next available strategy clientId |

## Strategy Lifecycle

### Starting a Strategy

```python
success = strategy_manager.start_strategy("TQQQ")
```

**Flow:**
1. Look up `filename` from `general/strategies` table
2. Dynamically load strategy class from `strategies/{filename}`
3. Load params from ArcticDB (or file's `PARAMS` dict)
4. Create instance with unique `clientId`
5. Call `strategy.start_strategy()` (starts thread)
6. Add to `active_strategies` dict

### Stopping a Strategy

```python
success = strategy_manager.stop_strategy("TQQQ")
```

**Flow:**
1. Call `strategy.stop_strategy()`
2. Strategy waits for pending trades (up to 5 min)
3. Disconnects strategy's IB connection
4. Remove from `active_strategies`

### Start All Active Strategies

```python
results = strategy_manager.start_all_strategies()
# Returns: {"TQQQ": True, "AAPL": True, ...}
```

Reads `general/strategies` table and starts all with `active=True`.

## Message Queue Processing

The message processor runs in a daemon thread with its own event loop and IB connection (`clientId=99`).

### Message Types

| Type | Trigger | Handler |
|------|---------|---------|
| `order` | Strategy places order | `notify_order_placement_async()` |
| `fill` | Order filled | `handle_fill_event_async()` |
| `status_change` | Order status update | `handle_status_change_async()` |

### Fill Processing Flow

```python
# In strategy (via BaseStrategy.on_fill):
strategy_manager.message_queue.put({
    "type": "fill",
    "strategy": self.symbol,
    "trade": trade,
    "fill": fill,
})

# In message processor thread:
async def handle_fill_event_async(self, strategy_symbol, trade, fill):
    # Log the fill
    self._queue_add_log(message, strategy_symbol)
    
    # Persist via PortfolioManager
    await self.portfolio_manager.process_fill(strategy_symbol, trade, fill)
    await self.portfolio_manager.record_status_change(strategy_symbol, trade, status)
```

## Connection Management

### Get Connection Status

```python
status = await strategy_manager.get_connection_status()
# Returns:
# {
#     "master_connection": {"connected": True, "client_id": 0, ...},
#     "message_queue_connection": {"connected": True, "client_id": 99, ...},
#     "strategy_connections": [
#         {"strategy_name": "TQQQ", "client_id": 1, "connected": True},
#         ...
#     ]
# }
```

### Disconnect Specific Client

```python
await strategy_manager.disconnect_client(client_id=1)  # Stops strategy with clientId=1
await strategy_manager.disconnect_client(client_id=0)  # Disconnects master
```

### Disconnect All

```python
await strategy_manager.disconnect_all()
```

## Strategy Metadata

### Reading Strategy Info

```python
# Get strategy filename from metadata
filename = strategy_manager._get_strategy_filename("TQQQ")
# Returns: "tqqq_strategy.py"
```

### Loading Strategy Parameters

```python
params = strategy_manager.load_strategy_params("TQQQ", module)
```

**Priority:**
1. JSON params from `general/strategies.params` column
2. Module's `PARAMS` dict (persisted back to ArcticDB)

## API Methods

| Method | Description |
|--------|-------------|
| `connect_to_ib()` | Connect master IB client |
| `disconnect()` | Disconnect master IB client |
| `start_strategy(symbol)` | Start a strategy by symbol |
| `stop_strategy(symbol)` | Stop a running strategy |
| `start_all_strategies()` | Start all active strategies |
| `stop_all_strategies()` | Stop all running strategies |
| `get_strategy_status()` | Get status of all strategies |
| `get_connection_status()` | Get all connection statuses |
| `list_strategy_files()` | List available strategy files |
| `load_strategy_class(filename)` | Load strategy class from file |
| `load_strategy_params(symbol, module)` | Load strategy parameters |
| `test_connection()` | Test IB connection |
| `cleanup()` | Stop all and disconnect |

## Usage in Routes

Routes receive the strategy manager via dependency injection:

```python
# In routes/strategies.py
_strategy_manager = None

def set_strategy_manager(sm):
    global _strategy_manager
    _strategy_manager = sm

@router.post("/strategies/{symbol}/start")
async def start_strategy(symbol: str):
    success = _strategy_manager.start_strategy(symbol)
    return {"success": success}
```
