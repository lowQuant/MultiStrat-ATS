"""
Strategy Manager for IB Multi-Strategy ATS using ib_async
"""
import asyncio
import threading
import asyncio
import queue
import os
import importlib.util
from typing import Optional, Dict, Any, List, Tuple
import pandas as pd
import json
from core.log_manager import add_log
from core.trade_manager import TradeManager
from core.portfolio_manager import PortfolioManager
from core.arctic_manager import get_ac
from utils.ib_connection import connect_to_ib, disconnect_from_ib, test_ib_connection


class StrategyManager:
    def __init__(self, arctic_client: Optional[object] = None):
        self.clientId = 0
        self.ib_client = None
        self.host = "127.0.0.1"
        self.port = 7497
        self.is_connected = False
        self.ac = arctic_client or get_ac()
        self.lib = self.ac.get_library('general')
        
        self.strategy_threads = []
        self.strategy_loops = {}
        self.strategies = []
        self.active_strategies = {}  # Dict to track running strategy instances
        self.next_client_id = 1  # Start strategy client IDs from 1
        
        # Initialize TradeManager and PortfolioManager
        self.trade_manager = None
        self.portfolio_manager = PortfolioManager(self)
        
        self.message_queue = queue.Queue()
        self.create_loop_in_thread = True
        self.message_processor_thread = threading.Thread(target=self.process_messages)
        self.message_processor_thread.daemon = True
        self.message_processor_thread.start()
        
        # Connect to IB on initialization like old backend
        print("Initializing StrategyManager and connecting to IB...", "StrategyManager")
        self._connect_on_init()

    def get_arctic_client(self):
        """Get ArcticDB client lazily to avoid blocking initialization"""
        if self.ac is None:
            self.ac = get_ac()
        return self.ac

    def _get_strategy_filename(self, sym: str) -> str:
        """Resolve filename for a given strategy symbol (uppercase) from ArcticDB metadata.
        Returns empty string if not found.
        """
        try:
            if not self.lib.has_symbol('strategies'):
                print("No strategies metadata found in ArcticDB (general/strategies)")
                return ""
            df = self.lib.read('strategies').data
            if df is None or df.empty:
                print("Strategies table is empty")
                return ""
            # Filter by strategy_symbol column (index may be numeric)
            mask = df['strategy_symbol'].astype(str).str.upper() == sym
            df_sym = df[mask]
            if df_sym.empty:
                print(f"Strategy symbol {sym} not found in metadata")
                return ""
            filename = str(df_sym.iloc[-1].get('filename') or '').strip()
            return filename
        except Exception as e:
            add_log(f"Error reading strategy metadata for {sym}: {e}", "CORE", "ERROR")
            return ""

    def _connect_on_init(self):
        """Connect to IB during initialization (sync version for __init__)"""
        try:
            # Try to connect synchronously during init
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're in an async context, schedule the connection
                    loop.create_task(self._async_connect_on_init())
                else:
                    # Run the async connection in the current loop
                    loop.run_until_complete(self._async_connect_on_init())
            except RuntimeError:
                # No event loop, create one for the connection
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._async_connect_on_init())
                finally:
                    loop.close()
        except Exception as e:
            add_log(f"StrategyManager initialization connection failed: {e}", "CORE", "ERROR")

    async def _async_connect_on_init(self):
        """Async helper for initial connection"""
        success = await self.connect_to_ib()
        if not success:
            add_log("StrategyManager initialization connection failed", "CORE", "ERROR")

    async def connect_to_ib(self):
        """Connect to IB"""
        try:
            self.ib_client = await connect_to_ib(client_id=self.clientId, existing_ib=self.ib_client)
            if self.ib_client:
                self.is_connected = True
                # Initialize TradeManager when IB connection is established
                self.trade_manager = TradeManager(self.ib_client, self)
                print("TradeManager initialized with IB connection")
                return True
            else:
                return False
        except Exception as e:
            return False

    def process_messages(self):
        if self.create_loop_in_thread:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.create_loop_in_thread = False
        try:
            while True:
                message = self.message_queue.get(block=True)
                # Run message handling in the thread's event loop for WebSocket broadcasting
                self.loop.run_until_complete(self.handle_message_async(message))
        except Exception as e:
            add_log(f"Error processing message: {e}", "CORE", "ERROR")
        finally:
            if hasattr(self, 'loop'):
                self.loop.close()

    async def handle_message_async(self, message):
        """Async version of handle_message for proper WebSocket broadcasting"""
        try:
            from core.log_manager import add_log as add_log_for_queue
            print(f"Received message: Type: {message['type']} /n {str(message)}")
            
            # Make add_log_for_queue available to other async methods
            self._queue_add_log = add_log_for_queue
            
            if message['type'] == 'order':
                await self.notify_order_placement_async(message['strategy'], message['trade'])
            elif message['type'] == 'fill':
                await self.handle_fill_event_async(message['strategy'], message['trade'], message['fill'])
            elif message['type'] == 'status_change':
                await self.handle_status_change_async(message['strategy'], message['trade'], message['status'])
                
            self.message_queue.task_done()
        except Exception as e:
            add_log_for_queue(f"Exception in handling message: {e}", "CORE", level="ERROR")

    async def notify_order_placement_async(self, strategy, trade):
        """Async version for WebSocket broadcasting"""
        symbol = trade.contract.symbol if hasattr(trade.contract, 'symbol') else "N/A"
        order_type = trade.order.orderType
        action = trade.order.action
        quantity = trade.order.totalQuantity

        if trade.isDone():
            message = f"{trade.fills[0].execution.side} {trade.orderStatus.filled} {trade.contract.symbol}@{trade.orderStatus.avgFillPrice} [{trade.order.orderRef}]"
            self._queue_add_log(message, strategy)
        else:
            message = f"{order_type} Order placed: {action} {quantity} {symbol} "
            self._queue_add_log(message, strategy)

    async def handle_fill_event_async(self, strategy_symbol, trade, fill):
        """Async version for WebSocket broadcasting and portfolio management"""
        message = f"{trade.fills[0].execution.side} {trade.orderStatus.filled} {trade.contract.symbol}@{trade.orderStatus.avgFillPrice} [{strategy_symbol}]"
        self._queue_add_log(message, strategy_symbol)
        
        # Process fill in PortfolioManager
        await self.portfolio_manager.process_fill(strategy_symbol, trade, fill)

    async def handle_status_change_async(self, strategy_symbol, trade, status):
        """Async version for WebSocket broadcasting and portfolio management"""
        if "Pending" not in status:
            message = f"{status}: {trade.order.action} {trade.order.totalQuantity} {trade.contract.symbol} [{strategy_symbol}]"
            self._queue_add_log(message, strategy_symbol)
            
            # Record status change in PortfolioManager
            await self.portfolio_manager.record_status_change(strategy_symbol, trade, status)

    async def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed connection status for all clients"""
        status = {
            "master_connection": {
                "connected": self.is_connected,
                "client_id": self.clientId,
                "host": self.host,
                "port": self.port
            },
            "strategy_connections": []
        }
        
        # Add strategy connections
        for name, strategy in self.active_strategies.items():
            if hasattr(strategy, 'is_connected') and hasattr(strategy, 'client_id'):
                status["strategy_connections"].append({
                    "strategy_name": name,
                    "client_id": strategy.client_id,
                    "connected": strategy.is_connected,
                    "symbol": getattr(strategy, 'symbol', 'N/A')
                })
        
        return status

    async def disconnect_client(self, client_id: int) -> bool:
        """Disconnect a specific client by client_id. 0 disconnects master; >0 disconnects a strategy IB session."""
        if client_id == 0:
            await self.disconnect()
            return True

        for name, strat in list(self.active_strategies.items()):
            if getattr(strat, "client_id", None) == client_id:
                try:
                    strat.stop_strategy()  # triggers its own disconnect
                    add_log(f"Disconnected strategy {name} (clientId={client_id})", "CORE")
                except Exception as e:
                    add_log(f"Error disconnecting strategy {name}: {e}", "CORE", "ERROR")
                return True
        return False

    async def disconnect_all(self) -> None:
        """Disconnect all strategies and the master connection."""
        add_log("Disconnecting all connections...", "CORE")
        self.stop_all_strategies()
        await self.disconnect()

    async def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed connection status for all clients"""
        status = {
            "master_connection": {
                "connected": self.is_connected,
                "client_id": self.clientId,
                "host": self.host,
                "port": self.port
            },
            "strategy_connections": []
        }
        
        # Add strategy connections
        for name, strategy in self.active_strategies.items():
            if hasattr(strategy, 'is_connected') and hasattr(strategy, 'client_id'):
                status["strategy_connections"].append({
                    "strategy_name": name,
                    "client_id": strategy.client_id,
                    "connected": strategy.is_connected,
                    "symbol": getattr(strategy, 'symbol', 'N/A')
                })
        
        return status

    async def test_connection(self) -> Dict[str, Any]:
        """Return current connection status instead of testing"""
        if self.is_connected and self.ib_client:
            try:
                result = await test_ib_connection(self.ib_client)
                return result
            except Exception as e:
                # Connection might be stale, try to reconnect
                await self._initialize_connection()
                if self.is_connected:
                    return await test_ib_connection(self.ib_client)
                else:
                    raise Exception(f"Connection test failed: {e}")
        else:
            # Try to reconnect
            await self._initialize_connection()
            if self.is_connected:
                return await test_ib_connection(self.ib_client)
            else:
                raise Exception("Not connected to IB")

    async def disconnect(self):
        """Disconnect from IB"""
        if self.ib_client and self.is_connected:
            await disconnect_from_ib(self.ib_client)
            self.is_connected = False

    def get_orders(self):
        return self.ib_client.orders() if self.ib_client else []

    def get_open_orders(self):
        return self.ib_client.openOrders() if self.ib_client else []

    def stop_all_strategy_threads(self):
        """Stop all strategy event loops/threads and reset thread bookkeeping"""
        for client_id, loop in self.strategy_loops.items():
            loop.call_soon_threadsafe(loop.stop)

        for thread in self.strategy_threads:
            thread.join(timeout=10)
            if thread.is_alive():
                add_log(f"Strategy thread {thread.name} did not terminate in time", "CORE", "WARNING")
            else:
                add_log(f"Strategy thread {thread.name} terminated", "CORE")

        self.strategy_threads = []
        self.strategies = []
        self.strategy_loops = {}

    def stop_all_strategies(self):
        """Stop all running strategies"""
        strategy_names = list(self.active_strategies.keys())
        for strategy_name in strategy_names:
            self.stop_strategy(strategy_name)
        # After asking strategies to stop, ensure all loops/threads are torn down
        self.stop_all_strategy_threads()

    def list_strategy_files(self) -> List[str]:
        """
        List available strategy files in the strategies directory.
        Returns a list of strategy filenames.
        """
        # Use absolute path to strategies directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(current_dir)
        strategy_dir = os.path.join(backend_dir, "strategies")
        
        strategy_files = []
        
        if os.path.exists(strategy_dir):
            for file in os.listdir(strategy_dir):
                if file.endswith(".py") and file != "base_strategy.py":
                    strategy_files.append(file)
            
            # Single log message with all discovered strategies
            if strategy_files:
                print(f"Available {len(strategy_files)} strategies: {', '.join(strategy_files)}")
            else:
                print("No strategies found in directory")
        else:
            print(f"Strategy directory not found: {strategy_dir}")
        
        return strategy_files
    
    def load_strategy_params(self, strategy_symbol: str, module: Any) -> Dict[str, Any]:
        """
        Load parameters for a strategy, checking ArcticDB first, then the file's PARAMS dict.
        If params are loaded from the file, they are persisted to ArcticDB for future loads.
        """
        try:
            # 1. Check ArcticDB for existing params
            lib = self.ac.get_library('general')
            if lib.has_symbol('strategies'):
                strat_df = lib.read('strategies').data
                # Case-insensitive match on strategy_symbol
                mask = strat_df['strategy_symbol'].astype(str).str.upper() == str(strategy_symbol).upper()
                strat_row = strat_df[mask]
                if not strat_row.empty and 'params' in strat_row.columns:
                    params_val = strat_row.iloc[-1].get('params')
                    # Accept either a JSON string or a dict already
                    if isinstance(params_val, dict) and params_val:
                        add_log(f"Loaded params for {strategy_symbol} from ArcticDB (dict)", "CORE")
                        return params_val
                    if isinstance(params_val, str) and params_val.strip() and params_val.strip() != '{}':
                        try:
                            params = json.loads(params_val)
                            add_log(f"Loaded params for {strategy_symbol} from ArcticDB", "CORE")
                            return params
                        except json.JSONDecodeError:
                            add_log(f"Failed to decode params JSON for {strategy_symbol}: {params_val}", "CORE", "ERROR")

            # 2. If not in Arctic, load from the module's global PARAMS
            if hasattr(module, 'PARAMS') and isinstance(module.PARAMS, dict):
                add_log(f"Loading params for {strategy_symbol} from file and saving to ArcticDB", "CORE")
                params = module.PARAMS
                
                # 3. Save to ArcticDB
                if lib.has_symbol('strategies'):
                    strat_df = lib.read('strategies').data
                    # Case-insensitive match
                    mask = strat_df['strategy_symbol'].astype(str).str.upper() == str(strategy_symbol).upper()
                    if mask.any():
                        # Use a copy to avoid SettingWithCopyWarning
                        new_df = strat_df.copy()
                        # Serialize params to a JSON string before saving (consistent storage)
                        params_json = json.dumps(params)
                        # Ensure 'params' column exists; pandas will create if missing
                        new_df.loc[mask, 'params'] = params_json
                        lib.write('strategies', new_df, metadata={'source': 'strategy_manager'})
                        add_log(f"Saved params for {strategy_symbol} to ArcticDB", "CORE")
                return params
            else:
                add_log(f"No PARAMS dictionary found for {strategy_symbol} in its file.", "CORE", "WARNING")
                return {}

        except Exception as e:
            add_log(f"Error loading params for {strategy_symbol}: {e}", "CORE", "ERROR")
            return {}

    def load_strategy_class(self, filename: str) -> Tuple[Optional[type], Optional[Any]]:
        """
        Dynamically load a strategy class from a Python file
        """
        try:
            # Use absolute path to strategies directory
            current_dir = os.path.dirname(os.path.abspath(__file__))
            backend_dir = os.path.dirname(current_dir)
            strategy_path = os.path.join(backend_dir, "strategies", filename)
            module_name = filename[:-3]  # Remove .py extension
            
            spec = importlib.util.spec_from_file_location(module_name, strategy_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Look for strategy classes (should end with 'Strategy').
            # Prefer non-backtest variants to avoid accidentally selecting a backtest helper class.
            candidates = []
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and attr_name.endswith('Strategy')
                    and attr_name != 'BaseStrategy'
                ):
                    candidates.append((attr_name, attr))

            # Prefer classes without 'Backtest' in the name
            preferred = [c for c in candidates if 'Backtest' not in c[0]]
            chosen = preferred[0] if preferred else (candidates[0] if candidates else None)

            if chosen:
                print(f"Loaded strategy class: {chosen[0]}")
                return chosen[1], module
            
            print(f"No strategy class found in {filename}")
            return None, None
            
        except Exception as e:
            add_log(f"Error loading strategy {filename}: {e}", "CORE", "ERROR")
            return None, None
    
    def start_strategy(self, strategy_symbol: str) -> bool:
        """Start a specific strategy by its strategy_symbol (uses metadata to resolve filename)."""
        sym = (strategy_symbol or "").upper()
        if sym in self.active_strategies:
            add_log(f"Strategy {sym} is already running", "CORE", "WARNING")
            return False

        filename = self._get_strategy_filename(sym)
        if not filename:
            return False

        strategy_class, strategy_module = self.load_strategy_class(filename)
        if not strategy_class or not strategy_module:
            add_log(f"Could not load strategy class or module for {sym}", "CORE", "ERROR")
            return False

        # Load strategy parameters
        params = self.load_strategy_params(sym, strategy_module)

        try:
            # Create strategy instance with unique client ID
            client_id = self.next_client_id
            self.next_client_id += 1
            
            strategy_instance = strategy_class(
                client_id=client_id,
                strategy_manager=self,
                params=params,
                strategy_symbol=sym,
            )
            strategy_instance.start_strategy()
            self.active_strategies[sym] = strategy_instance
            add_log(f"Started strategy {sym} with clientId={client_id}", "CORE")
            return True
        except Exception as e:
            add_log(f"Error starting strategy {sym}: {e}", "CORE", "ERROR")
            return False
    
    def stop_strategy(self, strategy_symbol: str) -> bool:
        """Stop a specific strategy by its strategy_symbol."""
        sym = (strategy_symbol or "").upper()
        if sym not in self.active_strategies:
            add_log(f"Strategy {sym} is not running", "CORE", "WARNING")
            return False

        try:
            strategy_instance = self.active_strategies[sym]
            strategy_instance.stop_strategy()
            del self.active_strategies[sym]
            print(f"Stopped strategy {sym}")
            return True
        except Exception as e:
            add_log(f"Error stopping strategy {sym}: {e}", "CORE", "ERROR")
            return False
    
    def start_all_strategies(self) -> Dict[str, bool]:
        """
        Start all discovered strategies
        Returns dict of strategy_name: success_status
        """
        strategy_files = self.list_strategy_files()
        results = {}
        
        for filename in strategy_files:
            strategy_name = filename.replace("_strategy.py", "").upper()
            results[strategy_name] = self.start_strategy(strategy_name)
        
        return results
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """
        Get status of all strategies
        """
        status = {
            "active_count": len(self.active_strategies),
            "next_client_id": self.next_client_id,
            "strategies": {}
        }
        
        for name, strategy in self.active_strategies.items():
            status["strategies"][name] = strategy.get_status()
        
        return status

    async def cleanup(self):
        """Cleanup all resources"""
        self.stop_all_strategies()
        await self.disconnect()
