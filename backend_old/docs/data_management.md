# Data Management Documentation

## Overview

The data management module provides comprehensive data handling capabilities for the IB Multi-Strategy ATS, including market data retrieval, historical data storage, and data processing workflows. The system integrates with ArcticDB for high-performance time-series data storage and supports both real-time and historical data operations.

## Module Structure

```
data_and_research/
├── __init__.py           # Module initialization and ArcticDB setup
├── data_manager.py       # Core data management class
├── utils.py             # Data utilities and helper functions
├── jobs/                # Scheduled data collection jobs
├── notebooks/           # Research and analysis notebooks
└── db/                  # Database files and configurations
```

## Core Components

### 1. DataManager Class (`data_manager.py`)

The central data management component that handles all data operations.

#### Key Features:
- **ArcticDB Integration**: High-performance time-series data storage
- **External Script Execution**: Run and schedule data collection scripts
- **Job Management**: Schedule and manage recurring data tasks
- **Data Retrieval**: Efficient data access and querying

#### Key Methods:

**Data Storage Operations:**
```python
def store_data_from_external_scripts(self, script_name, library, symbol, append=False):
    """Load and execute external script, store resulting DataFrame in ArcticDB"""
    
def get_data_from_arctic(self, library_name, symbol):
    """Retrieve data for a given symbol from Arctic library"""
```

**Job Management:**
```python
def save_new_job(self, filename, cron_notation, cron_command, operating_system, execution_method):
    """Save a scheduled task/job to ArcticDB"""
    
def get_saved_jobs(self):
    """Retrieve all saved jobs from ArcticDB"""
```

**Script Execution:**
```python
def run_python_script(self, script_path):
    """Execute an external Python script"""
    
def schedule_python_script(self, script_path, schedule_time):
    """Schedule a Python script to run at specific time"""
```

### 2. Data Utilities (`utils.py`)

Collection of utility functions for data processing and strategy management.

#### Key Functions:

**Strategy Management:**
```python
def fetch_strategies():
    """Fetch strategy configuration from ArcticDB"""
    
def save_strategy_config(strategy_data):
    """Save strategy configuration to ArcticDB"""
```

**Data Processing:**
```python
def process_market_data(data):
    """Process and clean market data"""
    
def calculate_technical_indicators(data):
    """Calculate technical indicators for trading strategies"""
```

**Database Operations:**
```python
def initialize_arctic_libraries():
    """Initialize required ArcticDB libraries"""
    
def backup_data(library_name, symbol):
    """Backup data from ArcticDB"""
```

## ArcticDB Integration

### 1. Database Architecture

The system uses ArcticDB for high-performance time-series data storage:

```python
# From data_and_research/__init__.py
import arcticdb as adb
ac = adb.Arctic('lmdb://./data_and_research/db/arctic_db')
```

### 2. Library Structure

Data is organized into logical libraries:
- **market_data**: Real-time and historical market data
- **strategies**: Strategy configurations and parameters
- **portfolios**: Portfolio positions and performance data
- **jobs**: Scheduled task configurations
- **research**: Research data and analysis results

### 3. Data Storage Patterns

**Time-Series Data:**
```python
# Store market data with timestamp index
lib = ac.get_library('market_data', create_if_missing=True)
lib.write('AAPL', market_data_df)
```

**Configuration Data:**
```python
# Store strategy configurations
lib = ac.get_library('strategies', create_if_missing=True)
lib.write('active_strategies', strategy_config_df)
```

**Append Operations:**
```python
# Append new data to existing time series
if symbol in lib.list_symbols():
    lib.append(symbol, new_data_df)
else:
    lib.write(symbol, new_data_df)
```

## Data Collection Workflows

### 1. Market Data Collection

The system supports multiple data sources:

**Interactive Brokers Data:**
- Real-time market data through IB API
- Historical data requests
- Fundamental data retrieval

**External Data Sources:**
- yfinance integration for additional market data
- Custom data providers through external scripts
- Alternative data sources

### 2. Scheduled Data Jobs

The system includes a job scheduling framework:

**Job Configuration:**
```python
job_data = {
    "filename": "collect_market_data.py",
    "cron_notation": "0 9 * * 1-5",  # Weekdays at 9 AM
    "operating_system": "macOS",
    "execution_method": "Centralized",
    "arctic_path": "market_data/AAPL"
}
```

