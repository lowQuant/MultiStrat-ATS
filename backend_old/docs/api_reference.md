# API Reference

## Overview

This document provides a comprehensive API reference for the IB Multi-Strategy ATS system, covering all major classes, methods, and interfaces available for strategy development and system integration.

## Core Classes

### StrategyManager

The central orchestrator for managing multiple trading strategies.

```python
class StrategyManager:
    """Central strategy management and coordination class"""
    
    def __init__(self):
        """Initialize StrategyManager with default settings"""
        
    def load_strategies(self) -> None:
        """Load active strategies from configuration database"""
        
    def start_all(self) -> None:
        """Start all loaded strategies in separate threads"""
        
    def stop_all(self) -> None:
        """Stop all running strategies gracefully"""
        
    def disconnect(self) -> None:
        """Disconnect from IB and cleanup resources"""
        
    def process_messages(self) -> None:
        """Process messages from strategy message queue"""
        
    def handle_message(self, message: dict) -> None:
        """Handle specific message types from strategies"""
        
    def notify_order_placement(self, strategy: str, trade: Trade) -> None:
        """Handle order placement notifications"""
        
    def handle_fill_event(self, strategy_symbol: str, trade: Trade, fill: Fill) -> None:
        """Process trade fill events"""
        
    def get_orders(self) -> List[Order]:
        """Get all current orders"""
        
    def get_open_orders(self) -> List[Order]:
        """Get all open orders"""
```

### DataManager

Handles data operations, storage, and retrieval.

```python
class DataManager:
    """Data management and ArcticDB integration"""
    
    def __init__(self, ib_client: IB, arctic=None):
        """Initialize DataManager with IB client and ArcticDB connection"""
        
    def store_data_from_external_scripts(self, script_name: str, library: str, 
                                       symbol: str, append: bool = False) -> None:
        """Execute external script and store resulting data"""
        
    def get_data_from_arctic(self, library_name: str, symbol: str) -> pd.DataFrame:
        """Retrieve data from ArcticDB library"""
        
    def save_new_job(self, filename: str, cron_notation: str, cron_command: str,
                    operating_system: str, execution_method: str, lib: str = "",
                    symbol: str = "", saving_method: str = "Replace") -> None:
        """Save scheduled data collection job"""
        
    def get_saved_jobs(self) -> pd.DataFrame:
        """Retrieve all saved data collection jobs"""
        
    def run_python_script(self, script_path: str) -> subprocess.CompletedProcess:
        """Execute external Python script"""
        
    def schedule_python_script(self, script_path: str, schedule_time: str) -> None:
        """Schedule Python script for execution"""
        
    def run_scheduler(self) -> None:
        """Run the job scheduler continuously"""
```

### TradeManager

Manages trade execution and order lifecycle.

```python
class TradeManager:
    """Trade execution and order management"""
    
    def __init__(self, ib_client: IB, strategy_manager: StrategyManager):
        """Initialize TradeManager with IB client and strategy manager"""
        
    def place_order(self, contract: Contract, order: Order, strategy_symbol: str) -> Trade:
        """Place order through IB API"""
        
    def modify_order(self, trade: Trade, new_order: Order) -> Trade:
        """Modify existing order"""
        
    def cancel_order(self, trade: Trade) -> None:
        """Cancel existing order"""
        
    def get_trade_status(self, trade: Trade) -> str:
        """Get current status of trade"""
        
    def handle_fill_event(self, trade: Trade, fill: Fill) -> None:
        """Process trade fill event"""
```

### PortfolioManager

Tracks portfolio positions and performance.

```python
class PortfolioManager:
    """Portfolio tracking and performance management"""
    
    def __init__(self, ib_client: IB):
        """Initialize PortfolioManager with IB client"""
        
    def process_new_trade(self, strategy: str, trade: Trade) -> None:
        """Process new trade and update portfolio"""
        
    def match_ib_positions_with_arcticdb(self) -> None:
        """Synchronize IB positions with ArcticDB storage"""
        
    def get_portfolio_summary(self) -> dict:
        """Get comprehensive portfolio summary"""
        
    def get_positions(self) -> List[Position]:
        """Get all current positions"""
        
    def calculate_pnl(self, strategy: str = None) -> float:
        """Calculate P&L for strategy or entire portfolio"""
        
    def get_performance_metrics(self) -> dict:
        """Calculate portfolio performance metrics"""
```

### RiskManager

Implements risk controls and position sizing.

