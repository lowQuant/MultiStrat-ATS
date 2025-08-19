# Configuration Guide

## Overview

This guide covers the configuration and setup of the IB Multi-Strategy ATS system, including Interactive Brokers connection setup, strategy configuration, risk management parameters, and system optimization settings.

## System Requirements

### 1. Software Requirements

**Python Environment:**
- Python 3.8 or higher
- Required packages (see setup.py):
  - ib_async
  - pandas
  - numpy
  - arcticdb
  - yfinance
  - asyncio
  - threading

**Interactive Brokers Setup:**
- IB TWS (Trader Workstation) or IB Gateway
- Active IB account with API access enabled
- Proper market data subscriptions

**Database:**
- ArcticDB for time-series data storage
- Local storage space for database files

### 2. Hardware Requirements

**Minimum Requirements:**
- 8GB RAM (16GB recommended for multiple strategies)
- 4-core CPU (8-core recommended)
- 10GB free disk space (more for extensive historical data)
- Stable internet connection

**Recommended for Production:**
- 32GB RAM
- 8+ core CPU
- SSD storage
- Redundant internet connections

## Interactive Brokers Configuration

### 1. TWS/Gateway Setup

**Enable API Access:**
1. Open TWS or IB Gateway
2. Go to File → Global Configuration → API → Settings
3. Enable "Enable ActiveX and Socket Clients"
4. Set Socket port (default: 7497 for TWS, 4001 for Gateway)
5. Add trusted IP addresses (127.0.0.1 for local)
6. Set Master API client ID if needed

**Connection Parameters:**
```python
# Default IB connection settings
IB_HOST = '127.0.0.1'
IB_PORT = 7497  # TWS paper trading
# IB_PORT = 7496  # TWS live trading
# IB_PORT = 4001  # IB Gateway paper trading
# IB_PORT = 4000  # IB Gateway live trading

CLIENT_ID_START = 1  # Starting client ID for strategies
```

### 2. Market Data Subscriptions

Ensure you have appropriate market data subscriptions:
- US Securities Snapshot and Futures Value Bundle
- Real-time market data for your trading instruments
- Level II data if required by strategies

### 3. Account Permissions

Required account permissions:
- Stock trading permissions
- Options trading (if using options strategies)
- Futures trading (if using futures strategies)
- API trading permissions

## Strategy Configuration

### 1. Strategy Database Setup

Strategies are configured in ArcticDB under the 'strategies' library:

```python
# Example strategy configuration
strategy_config = {
    'filename': 'LTMT.py',
    'strategy_name': 'Long Term Momentum',
    'active': 'True',
    'parameters': {
        'symbols': ['AAPL', 'MSFT', 'GOOGL'],
        'lookback_period': 252,
        'rebalance_frequency': 'monthly',
        'risk_per_trade': 0.02
    },
    'risk_limits': {
        'max_position_size': 10000,
        'max_portfolio_weight': 0.1,
        'stop_loss_pct': 0.05
    }
}
```

### 2. Strategy Activation

**Via GUI:**
1. Open Settings Window
2. Navigate to Strategy Management
3. Select strategies to activate
4. Configure parameters
5. Apply changes

**Via Database Direct:**
```python
from data_and_research.utils import save_strategy_config

# Save strategy configuration
save_strategy_config(strategy_config)
```

### 3. Strategy Parameters

**Common Parameters:**
- `symbols`: List of trading instruments
- `lookback_period`: Historical data period for analysis
- `rebalance_frequency`: How often to rebalance positions
- `risk_per_trade`: Risk percentage per trade
- `max_positions`: Maximum number of concurrent positions

## Risk Management Configuration

### 1. Global Risk Limits

```python
# Global risk management settings
RISK_CONFIG = {
    'max_account_risk': 0.02,  # 2% of account per day
    'max_strategy_risk': 0.005,  # 0.5% per strategy
    'max_position_size': 0.1,  # 10% of account per position
    'max_correlation': 0.7,  # Maximum correlation between strategies
    'emergency_stop_loss': 0.05,  # 5% account drawdown triggers stop
    'margin_buffer': 0.2  # 20% margin buffer
}
```

### 2. Position Sizing Rules

```python
# Position sizing configuration
POSITION_SIZING = {
    'method': 'volatility_adjusted',  # or 'fixed', 'kelly'
    'base_position_size': 1000,  # Base position size in dollars
    'volatility_lookback': 30,  # Days for volatility calculation
    'max_leverage': 2.0,  # Maximum leverage allowed
    'min_position_size': 100,  # Minimum position size
    'position_increment': 100  # Position size increments
}
```

