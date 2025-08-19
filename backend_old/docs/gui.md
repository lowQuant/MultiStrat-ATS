# GUI Module Documentation

## Overview

The GUI module provides a comprehensive graphical user interface for the IB Multi-Strategy ATS system. Built with modern UI frameworks, it offers real-time monitoring, configuration management, and interactive control of the trading system. The interface is designed for both novice and experienced traders, providing intuitive access to complex trading operations.

## Module Structure

```
gui/
├── __init__.py              # Module initialization and main entry point
├── gui.py                   # Main GUI application and window management
├── database_window.py       # Database management interface
├── portfolio_window.py      # Portfolio monitoring and analysis
├── settings_window.py       # System configuration interface
├── log.py                   # Logging system integration
├── utils.py                 # GUI utility functions
└── assets/                  # UI assets (icons, images, stylesheets)
```

## Core Components

### 1. Main GUI Application (`gui.py`)

The central GUI controller that manages the main application window and coordinates between different interface components.

#### Key Features:
- **Main Dashboard**: Overview of system status and key metrics
- **Window Management**: Coordinates multiple specialized windows
- **Real-time Updates**: Live data feeds and status updates
- **Navigation**: Central hub for accessing all system features

#### Key Functions:
```python
def run_gui():
    """Main entry point for GUI application"""
    
def initialize_main_window():
    """Set up the main application window"""
    
def update_dashboard():
    """Update real-time dashboard information"""
```

### 2. Database Management Window (`database_window.py`)

Comprehensive interface for managing ArcticDB data and system databases.

#### Key Features:
- **Data Browser**: Navigate and explore stored data
- **Query Interface**: Execute custom data queries
- **Data Import/Export**: Manage data transfers
- **Library Management**: Create and manage ArcticDB libraries
- **Job Scheduling**: Configure and monitor data collection jobs

#### Key Sections:
```python
class DatabaseWindow:
    def __init__(self):
        self.setup_data_browser()
        self.setup_query_interface()
        self.setup_job_manager()
        self.setup_import_export()
```

**Data Browser Features:**
- Tree view of all ArcticDB libraries and symbols
- Data preview with filtering and sorting
- Metadata display (data types, date ranges, record counts)
- Search functionality across libraries

**Job Management:**
- Visual job scheduler interface
- Cron expression builder
- Job status monitoring
- Execution history and logs

### 3. Portfolio Window (`portfolio_window.py`)

Real-time portfolio monitoring and analysis interface.

#### Key Features:
- **Position Tracking**: Real-time position display
- **P&L Monitoring**: Profit and loss tracking per strategy
- **Risk Metrics**: Portfolio risk analysis and monitoring
- **Performance Analytics**: Historical performance visualization
- **Trade History**: Complete trade execution history

#### Dashboard Sections:
```python
class PortfolioWindow:
    def setup_positions_view(self):
        """Display current positions by strategy"""
        
    def setup_pnl_tracking(self):
        """Real-time P&L monitoring"""
        
    def setup_risk_dashboard(self):
        """Risk metrics and controls"""
        
    def setup_performance_charts(self):
        """Performance visualization"""
```

**Position Display:**
- Strategy-level position breakdown
- Real-time market values
- Unrealized P&L calculations
- Position sizing and allocation

**Performance Analytics:**
- Interactive charts and graphs
- Strategy comparison tools
- Benchmark analysis
- Risk-adjusted returns

### 4. Settings Window (`settings_window.py`)

Comprehensive system configuration interface.

#### Configuration Sections:

**Strategy Management:**
- Strategy activation/deactivation
- Parameter configuration
- Strategy-specific settings
- Performance monitoring setup

**Connection Settings:**
- Interactive Brokers connection parameters
- API configuration
- Timeout and retry settings
- Connection health monitoring

**Risk Management:**
- Position size limits
- Maximum drawdown controls
- Stop-loss configurations
- Emergency stop mechanisms

**Data Sources:**
- Market data provider settings
- Data update frequencies
- Historical data management
- External data source configuration

#### Key Features:
```python
class SettingsWindow:
    def setup_strategy_config(self):
        """Strategy configuration interface"""
        
    def setup_connection_settings(self):
        """IB connection configuration"""
        
    def setup_risk_controls(self):
        """Risk management settings"""
        
    def setup_data_sources(self):
        """Data source configuration"""
```

### 5. Logging System (`log.py`)

Integrated logging interface that provides real-time system monitoring.

#### Features:
- **Real-time Log Display**: Live log streaming
- **Log Filtering**: Filter by severity, component, or strategy
- **Log Search**: Search through historical logs
- **Export Functionality**: Export logs for analysis

#### Integration:
```python
def add_log(message, level='INFO', component='SYSTEM'):
    """Add log entry with automatic GUI update"""
    
def setup_log_viewer():
    """Initialize the log viewing interface"""
```

### 6. GUI Utilities (`utils.py`)

Collection of utility functions for GUI operations.

#### Key Utilities:
- **Data Formatting**: Format financial data for display
- **Chart Helpers**: Chart creation and updating functions
- **Validation**: Input validation for forms
- **Styling**: Consistent styling and theming