```python
class RiskManager:
    """Risk management and position sizing"""
    
    def __init__(self, portfolio_manager: PortfolioManager):
        """Initialize RiskManager with portfolio manager"""
        
    def validate_order(self, order: Order, contract: Contract, strategy: str) -> bool:
        """Validate order against risk limits"""
        
    def calculate_position_size(self, symbol: str, strategy: str, 
                              signal_strength: float) -> int:
        """Calculate appropriate position size"""
        
    def check_risk_limits(self, strategy: str) -> dict:
        """Check current risk exposure against limits"""
        
    def apply_stop_loss(self, position: Position, stop_percentage: float) -> Order:
        """Create stop loss order for position"""
        
    def calculate_var(self, confidence_level: float = 0.95, 
                     time_horizon: int = 1) -> float:
        """Calculate Value at Risk"""
```

## Strategy Development API

### Base Strategy Class

```python
class Strategy:
    """Base class for all trading strategies"""
    
    def __init__(self, client_id: int, strategy_manager: StrategyManager):
        """Initialize strategy with unique client ID"""
        self.client_id = client_id
        self.strategy_manager = strategy_manager
        self.strategy_name = "BaseStrategy"
        self.ib = connect_to_IB(clientid=client_id)
        
    async def initialize(self) -> None:
        """Initialize strategy - called once at startup"""
        pass
        
    async def on_market_data(self, ticker: Ticker) -> None:
        """Handle real-time market data updates"""
        pass
        
    async def on_order_status(self, trade: Trade) -> None:
        """Handle order status changes"""
        pass
        
    async def generate_signals(self) -> List[dict]:
        """Generate trading signals - implement in subclass"""
        raise NotImplementedError
        
    async def execute_trades(self, signals: List[dict]) -> None:
        """Execute trades based on signals"""
        pass
        
    async def run_strategy(self) -> None:
        """Main strategy execution loop"""
        pass
        
    def stop(self) -> None:
        """Stop strategy and cleanup resources"""
        pass

def manage_strategy(client_id: int, strategy_manager: StrategyManager, 
                   strategy_loops: dict) -> None:
    """Required entry point function for strategy threads"""
    pass
```

### Strategy Utilities

```python
def create_stock_contract(symbol: str, exchange: str = "SMART", 
                         currency: str = "USD") -> Stock:
    """Create stock contract for trading"""
    
def create_market_order(action: str, quantity: int) -> MarketOrder:
    """Create market order"""
    
def create_limit_order(action: str, quantity: int, limit_price: float) -> LimitOrder:
    """Create limit order"""
    
def create_stop_order(action: str, quantity: int, stop_price: float) -> StopOrder:
    """Create stop order"""
    
def calculate_technical_indicators(data: pd.DataFrame) -> pd.DataFrame:
    """Calculate common technical indicators"""
    
def load_historical_data(symbol: str, days: int = 30) -> pd.DataFrame:
    """Load historical market data"""
```

## Data Access API

### ArcticDB Operations

```python
def get_arctic_library(library_name: str, create_if_missing: bool = False) -> Library:
    """Get ArcticDB library instance"""
    
def write_data(library: str, symbol: str, data: pd.DataFrame) -> None:
    """Write data to ArcticDB"""
    
def read_data(library: str, symbol: str, date_range: tuple = None) -> pd.DataFrame:
    """Read data from ArcticDB"""
    
def append_data(library: str, symbol: str, data: pd.DataFrame) -> None:
    """Append data to existing ArcticDB symbol"""
    
def list_symbols(library: str) -> List[str]:
    """List all symbols in ArcticDB library"""
    
def delete_data(library: str, symbol: str) -> None:
    """Delete data from ArcticDB"""
```

### Market Data API

```python
def get_real_time_data(symbol: str, data_type: str = "TRADES") -> Ticker:
    """Subscribe to real-time market data"""
    
def get_historical_bars(contract: Contract, duration: str, bar_size: str) -> List[BarData]:
    """Get historical bar data from IB"""
    
def get_market_depth(contract: Contract) -> MktDepthData:
    """Get market depth data"""
    
def get_fundamental_data(contract: Contract, report_type: str) -> str:
    """Get fundamental data for contract"""
```

## GUI API

### Main GUI Functions

```python
def run_gui() -> None:
    """Start the main GUI application"""
    
def initialize_main_window() -> None:
    """Initialize the main application window"""
    
def update_dashboard() -> None:
    """Update the main dashboard display"""
    
def show_portfolio_window() -> None:
    """Display portfolio monitoring window"""
    
def show_settings_window() -> None:
    """Display system settings window"""
    
def show_database_window() -> None:
    """Display database management window"""
```

### Logging API

```python
def add_log(message: str, level: str = 'INFO', component: str = 'SYSTEM') -> None:
    """Add log entry to system log"""
    
def setup_log_viewer() -> None:
    """Initialize log viewing interface"""
    
def export_logs(start_date: datetime, end_date: datetime, 
               filename: str) -> None:
    """Export logs to file"""
```

## Broker Integration API

### Connection Management