### 3. Stop Loss Configuration

```python
# Stop loss settings
STOP_LOSS_CONFIG = {
    'default_stop_pct': 0.02,  # 2% stop loss
    'trailing_stop': True,  # Enable trailing stops
    'trailing_stop_pct': 0.01,  # 1% trailing stop
    'time_based_stop': 30,  # Days to hold position max
    'profit_target_ratio': 2.0  # Risk:Reward ratio
}
```

## Data Configuration

### 1. ArcticDB Setup

```python
# ArcticDB configuration
ARCTIC_CONFIG = {
    'uri': 'lmdb://./data_and_research/db/arctic_db',
    'libraries': {
        'market_data': 'Time-series market data',
        'strategies': 'Strategy configurations',
        'portfolios': 'Portfolio positions and performance',
        'jobs': 'Scheduled data collection jobs',
        'research': 'Research and analysis data'
    }
}
```

### 2. Data Collection Jobs

```python
# Data collection job configuration
DATA_JOBS = [
    {
        'name': 'us_stock_data_download',
        'script': 'data_and_research/jobs/download_us_stock_data.py',
        'schedule': '0 6 * * 1-5',  # Weekdays at 6 AM
        'symbols': 'univ_us_equities.csv',
        'library': 'market_data'
    },
    {
        'name': 'options_data_collection',
        'script': 'data_and_research/jobs/collect_options_data.py',
        'schedule': '0 16 * * 1-5',  # Weekdays at 4 PM
        'library': 'options_data'
    }
]
```

### 3. External Data Sources

```python
# External data source configuration
EXTERNAL_DATA = {
    'yfinance': {
        'enabled': True,
        'rate_limit': 2000,  # Requests per hour
        'timeout': 30  # Request timeout in seconds
    },
    'alpha_vantage': {
        'enabled': False,
        'api_key': 'YOUR_API_KEY',
        'rate_limit': 500
    },
    'quandl': {
        'enabled': False,
        'api_key': 'YOUR_API_KEY'
    }
}
```

## System Performance Configuration

### 1. Threading Configuration

```python
# Threading and performance settings
PERFORMANCE_CONFIG = {
    'max_strategy_threads': 10,  # Maximum concurrent strategies
    'thread_pool_size': 4,  # Thread pool for I/O operations
    'message_queue_size': 1000,  # Message queue buffer size
    'data_cache_size': 100,  # MB for data caching
    'connection_timeout': 30,  # IB connection timeout
    'reconnect_attempts': 5,  # Auto-reconnect attempts
    'heartbeat_interval': 30  # Seconds between heartbeats
}
```

### 2. Logging Configuration

```python
# Logging configuration
LOGGING_CONFIG = {
    'level': 'INFO',  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    'file_logging': True,
    'log_file': 'logs/ats_system.log',
    'max_file_size': '10MB',
    'backup_count': 5,
    'console_logging': True,
    'gui_logging': True,
    'log_format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
}
```

### 3. Memory Management

```python
# Memory management settings
MEMORY_CONFIG = {
    'max_memory_usage': '4GB',  # Maximum memory usage
    'data_retention_days': 365,  # Days to keep detailed data
    'cleanup_interval': 3600,  # Seconds between cleanup runs
    'cache_cleanup_threshold': 0.8,  # Memory threshold for cache cleanup
    'garbage_collection_interval': 300  # Seconds between GC runs
}
```

## GUI Configuration

### 1. Interface Settings

```python
# GUI configuration
GUI_CONFIG = {
    'theme': 'dark',  # 'light', 'dark', 'auto'
    'update_frequency': 1000,  # Milliseconds between updates
    'chart_history_days': 30,  # Days of data for charts
    'max_log_entries': 1000,  # Maximum log entries to display
    'auto_refresh': True,  # Auto-refresh data
    'notifications': True,  # Enable notifications
    'sound_alerts': False  # Enable sound alerts
}
```

### 2. Dashboard Layout

```python
# Dashboard configuration
DASHBOARD_CONFIG = {
    'default_widgets': [
        'portfolio_summary',
        'active_strategies',
        'recent_trades',
        'system_status',
        'market_overview'
    ],
    'refresh_intervals': {
        'portfolio': 5,  # Seconds
        'strategies': 10,
        'trades': 5,
        'system': 30,
        'market': 60
    }
}
```

