"""
Abstract Base Class for Broker implementations.

The Broker abstraction provides a unified interface for both live trading and backtesting.
It handles equity management with ArcticDB integration and strategy-specific allocations.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import json
import pandas as pd
from ib_async import Contract, Order, Trade, Position

class Broker(ABC):
    """
    An abstract base class that defines the interface for broker implementations.
    This allows strategies to interact with a broker in the same way, whether in a
    live trading environment or a backtesting simulation.
    
    Equity Logic:
    1. First check for strategy-specific equity in ArcticDB strategy_equity library
    2. Fallback: Read target_weight from general/strategies and calculate from total portfolio equity
    """
    
    def __init__(self, strategy_symbol: str, arctic_client=None):
        """
        Initialize the broker with strategy symbol and optional ArcticDB client.
        
        Args:
            strategy_symbol: The symbol of the strategy using this broker
            arctic_client: Optional ArcticDB client for data access
        """
        self.strategy_symbol = strategy_symbol
        self.arctic_client = arctic_client

    async def get_equity(self) -> float:
        """
        Retrieves the equity allocated to this strategy.
        
        Implements a two-tier approach:
        1. Check for strategy-specific equity in ArcticDB strategy_{strategy_symbol} table
        2. Fallback to calculating from target_weight and total portfolio equity
        
        Returns:
            The equity allocated to this strategy as a float.
        """
        # First try to get strategy-specific equity from ArcticDB
        strategy_equity = await self._get_strategy_equity_from_arctic()
        if strategy_equity is not None and strategy_equity > 0:
            return strategy_equity
        
        # Fallback: calculate from target_weight and total equity
        return await self._calculate_equity_from_weight()
    
    async def _get_strategy_equity_from_arctic(self) -> Optional[float]:
        """
        Try to get strategy-specific equity from ArcticDB.
        This should be overridden in subclasses to read from account-specific library.
        
        Returns:
            Strategy equity if found, None otherwise
        """
        # This base implementation is for backward compatibility
        # Subclasses should override this to read from {account_id}/strategy_{symbol}
        return None
    
    async def _calculate_equity_from_weight(self) -> float:
        """
        Calculate strategy equity from target_weight in general/strategies table.
        
        Returns:
            Calculated equity based on weight and total portfolio equity
        """
        if not self.arctic_client:
            # If no Arctic client, use total equity (for backward compatibility)
            return await self._get_total_equity()
            
        try:
            # Get target weight from general/strategies
            lib = self.arctic_client.get_library('general')
            if lib.has_symbol('strategies'):
                strat_df = lib.read('strategies').data
                strat_row = strat_df[strat_df['strategy_symbol'] == self.strategy_symbol]
                if not strat_row.empty:
                    target_weight = None
                    # Prefer params JSON
                    if 'params' in strat_row.columns:
                        pval = strat_row.iloc[-1].get('params')
                        try:
                            pobj = json.loads(pval) if isinstance(pval, str) else (pval or {})
                        except Exception:
                            pobj = {}
                        if isinstance(pobj, dict) and 'target_weight' in pobj:
                            try:
                                target_weight = float(pobj.get('target_weight'))
                            except Exception:
                                target_weight = None
                    # Backward compat fallback to top-level column
                    if target_weight is None and 'target_weight' in strat_row.columns:
                        try:
                            target_weight = float(strat_row.iloc[-1]['target_weight'])
                        except Exception:
                            target_weight = None
                    if target_weight is not None:
                        total_equity = await self._get_total_equity()
                        return total_equity * target_weight
                    
        except Exception as e:
            print(f"Error calculating equity from weight: {e}")
            
        # Final fallback: return total equity
        return await self._get_total_equity()
    
    @abstractmethod
    async def _get_total_equity(self) -> float:
        """
        Get the total account equity (implementation-specific).
        
        Returns:
            Total account equity
        """
        pass

    @abstractmethod
    async def place_order(
        self, 
        contract: Contract, 
        order: Order, 
        size: float, 
        stop_price: Optional[float] = None
    ) -> Trade:
        """
        Places an order with the broker.

        Args:
            contract: The contract to trade.
            order: The order details.
            size: The percentage of allocated capital to use (e.g., 1.0 for 100%).
            stop_price: The optional stop price for stop-loss orders.

        Returns:
            The resulting trade object.
        """
        pass

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Retrieves a list of all current positions.

        Returns:
            A list of Position objects.
        """
        pass
