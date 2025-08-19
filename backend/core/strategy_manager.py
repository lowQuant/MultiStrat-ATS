"""
Strategy Manager for IB Multi-Strategy ATS using ib_async
"""
import asyncio
import threading
import asyncio
import queue
import os
import importlib.util
from typing import Optional, Dict, Any, List
from core.log_manager import add_log
from utils.ib_connection import connect_to_ib, disconnect_from_ib, test_ib_connection


class StrategyManager:
    def __init__(self):
        self.clientId = 0
        self.ib_client = None
        self.host = "127.0.0.1"
        self.port = 7497
        self.is_connected = False
        
        self.strategy_threads = []
        self.strategy_loops = {}
        self.strategies = []
        self.active_strategies = {}  # Dict to track running strategy instances
        self.next_client_id = 1  # Start strategy client IDs from 1
        
        self.message_queue = queue.Queue()
        self.create_loop_in_thread = True
        self.message_processor_thread = threading.Thread(target=self.process_messages)
        self.message_processor_thread.daemon = True
        self.message_processor_thread.start()

    def process_messages(self):
        if self.create_loop_in_thread:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.create_loop_in_thread = False
        try:
            while True:
                message = self.message_queue.get(block=True)
                self.handle_message(message)
        except Exception as e:
            add_log(f"Error processing message: {e}", "StrategyManager", "ERROR")
        finally:
            if hasattr(self, 'loop'):
                self.loop.close()

    def handle_message(self, message):
        try:
            add_log(f"Received message: Type: {message['type'].upper()} [{message['strategy']}]", "StrategyManager")
            
            if message['type'] == 'order':
                self.notify_order_placement(message['strategy'], message['trade'])
            elif message['type'] == 'fill':
                self.handle_fill_event(message['strategy'], message['trade'], message['fill'])
            elif message['type'] == 'status_change':
                self.handle_status_change(message['strategy'], message['trade'], message['status'])
                
            self.message_queue.task_done()
        except Exception as e:
            add_log(f"Exception in handling message: {e}", "StrategyManager", "ERROR")

    def notify_order_placement(self, strategy, trade):
        symbol = trade.contract.symbol if hasattr(trade.contract, 'symbol') else "N/A"
        order_type = trade.order.orderType
        action = trade.order.action
        quantity = trade.order.totalQuantity

        if trade.isDone():
            add_log(f"{trade.fills[0].execution.side} {trade.orderStatus.filled} {trade.contract.symbol}@{trade.orderStatus.avgFillPrice} [{trade.order.orderRef}]", strategy)
        else:
            add_log(f"{order_type} Order placed: {action} {quantity} {symbol} [{strategy}]", strategy)

    def handle_fill_event(self, strategy_symbol, trade, fill):
        add_log(f"{trade.fills[0].execution.side} {trade.orderStatus.filled} {trade.contract.symbol}@{trade.orderStatus.avgFillPrice} [{strategy_symbol}]", strategy_symbol)

    def handle_status_change(self, strategy_symbol, trade, status):
        if "Pending" not in status:
            add_log(f"{status}: {trade.order.action} {trade.order.totalQuantity} {trade.contract.symbol} [{strategy_symbol}]", strategy_symbol)

    async def test_connection(self) -> Dict[str, Any]:
        """Test IB connection and return connection details"""
        self.ib_client = await connect_to_ib(client_id=self.clientId)
        if not self.ib_client:
            raise Exception("Could not connect to IB")
        
        self.is_connected = True
        try:
            return await test_ib_connection(self.ib_client)
        except Exception as e:
            await self.disconnect()
            raise Exception(f"Connection test failed: {e}")

    async def disconnect(self):
        """Disconnect from IB"""
        if self.ib_client and self.is_connected:
            await disconnect_from_ib(self.ib_client)
            self.is_connected = False

    def get_orders(self):
        return self.ib_client.orders() if self.ib_client else []

    def get_open_orders(self):
        return self.ib_client.openOrders() if self.ib_client else []

    def stop_all_strategies(self):
        """Stop all running strategies and threads"""
        for client_id, loop in self.strategy_loops.items():
            add_log(f"Stopping strategy {client_id}...", "StrategyManager")
            loop.call_soon_threadsafe(loop.stop)

        for thread in self.strategy_threads:
            thread.join(timeout=10)
            if thread.is_alive():
                add_log(f"Strategy thread {thread.name} did not terminate in time", "StrategyManager", "WARNING")
            else:
                add_log(f"Strategy thread {thread.name} has terminated", "StrategyManager")

        self.strategy_threads = []
        self.strategies = []
        self.strategy_loops = {}

    def discover_strategies(self) -> List[str]:
        """
        Discover available strategy files in the strategies directory
        Returns list of strategy filenames
        """
        strategy_dir = "strategies"
        strategy_files = []
        
        if os.path.exists(strategy_dir):
            for file in os.listdir(strategy_dir):
                if file.endswith(".py") and file != "base_strategy.py":
                    strategy_files.append(file)
                    add_log(f"Discovered strategy: {file}", "StrategyManager")
        
        return strategy_files
    
    def load_strategy_class(self, filename: str):
        """
        Dynamically load a strategy class from a Python file
        """
        try:
            strategy_path = os.path.join("strategies", filename)
            module_name = filename[:-3]  # Remove .py extension
            
            spec = importlib.util.spec_from_file_location(module_name, strategy_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Look for strategy classes (should end with 'Strategy')
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    attr_name.endswith('Strategy') and 
                    attr_name != 'BaseStrategy'):
                    add_log(f"Loaded strategy class: {attr_name}", "StrategyManager")
                    return attr
            
            add_log(f"No strategy class found in {filename}", "StrategyManager", "WARNING")
            return None
            
        except Exception as e:
            add_log(f"Error loading strategy {filename}: {e}", "StrategyManager", "ERROR")
            return None
    
    def start_strategy(self, strategy_name: str) -> bool:
        """
        Start a specific strategy by name
        """
        if strategy_name in self.active_strategies:
            add_log(f"Strategy {strategy_name} is already running", "StrategyManager", "WARNING")
            return False
        
        # Find the strategy file
        filename = f"{strategy_name.lower()}_strategy.py"
        strategy_class = self.load_strategy_class(filename)
        
        if not strategy_class:
            add_log(f"Could not load strategy class for {strategy_name}", "StrategyManager", "ERROR")
            return False
        
        try:
            # Create strategy instance with unique client ID
            client_id = self.next_client_id
            self.next_client_id += 1
            
            strategy_instance = strategy_class(client_id=client_id, strategy_manager=self)
            
            # Start the strategy
            strategy_instance.start_strategy()
            
            # Track the running strategy
            self.active_strategies[strategy_name] = strategy_instance
            
            add_log(f"Started strategy {strategy_name} with clientId={client_id}", "StrategyManager")
            return True
            
        except Exception as e:
            add_log(f"Error starting strategy {strategy_name}: {e}", "StrategyManager", "ERROR")
            return False
    
    def stop_strategy(self, strategy_name: str) -> bool:
        """
        Stop a specific strategy by name
        """
        if strategy_name not in self.active_strategies:
            add_log(f"Strategy {strategy_name} is not running", "StrategyManager", "WARNING")
            return False
        
        try:
            strategy_instance = self.active_strategies[strategy_name]
            strategy_instance.stop_strategy()
            
            # Remove from active strategies
            del self.active_strategies[strategy_name]
            
            add_log(f"Stopped strategy {strategy_name}", "StrategyManager")
            return True
            
        except Exception as e:
            add_log(f"Error stopping strategy {strategy_name}: {e}", "StrategyManager", "ERROR")
            return False
    
    def start_all_strategies(self) -> Dict[str, bool]:
        """
        Start all discovered strategies
        Returns dict of strategy_name: success_status
        """
        strategy_files = self.discover_strategies()
        results = {}
        
        for filename in strategy_files:
            strategy_name = filename.replace("_strategy.py", "").upper()
            results[strategy_name] = self.start_strategy(strategy_name)
        
        return results
    
    def stop_all_strategies(self):
        """Stop all running strategies"""
        strategy_names = list(self.active_strategies.keys())
        for strategy_name in strategy_names:
            self.stop_strategy(strategy_name)
    
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