```python
def connect_to_IB(clientid: int, host: str = '127.0.0.1', 
                 port: int = 7497) -> IB:
    """Connect to Interactive Brokers API"""
    
def disconnect_from_IB(ib_client: IB) -> None:
    """Disconnect from Interactive Brokers API"""
    
def check_connection_status(ib_client: IB) -> bool:
    """Check if IB connection is active"""
    
def reconnect_to_IB(ib_client: IB) -> bool:
    """Attempt to reconnect to IB"""
```

### Account Information

```python
def get_account_summary(ib_client: IB) -> List[AccountValue]:
    """Get account summary information"""
    
def get_portfolio_positions(ib_client: IB) -> List[Position]:
    """Get current portfolio positions"""
    
def get_account_value(ib_client: IB, tag: str) -> float:
    """Get specific account value"""
    
def get_buying_power(ib_client: IB) -> float:
    """Get available buying power"""
```

## Utility Functions

### Data Processing

```python
def clean_market_data(data: pd.DataFrame) -> pd.DataFrame:
    """Clean and validate market data"""
    
def resample_data(data: pd.DataFrame, frequency: str) -> pd.DataFrame:
    """Resample data to different frequency"""
    
def calculate_returns(data: pd.DataFrame, method: str = 'simple') -> pd.Series:
    """Calculate returns from price data"""
    
def normalize_data(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize data for analysis"""
```

### Performance Metrics

```python
def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """Calculate Sharpe ratio"""
    
def calculate_max_drawdown(returns: pd.Series) -> float:
    """Calculate maximum drawdown"""
    
def calculate_var(returns: pd.Series, confidence_level: float = 0.95) -> float:
    """Calculate Value at Risk"""
    
def calculate_beta(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Calculate beta relative to benchmark"""
```

### Risk Calculations

```python
def calculate_position_risk(position_size: int, price: float, 
                          volatility: float) -> float:
    """Calculate position risk"""
    
def calculate_portfolio_var(positions: List[Position], 
                          correlation_matrix: pd.DataFrame) -> float:
    """Calculate portfolio Value at Risk"""
    
def calculate_leverage(portfolio_value: float, cash: float) -> float:
    """Calculate portfolio leverage"""
```

## Configuration API

### Settings Management

```python
def load_configuration(config_file: str) -> dict:
    """Load configuration from file"""
    
def save_configuration(config: dict, config_file: str) -> None:
    """Save configuration to file"""
    
def get_setting(key: str, default=None):
    """Get configuration setting"""
    
def set_setting(key: str, value) -> None:
    """Set configuration setting"""
    
def validate_configuration(config: dict) -> bool:
    """Validate configuration settings"""
```

### Strategy Configuration

```python
def load_strategy_config(strategy_name: str) -> dict:
    """Load strategy-specific configuration"""
    
def save_strategy_config(strategy_name: str, config: dict) -> None:
    """Save strategy configuration"""
    
def get_active_strategies() -> List[str]:
    """Get list of active strategies"""
    
def activate_strategy(strategy_name: str) -> None:
    """Activate a strategy"""
    
def deactivate_strategy(strategy_name: str) -> None:
    """Deactivate a strategy"""
```

## Error Handling

### Exception Classes

```python
class ATSError(Exception):
    """Base exception for ATS system"""
    
class ConnectionError(ATSError):
    """IB connection related errors"""
    
class DataError(ATSError):
    """Data access and processing errors"""
    
class StrategyError(ATSError):
    """Strategy execution errors"""
    
class RiskError(ATSError):
    """Risk management violations"""
    
class ConfigurationError(ATSError):
    """Configuration related errors"""
```

### Error Handling Utilities

```python
def handle_ib_error(error: Exception) -> None:
    """Handle IB API errors"""
    
def log_error(error: Exception, context: str) -> None:
    """Log error with context information"""
    
def send_error_alert(error: Exception, severity: str) -> None:
    """Send error alert to monitoring system"""
    
def recover_from_error(error: Exception) -> bool:
    """Attempt to recover from error"""
```

## Constants and Enums

### Order Types

```python
ORDER_TYPES = {
    'MKT': 'Market Order',
    'LMT': 'Limit Order',
    'STP': 'Stop Order',
    'STP_LMT': 'Stop Limit Order',
    'TRAIL': 'Trailing Stop Order'
}
```

### Time in Force

```python
TIME_IN_FORCE = {
    'DAY': 'Day Order',
    'GTC': 'Good Till Canceled',
    'IOC': 'Immediate or Cancel',
    'FOK': 'Fill or Kill'
}
```

### Data Types

```python
DATA_TYPES = {
    'TRADES': 'Trade Data',
    'MIDPOINT': 'Midpoint Data',
    'BID': 'Bid Data',
    'ASK': 'Ask Data',
    'BID_ASK': 'Bid/Ask Data'
}
```

## Version Information

```python
__version__ = "1.0.0"
__author__ = "IB Multi-Strategy ATS Team"
__license__ = "MIT"
__python_requires__ = ">=3.8"
```
