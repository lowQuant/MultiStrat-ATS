# Creating Strategies

This guide walks through creating a new trading strategy in MATS.

## Quick Start

### 1. Create Strategy File

Create a new file in `backend/strategies/`:

```python
# strategies/my_strategy.py

from obj.base_strategy import BaseStrategy, PARAMS as BASE_PARAMS
from ib_async import Stock, MarketOrder

PARAMS = {
    **BASE_PARAMS,
    "universe": "AAPL",
    "target_weight": 0.10,
    "stop_loss": 0.05,
    "profit_target": 0.20,
}

class MyStrategy(BaseStrategy):
    async def initialize_strategy(self):
        """Setup contracts and subscriptions."""
        symbol = self.params.get("universe", "AAPL")
        self.contract = Stock(symbol, "SMART", "USD")
        await self.ib.qualifyContractsAsync(self.contract)
    
    async def run_strategy(self):
        """Main trading logic."""
        while self.is_running:
            # Your logic here
            await asyncio.sleep(60)
```

### 2. Register in ArcticDB

Add strategy metadata to `general/strategies` table:

| Column | Value |
|--------|-------|
| `strategy_symbol` | MY_STRATEGY |
| `filename` | my_strategy.py |
| `target_weight` | 0.10 |
| `params` | {} |
| `active` | False |

Or via the frontend Strategy Management UI.

### 3. Start Strategy

```python
# Via API
POST /strategies/MY_STRATEGY/start

# Or programmatically
strategy_manager.start_strategy("MY_STRATEGY")
```

---

## Strategy Template

```python
"""
My Strategy - Brief description
"""
import asyncio
from obj.base_strategy import BaseStrategy, PARAMS as BASE_PARAMS
from ib_async import Stock, LimitOrder, MarketOrder
from core.log_manager import add_log

PARAMS = {
    **BASE_PARAMS,
    # === Required ===
    "universe": "AAPL",           # Symbol(s) to trade
    "target_weight": 0.10,        # 10% of portfolio
    
    # === Optional Overrides ===
    "max_position_size": 0.5,     # Max 50% of strategy equity per position
    "stop_loss": 0.05,            # 5% stop loss
    "profit_target": 0.20,        # 20% take profit
    
    # === Custom Parameters ===
    "lookback_days": 20,
    "entry_threshold": 0.02,
}


class MyStrategy(BaseStrategy):
    """Strategy implementation."""
    
    async def initialize_strategy(self):
        """
        Called once after IB connection established.
        Setup contracts, subscribe to data, etc.
        """
        # Parse universe
        symbols = self.get_universe_symbols()
        self.contracts = {}
        
        for sym in symbols:
            contract = Stock(sym, "SMART", "USD")
            await self.ib.qualifyContractsAsync(contract)
            self.contracts[sym] = contract
        
        # Load historical data if needed
        self.data = await self.get_data(
            symbols=symbols,
            timeframe='1_day',
            start_date='max'
        )
        
        add_log(f"Initialized with {len(self.contracts)} contracts", self.symbol)
    
    async def run_strategy(self):
        """
        Main strategy loop.
        Called after initialize_strategy().
        """
        while self.is_running:
            try:
                await self.check_signals()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                add_log(f"Error in strategy loop: {e}", self.symbol, "ERROR")
                await asyncio.sleep(5)
    
    async def check_signals(self):
        """Check for entry/exit signals."""
        for sym, contract in self.contracts.items():
            price = await self.get_market_price(contract)
            if price is None:
                continue
            
            # Your signal logic here
            if self.should_enter(sym, price):
                await self.enter_position(contract, price)
            elif self.should_exit(sym, price):
                await self.exit_position(contract, price)
    
    def should_enter(self, symbol: str, price: float) -> bool:
        """Entry signal logic."""
        # Implement your entry conditions
        return False
    
    def should_exit(self, symbol: str, price: float) -> bool:
        """Exit signal logic."""
        # Implement your exit conditions
        return False
    
    async def enter_position(self, contract, price: float):
        """Enter a new position."""
        # Calculate position size (50% of allocated equity)
        trade = await self.place_order_by_size(
            contract=contract,
            size=0.5,
            side='BUY',
            order_type='MKT',
            urgency='Patient'
        )
        
        if trade:
            add_log(f"Entered {contract.symbol}", self.symbol)
    
    async def exit_position(self, contract, price: float):
        """Exit existing position."""
        positions = await self.get_positions()
        
        for pos in positions:
            if pos.contract.symbol == contract.symbol:
                qty = abs(pos.position)
                side = 'SELL' if pos.position > 0 else 'BUY'
                
                trade = await self.place_order(
                    contract=contract,
                    quantity=-pos.position,  # Negative to close
                    order_type='MKT'
                )
                
                if trade:
                    add_log(f"Exited {contract.symbol}", self.symbol)
                break
```