## User Interface Design

### 1. Main Dashboard Layout

```
┌─────────────────────────────────────────────────────────────┐
│ IB Multi-Strategy ATS                    [Settings] [Help]  │
├─────────────────────────────────────────────────────────────┤
│ System Status: ●CONNECTED    Strategies: 5 Active          │
├─────────────────┬───────────────────────┬───────────────────┤
│ Portfolio       │ Active Strategies     │ Recent Activity   │
│ Total P&L: +$X  │ ● Strategy A: +$Y     │ 10:30 - Order     │
│ Positions: N    │ ● Strategy B: +$Z     │ 10:25 - Fill      │
│ Cash: $X        │ ● Strategy C: -$W     │ 10:20 - Alert     │
├─────────────────┼───────────────────────┼───────────────────┤
│ [Portfolio]     │ [Database]            │ [Logs]            │
│ [Settings]      │ [Research]            │ [Help]            │
└─────────────────┴───────────────────────┴───────────────────┘
```

### 2. Window Management

The GUI uses a multi-window approach:
- **Main Window**: Central dashboard and navigation
- **Portfolio Window**: Detailed portfolio analysis
- **Database Window**: Data management interface
- **Settings Window**: Configuration management
- **Modal Dialogs**: For specific tasks and confirmations

### 3. Real-time Updates

The interface provides real-time updates through:
- **WebSocket Connections**: For live data feeds
- **Event-driven Updates**: Automatic refresh on data changes
- **Polling Mechanisms**: For less critical data
- **Push Notifications**: For important alerts

## Integration with Core System

### 1. Strategy Manager Integration

The GUI interfaces directly with the StrategyManager:

```python
# Strategy control from GUI
def start_strategies():
    strategy_manager.start_all()
    
def stop_strategies():
    strategy_manager.stop_all()
    
def get_strategy_status():
    return strategy_manager.get_status()
```

### 2. Data Manager Integration

Real-time data access through DataManager:

```python
# Data retrieval for GUI display
def update_portfolio_display():
    positions = data_manager.get_data_from_arctic('portfolios', 'current_positions')
    update_portfolio_table(positions)
```

### 3. Broker Module Integration

Direct integration with trading operations:

```python
# Order management from GUI
def place_manual_order(contract, order):
    trade_manager.place_order(contract, order, 'MANUAL')
    
def cancel_order(order_id):
    trade_manager.cancel_order(order_id)
```

## User Experience Features

### 1. Responsive Design

- **Adaptive Layout**: Adjusts to different screen sizes
- **Resizable Components**: Flexible window and panel sizing
- **Mobile Support**: Touch-friendly interface elements

### 2. Customization Options

- **Dashboard Layout**: Customizable widget arrangement
- **Color Themes**: Multiple theme options
- **Data Display**: Configurable table columns and charts
- **Alert Preferences**: Customizable notification settings

### 3. Accessibility Features

- **Keyboard Navigation**: Full keyboard accessibility
- **High Contrast Modes**: For visual accessibility
- **Font Size Controls**: Adjustable text sizing
- **Screen Reader Support**: Compatibility with assistive technologies

## Performance Optimization

### 1. Efficient Data Handling

- **Virtual Scrolling**: For large data tables
- **Lazy Loading**: Load data on demand
- **Data Caching**: Cache frequently accessed data
- **Batch Updates**: Minimize UI refresh operations

### 2. Memory Management

- **Resource Cleanup**: Proper cleanup of UI resources
- **Memory Monitoring**: Track memory usage
- **Garbage Collection**: Efficient memory management
- **Data Pagination**: Handle large datasets efficiently

### 3. Network Optimization

- **Connection Pooling**: Efficient network connections
- **Data Compression**: Compress data transfers
- **Caching Strategies**: Reduce network requests
- **Offline Capabilities**: Handle network interruptions

## Security and Access Control

### 1. User Authentication

- **Login System**: Secure user authentication
- **Session Management**: Secure session handling
- **Password Security**: Strong password requirements
- **Multi-factor Authentication**: Optional 2FA support

### 2. Data Protection

- **Encrypted Communication**: Secure data transmission
- **Local Data Encryption**: Protect stored data
- **Access Logging**: Track user actions
- **Data Masking**: Hide sensitive information

### 3. Operational Security

- **Input Validation**: Prevent injection attacks
- **Error Handling**: Secure error messages
- **Audit Trails**: Complete action logging
- **Backup Integration**: Secure data backup

## Customization and Extensions

### 1. Plugin Architecture

- **Custom Widgets**: Add new dashboard widgets
- **Strategy Displays**: Custom strategy monitoring
- **Data Visualizations**: Custom chart types
- **Alert Systems**: Custom notification methods

### 2. Theme System

- **Custom Themes**: Create custom color schemes
- **Layout Templates**: Predefined layout options
- **Branding Options**: Custom logos and styling
- **Export/Import**: Share theme configurations

### 3. API Integration

- **External Tools**: Integration with external applications
- **Data Export**: Export data to external systems
- **Webhook Support**: Real-time data sharing
- **REST API**: Programmatic access to GUI functions