**Job Execution:**
- Centralized execution through DataManager
- Distributed execution on multiple machines
- Error handling and retry mechanisms

### 3. Data Processing Pipeline

**Raw Data → Processing → Storage → Strategy Consumption**

1. **Collection**: Gather data from various sources
2. **Validation**: Data quality checks and cleaning
3. **Processing**: Technical indicators and transformations
4. **Storage**: Efficient storage in ArcticDB
5. **Distribution**: Make available to strategies

## Integration with Trading System

### 1. Strategy Data Access

Strategies access data through the DataManager:

```python
# In strategy implementation
data_manager = self.strategy_manager.data_manager
historical_data = data_manager.get_data_from_arctic('market_data', 'AAPL')
```

### 2. Real-Time Data Flow

```
IB API → DataManager → ArcticDB → Strategy Consumption
                   ↓
              Real-time Processing
```

### 3. Portfolio Data Integration

Portfolio data is automatically stored and retrieved:
- Position updates stored in real-time
- Historical portfolio performance tracking
- Strategy attribution and analysis

## External Script Integration

### 1. Script Execution Framework

The system can execute external Python scripts for data collection:

```python
# Example external script structure
def main():
    # Data collection logic
    data = collect_market_data()
    return processed_dataframe

if __name__ == "__main__":
    result = main()
```

### 2. GitHub Workflow Integration

Based on the memory about the user's setup, the system integrates with GitHub workflows:

**US Stock Data Download Workflow:**
- Runs Monday-Friday every morning
- Uses yfinance for data collection
- Processes data with technical indicators
- Stores results in ArcticDB
- Handles TA-Lib compilation and numpy compatibility

### 3. Data Source Management

**Supported Data Sources:**
- Interactive Brokers API
- yfinance (Yahoo Finance)
- Custom data providers
- File-based data imports
- API-based data feeds

## Performance Optimization

### 1. Data Storage Optimization

**ArcticDB Features:**
- Columnar storage for efficient queries
- Compression for reduced storage requirements
- Indexing for fast data retrieval
- Concurrent read/write operations

### 2. Query Optimization

```python
# Efficient data retrieval patterns
def get_recent_data(self, symbol, days=30):
    """Get recent data with date filtering"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    lib = self.arctic.get_library('market_data')
    data = lib.read(symbol, date_range=(start_date, end_date)).data
    return data
```

### 3. Caching Strategies

- In-memory caching for frequently accessed data
- Redis integration for distributed caching
- Smart cache invalidation policies

## Data Quality and Validation

### 1. Data Validation Framework

```python
def validate_market_data(data):
    """Validate market data quality"""
    checks = [
        check_missing_values,
        check_price_consistency,
        check_volume_validity,
        check_timestamp_ordering
    ]
    
    for check in checks:
        if not check(data):
            raise DataValidationError(f"Failed {check.__name__}")
```

### 2. Error Handling

- Graceful handling of data source failures
- Automatic retry mechanisms
- Data quality alerts and notifications
- Fallback data sources

### 3. Data Monitoring

- Real-time data quality monitoring
- Data freshness checks
- Source availability monitoring
- Performance metrics tracking

## Configuration and Setup

### 1. Database Configuration

```python
# ArcticDB setup
ARCTIC_URI = 'lmdb://./data_and_research/db/arctic_db'
ac = adb.Arctic(ARCTIC_URI)
```

### 2. Data Source Configuration

- API credentials management
- Data source endpoints
- Update frequencies and schedules
- Data retention policies

### 3. Performance Tuning

- Memory allocation settings
- Concurrent operation limits
- Cache size configurations
- Network timeout settings

## Research and Analysis Tools

### 1. Jupyter Notebook Integration

The `notebooks/` directory contains research tools:
- Data exploration notebooks
- Strategy backtesting frameworks
- Performance analysis tools
- Market research templates

### 2. Analysis Utilities

```python
# Research helper functions
def backtest_strategy(strategy_data, market_data):
    """Backtest a strategy against historical data"""
    
def calculate_performance_metrics(returns):
    """Calculate comprehensive performance metrics"""
    
def generate_research_report(analysis_results):
    """Generate formatted research reports"""
```

### 3. Data Visualization

- Interactive charts and graphs
- Performance dashboards
- Market analysis visualizations
- Strategy comparison tools