---

## Key Concepts

### Parameters

Define in module-level `PARAMS` dict:

```python
PARAMS = {
    **BASE_PARAMS,  # Include base defaults
    "my_param": 123,
}
```

Access in strategy:
```python
value = self.params.get("my_param", default_value)
```

**Parameter Source Priority:**
1. `general/strategies.params` (JSON) - persisted
2. Module `PARAMS` dict (saved to ArcticDB on first run)

### Order Placement

#### By Quantity

```python
trade = await self.place_order(
    contract=contract,
    quantity=100,       # Positive=BUY, Negative=SELL
    order_type='MKT',   # MKT, LMT, MOC
    algo=True,
    urgency='Patient',  # Patient, Normal, Urgent
    limit=150.00,       # Required for LMT
    tif='DAY',
)
```

#### By Size (Fraction of Equity)

```python
trade = await self.place_order_by_size(
    contract=contract,
    size=0.5,           # 50% of strategy equity
    side='BUY',
    order_type='MKT',
)
```

### Getting Data

#### From ArcticDB (Cached)

```python
df = await self.get_data(
    symbols=['AAPL'],
    timeframe='1_min',  # 1_min, 1_hour, 1_day
    force_download=False
)
```

#### Fresh from IB

```python
df = await self.download_data(
    symbol='AAPL',
    timeframe='1_min',
    start_date='max',
    end_date='today'
)
```

### Equity and Sizing

```python
# Strategy's allocated equity
equity = await self.get_equity()

# Calculate shares from percentage
qty = await self.calculate_quantity(contract, percent_of_equity=0.25)

# Current market price
price = await self.get_market_price(contract)
```

### Positions

```python
# All IB positions
positions = await self.get_positions()

# Filter for this strategy's positions
for pos in positions:
    print(f"{pos.contract.symbol}: {pos.position} @ {pos.avgCost}")
```

### Logging

```python
from core.log_manager import add_log

add_log("Info message", self.symbol)
add_log("Warning", self.symbol, "WARNING")
add_log("Error", self.symbol, "ERROR")
```

---

## Event-Driven Strategies

For strategies that react to bar updates:

```python
class MyBarStrategy(BaseStrategy):
    async def initialize_strategy(self):
        self.contract = Stock("AAPL", "SMART", "USD")
        await self.ib.qualifyContractsAsync(self.contract)
        
        # Subscribe to 5-second bars
        self.bars = self.ib.reqRealTimeBars(
            self.contract, 5, 'TRADES', False
        )
        self.bars.updateEvent += self.on_bar_update
    
    def on_bar_update(self, bars, hasNewBar):
        """Called on each bar update."""
        if hasNewBar:
            bar = bars[-1]
            # React to new bar
            print(f"New bar: {bar.close}")
    
    async def run_strategy(self):
        """Keep alive while running."""
        while self.is_running:
            await asyncio.sleep(1)
```

---

## Backtesting

To make strategy backtestable:

```python
class MyStrategy(BaseStrategy):
    async def initialize_strategy(self):
        # Works for both live and backtest
        self.contract = Stock("AAPL", "SMART", "USD")
        
        if self.broker_type == "live":
            await self.ib.qualifyContractsAsync(self.contract)
    
    async def run_strategy(self):
        if self.broker_type == "backtest":
            # Backtest mode: process historical bars
            for bar in self.backtest_engine.bars:
                self.on_bar(bar, True)
        else:
            # Live mode: event loop
            while self.is_running:
                await asyncio.sleep(1)
```

---

## Best Practices

### 1. Handle Disconnections

```python
async def run_strategy(self):
    while self.is_running:
        if not self.is_connected:
            add_log("Waiting for reconnection...", self.symbol, "WARNING")
            await asyncio.sleep(5)
            continue
        
        # Normal logic
        await self.check_signals()
```

### 2. Respect Rate Limits

```python
# Don't spam market data requests
price = await self.get_market_price(contract)
await asyncio.sleep(0.1)  # Small delay between requests
```

### 3. Use Logging

```python
add_log(f"Signal: {signal_type} for {symbol}", self.symbol)
add_log(f"Order placed: {trade.order.orderId}", self.symbol)
```

### 4. Clean Exit

```python
async def run_strategy(self):
    try:
        while self.is_running:
            await self.check_signals()
            await asyncio.sleep(60)
    finally:
        # Cleanup on exit
        add_log("Strategy shutting down", self.symbol)
```

### 5. Test Parameters

Start with small `target_weight` while testing:

```python
PARAMS = {
    "target_weight": 0.01,  # 1% for testing
}
```