## Environment Configuration

### 1. Development Environment

```python
# Development settings
DEV_CONFIG = {
    'paper_trading': True,
    'debug_mode': True,
    'mock_data': False,
    'test_strategies': ['test_strategy.py'],
    'reduced_logging': False,
    'development_port': 7497  # TWS paper trading port
}
```

### 2. Production Environment

```python
# Production settings
PROD_CONFIG = {
    'paper_trading': False,
    'debug_mode': False,
    'mock_data': False,
    'enhanced_logging': True,
    'monitoring_enabled': True,
    'backup_enabled': True,
    'production_port': 7496  # TWS live trading port
}
```

### 3. Environment Variables

```bash
# Environment variables (.env file)
IB_HOST=127.0.0.1
IB_PORT=7497
IB_CLIENT_ID=1

ARCTIC_DB_PATH=./data_and_research/db/arctic_db
LOG_LEVEL=INFO
ENVIRONMENT=development

# API Keys (if using external data sources)
ALPHA_VANTAGE_API_KEY=your_key_here
QUANDL_API_KEY=your_key_here
```

## Security Configuration

### 1. Access Control

```python
# Security settings
SECURITY_CONFIG = {
    'enable_authentication': False,  # Enable for production
    'session_timeout': 3600,  # Session timeout in seconds
    'max_login_attempts': 3,
    'password_complexity': True,
    'two_factor_auth': False,  # Enable for enhanced security
    'api_rate_limiting': True
}
```

### 2. Data Encryption

```python
# Encryption settings
ENCRYPTION_CONFIG = {
    'encrypt_database': False,  # Enable for sensitive data
    'encrypt_logs': False,
    'encryption_key_file': 'keys/encryption.key',
    'ssl_enabled': False,  # Enable for network security
    'certificate_file': 'certs/server.crt'
}
```

## Backup and Recovery

### 1. Backup Configuration

```python
# Backup settings
BACKUP_CONFIG = {
    'auto_backup': True,
    'backup_frequency': 'daily',  # 'hourly', 'daily', 'weekly'
    'backup_location': './backups/',
    'retention_days': 30,
    'compress_backups': True,
    'backup_components': [
        'database',
        'configurations',
        'logs',
        'strategies'
    ]
}
```

### 2. Recovery Procedures

```python
# Recovery configuration
RECOVERY_CONFIG = {
    'auto_recovery': True,
    'recovery_timeout': 300,  # Seconds
    'max_recovery_attempts': 3,
    'recovery_notification': True,
    'fallback_mode': 'safe',  # 'safe', 'aggressive', 'manual'
}
```

## Monitoring and Alerting

### 1. System Monitoring

```python
# Monitoring configuration
MONITORING_CONFIG = {
    'system_health_check': True,
    'performance_monitoring': True,
    'resource_monitoring': True,
    'connection_monitoring': True,
    'strategy_monitoring': True,
    'alert_thresholds': {
        'cpu_usage': 80,  # Percentage
        'memory_usage': 85,
        'disk_usage': 90,
        'connection_latency': 1000,  # Milliseconds
        'error_rate': 0.05  # 5% error rate
    }
}
```

### 2. Alert Configuration

```python
# Alert settings
ALERT_CONFIG = {
    'email_alerts': False,
    'sms_alerts': False,
    'gui_alerts': True,
    'log_alerts': True,
    'alert_levels': ['ERROR', 'CRITICAL'],
    'alert_frequency_limit': 300,  # Seconds between same alerts
    'emergency_contacts': []
}
```

## Configuration File Management

### 1. Configuration Files

The system uses multiple configuration approaches:
- **Python files**: For complex configuration logic
- **JSON files**: For simple key-value configurations
- **Environment variables**: For sensitive or environment-specific settings
- **Database storage**: For runtime-modifiable configurations

### 2. Configuration Validation

```python
def validate_configuration():
    """Validate system configuration before startup"""
    
    # Check IB connection parameters
    validate_ib_config()
    
    # Check database accessibility
    validate_database_config()
    
    # Check strategy configurations
    validate_strategy_configs()
    
    # Check risk management settings
    validate_risk_config()
    
    # Check resource availability
    validate_system_resources()
```

### 3. Configuration Updates

- **Runtime Updates**: Some configurations can be updated while system is running
- **Restart Required**: Critical configurations require system restart
- **Hot Reload**: Strategy parameters can often be updated without restart
- **Validation**: All configuration changes are validated before application
