"""
Portfolio Manager for IB Multi-Strategy ATS
Handles per-strategy position tracking, fills, and portfolio consolidation with ArcticDB
"""
import asyncio
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from ib_async import *

from .arctic_manager import get_ac
from .log_manager import add_log
from utils.fx_cache import FXCache
from utils.position_helpers import create_position_dict


class PortfolioManager:
    """
    Manages portfolio positions, fills, and P&L across multiple strategies.
    
    Key features:
    - Per-strategy position attribution
    - ArcticDB-backed persistence
    - Real-time position updates from fills
    - Portfolio consolidation with attribution
    - P&L calculation (realized/unrealized)
    """
    
    def __init__(self, strategy_manager=None):
        """
        Initialize PortfolioManager with IB client and ArcticDB integration.
        
        Args:
            ib_client: IB client for portfolio data access
            arctic_client: Optional ArcticDB client, will be created lazily if not provided
        """
        self.strategy_manager = strategy_manager
        self.ac = self.strategy_manager.ac

        # Set default base currency - will be updated when IB data is available
        self.fx_cache = None
        
        self._position_cache = {}  # Cache for frequently accessed positions
        self._batch_writes = []  # Buffer for batch ArcticDB writes
        self._batch_size = 10  # Number of operations to batch before writing
        
        print("PortfolioManager initialized")

    def get_arctic_client(self):
        """Get ArcticDB client lazily"""
        if self.ac is None:
            self.ac = get_ac()
        return self.ac
    
    async def _get_positions_from_ib(self) -> pd.DataFrame:
        """
        Get all portfolio positions from IB in DataFrame format without strategy assignment.
        """
        # Get IB client dynamically from strategy manager
        ib_client = self.strategy_manager.ib_client if self.strategy_manager else None
        
        if not ib_client:
            print("No IB client available for portfolio data")
            return pd.DataFrame()
        
        try:
            # Get total equity using async IB calls
            account_summary = await ib_client.accountSummaryAsync()
            self.total_equity = sum(
                float(entry.value) for entry in account_summary 
                if entry.tag == "EquityWithLoanValue"
            )
            self.base_currency = [entry.currency for entry in account_summary if entry.tag == "EquityWithLoanValue"][0]
            
            if self.total_equity == 0:
                print("Total equity is zero, cannot calculate % of NAV")
                return pd.DataFrame()
            
            # Get portfolio positions using async IB calls
            portfolio_data = []
            portfolio_items = ib_client.portfolio()
            #portfolio_items = await ib_client.portfolioAsync()
            for item in portfolio_items:
                position = create_position_dict(self, item)
                portfolio_data.append(position)
            
            if not portfolio_data:
                print("No portfolio positions found")
                return pd.DataFrame()
            
            # Create DataFrame
            df = pd.DataFrame(portfolio_data)
            df.set_index('timestamp', inplace=True)
            
            # Initialize FX cache if needed
            print(f" Base Currency is {self.base_currency}")
            if not self.fx_cache:
                self.fx_cache = FXCache(ib_client, self.base_currency)
            
            # Convert market values to base currency
            if self.fx_cache:
                df = await self.fx_cache.convert_marketValue_to_base_async(df, self.base_currency)
                # Recalculate % of NAV with base currency values
                df['% of nav'] = df['marketValue_base'] / self.total_equity * 100
            else:
                # No FX conversion, assume all in base currency
                df['marketValue_base'] = df['marketValue']
                df['% of nav'] = df['marketValue'] / self.total_equity * 100
            
            # Use marketValue_base for display (always in base currency)
            df['marketValue'] = df['marketValue_base']
            
            return df
            
        except Exception as e:
            print(f"Error getting positions from IB: {e}")
            return pd.DataFrame()
        
    async def get_ib_positions_for_frontend(self):
        """
        Get IB positions formatted for frontend display.
        Based on the original get_ib_positions_for_gui implementation.
        
        Returns:
            pd.DataFrame: Formatted positions sorted by symbol and % of NAV
        """
        try:
            # Get positions directly from IB
            df = await self._get_positions_from_ib()
            
            if df.empty:
                add_log("No positions to display for frontend", "PORTFOLIO")
                return df
            
            # Convert '% of nav' to numeric for sorting
            df['% of nav'] = pd.to_numeric(df['% of nav'], errors='coerce')
            
            # Sort by side (Long first, then Short) and then by symbol
            df_sorted = df.sort_values(by=['side', 'symbol'], ascending=[False, True])

            # Select columns for frontend (excluding 'side' from final output)
            columns_for_frontend = [
                'symbol', 'asset class', 'position', '% of nav',
                'marketPrice', 'averageCost', 'marketValue', 'pnl %', 'strategy'
            ]

            # Return only actual position rows (no group header rows)
            df_final = df_sorted[columns_for_frontend].reset_index(drop=True)

            # Ensure numeric types and no NaNs for frontend formatting
            numeric_cols = ['position', '% of nav', 'marketPrice', 'averageCost', 'marketValue', 'pnl %']
            for col in numeric_cols:
                if col in df_final.columns:
                    df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0.0)

            # Ensure strategy has a default string
            if 'strategy' in df_final.columns:
                df_final['strategy'] = df_final['strategy'].fillna('Unassigned').replace('', 'Unassigned')
            
            return df_final
            
        except Exception as e:
            print(f"Error formatting positions for frontend: {e}")
            return pd.DataFrame()
    
    # =============================================================================
    # Fill Processing
    # =============================================================================
    
    async def process_fill(self, strategy: str, trade: Trade, fill: Fill):
        """
        Process a fill event and update positions.
        
        Args:
            strategy: Strategy name that generated the fill
            trade: ib_async Trade object
            fill: ib_async Fill object
        """
        try:
            # Extract fill details
            fill_data = self._extract_fill_data(strategy, trade, fill)
            
            # Record the fill in ArcticDB
            await self._record_fill(fill_data)
            
            # Update position for this strategy/symbol
            await self._update_position_from_fill(strategy, fill_data)
            
            # Update consolidated portfolio view
            await self._update_consolidated_portfolio(fill_data['symbol'])
            
            add_log(f"Processed fill: {fill_data['side']} {fill_data['quantity']} {fill_data['symbol']} @ {fill_data['price']}", 
                   f"PORTFOLIO-{strategy}")
            
        except Exception as e:
            add_log(f"Error processing fill event: {e}", "PORTFOLIO", "ERROR")
    
    def _extract_fill_data(self, strategy: str, trade: Trade, fill: Fill) -> Dict[str, Any]:
        """Extract standardized fill data from ib_async objects"""
        execution = fill.execution
        contract = trade.contract
        
        return {
            'strategy': strategy,
            'symbol': contract.symbol,
            'asset_class': contract.secType,
            'exchange': contract.exchange,
            'currency': contract.currency,
            'fill_id': execution.execId,
            'order_ref': trade.order.orderRef or f"auto_{trade.order.orderId}",
            'side': execution.side,  # 'BOT' or 'SLD'
            'quantity': float(execution.shares),
            'price': float(execution.price),
            'commission': float(fill.commissionReport.commission) if fill.commissionReport else 0.0,
            'timestamp': datetime.now(timezone.utc),
            'order_id': trade.order.orderId,
            'perm_id': trade.order.permId
        }
    
    async def _record_fill(self, fill_data: Dict[str, Any]):
        """Record fill in ArcticDB fills/<STRATEGY> library"""
        try:
            ac = self.get_arctic_client()
            library_name = f"fills/{fill_data['strategy']}"
            
            # Ensure library exists
            if library_name not in ac.list_libraries():
                ac.get_library(library_name, create_if_missing=True)
            
            lib = ac.get_library(library_name)
            
            # Create DataFrame for the fill
            fill_df = pd.DataFrame([fill_data])
            fill_df['timestamp'] = pd.to_datetime(fill_df['timestamp'])
            
            # Use fill_id as symbol for unique identification
            symbol = f"{fill_data['symbol']}_{fill_data['fill_id']}"
            
            # Write to ArcticDB
            lib.write(symbol, fill_df)
            
        except Exception as e:
            add_log(f"Error recording fill to ArcticDB: {e}", "PORTFOLIO", "ERROR")
    
    async def _update_position_from_fill(self, strategy: str, fill_data: Dict[str, Any]):
        """Update position data based on fill"""
        try:
            symbol = fill_data['symbol']
            quantity = fill_data['quantity']
            price = fill_data['price']
            side = fill_data['side']
            commission = fill_data['commission']
            
            # Get current position
            current_position = await self._get_position(strategy, symbol)
            
            # Calculate position changes
            if side == 'BOT':  # Buy
                new_quantity = current_position['quantity'] + quantity
                if current_position['quantity'] >= 0:  # Adding to long or starting long
                    # Update average cost
                    total_cost = (current_position['quantity'] * current_position['avg_cost']) + (quantity * price)
                    new_avg_cost = total_cost / new_quantity if new_quantity != 0 else 0
                else:  # Covering short
                    if new_quantity >= 0:  # Fully covered, now long
                        new_avg_cost = price
                    else:  # Partially covered, still short
                        new_avg_cost = current_position['avg_cost']
            else:  # Sell
                new_quantity = current_position['quantity'] - quantity
                if current_position['quantity'] <= 0:  # Adding to short or starting short
                    # Update average cost for short position
                    total_cost = abs(current_position['quantity'] * current_position['avg_cost']) + (quantity * price)
                    new_avg_cost = total_cost / abs(new_quantity) if new_quantity != 0 else 0
                else:  # Selling long
                    if new_quantity <= 0:  # Fully sold, now short
                        new_avg_cost = price
                    else:  # Partially sold, still long
                        new_avg_cost = current_position['avg_cost']
            
            # Calculate realized P&L for this fill
            realized_pnl = 0.0
            if side == 'SLD' and current_position['quantity'] > 0:  # Selling long position
                realized_pnl = quantity * (price - current_position['avg_cost']) - commission
            elif side == 'BOT' and current_position['quantity'] < 0:  # Covering short position
                realized_pnl = quantity * (current_position['avg_cost'] - price) - commission
            
            # Update position data
            updated_position = {
                'strategy': strategy,
                'symbol': symbol,
                'asset_class': fill_data['asset_class'],
                'exchange': fill_data['exchange'],
                'currency': fill_data['currency'],
                'quantity': new_quantity,
                'avg_cost': new_avg_cost,
                'realized_pnl': current_position['realized_pnl'] + realized_pnl,
                'last_updated': datetime.now(timezone.utc)
            }
            
            # Save updated position
            await self._save_position(strategy, symbol, updated_position)
            
            # Update cache
            cache_key = f"{strategy}_{symbol}"
            self._position_cache[cache_key] = updated_position
            
        except Exception as e:
            add_log(f"Error updating position from fill: {e}", "PORTFOLIO", "ERROR")
    
    # =============================================================================
    # Order Status Tracking
    # =============================================================================
    
    async def record_status_change(self, strategy: str, trade: Trade, status: str):
        """
        Record order status change and update order tracking.
        
        Args:
            strategy: Strategy name
            trade: ib_async Trade object
            status: New order status
        """
        try:
            # Extract order data
            order_data = self._extract_order_data(strategy, trade, status)
            
            # Record status change in ArcticDB
            await self._record_order_status(order_data)
            
            add_log(f"Recorded status change: {status} for {order_data['symbol']}", 
                   f"PORTFOLIO-{strategy}")
            
        except Exception as e:
            add_log(f"Error processing status change: {e}", "PORTFOLIO", "ERROR")
    
    def _extract_order_data(self, strategy: str, trade: Trade, status: str) -> Dict[str, Any]:
        """Extract standardized order data from ib_async objects"""
        order = trade.order
        contract = trade.contract
        order_status = trade.orderStatus
        
        return {
            'strategy': strategy,
            'symbol': contract.symbol,
            'asset_class': contract.secType,
            'exchange': contract.exchange,
            'currency': contract.currency,
            'order_id': order.orderId,
            'perm_id': order.permId,
            'order_ref': order.orderRef or f"auto_{order.orderId}",
            'order_type': order.orderType,
            'side': order.action,  # 'BUY' or 'SELL'
            'total_quantity': float(order.totalQuantity),
            'filled_quantity': float(order_status.filled),
            'remaining_quantity': float(order_status.remaining),
            'avg_fill_price': float(order_status.avgFillPrice) if order_status.avgFillPrice else 0.0,
            'status': status,
            'timestamp': datetime.now(timezone.utc)
        }
    
    async def _record_order_status(self, order_data: Dict[str, Any]):
        """Record order status in ArcticDB orders/<STRATEGY> library"""
        try:
            ac = self.get_arctic_client()
            library_name = f"orders/{order_data['strategy']}"
            
            # Ensure library exists
            if library_name not in ac.list_libraries():
                ac.get_library(library_name, create_if_missing=True)
            
            lib = ac.get_library(library_name)
            
            # Create DataFrame for the order status
            order_df = pd.DataFrame([order_data])
            order_df['timestamp'] = pd.to_datetime(order_df['timestamp'])
            
            # Use order_ref as symbol for tracking
            symbol = f"{order_data['symbol']}_{order_data['order_ref']}"
            
            # Write to ArcticDB (this will update existing or create new)
            lib.write(symbol, order_df)
            
        except Exception as e:
            add_log(f"Error recording order status to ArcticDB: {e}", "PORTFOLIO", "ERROR")
    
    # =============================================================================
    # Position Management
    # =============================================================================
    
    async def _get_position(self, strategy: str, symbol: str) -> Dict[str, Any]:
        """Get current position for strategy/symbol combination"""
        cache_key = f"{strategy}_{symbol}"
        
        # Check cache first
        if cache_key in self._position_cache:
            return self._position_cache[cache_key]
        
        # Load from ArcticDB
        try:
            ac = self.get_arctic_client()
            library_name = f"positions/{strategy}"
            
            if library_name in ac.list_libraries():
                lib = ac.get_library(library_name)
                try:
                    position_df = lib.read(symbol).data
                    if not position_df.empty:
                        position = position_df.iloc[-1].to_dict()  # Get latest record
                        self._position_cache[cache_key] = position
                        return position
                except:
                    pass  # Position doesn't exist yet
        except Exception as e:
            add_log(f"Error loading position from ArcticDB: {e}", "PORTFOLIO", "ERROR")
        
        # Return empty position if not found
        empty_position = {
            'strategy': strategy,
            'symbol': symbol,
            'asset_class': '',
            'exchange': '',
            'currency': '',
            'quantity': 0.0,
            'avg_cost': 0.0,
            'realized_pnl': 0.0,
            'last_updated': datetime.now(timezone.utc)
        }
        
        self._position_cache[cache_key] = empty_position
        return empty_position
    
    async def _save_position(self, strategy: str, symbol: str, position_data: Dict[str, Any]):
        """Save position data to ArcticDB"""
        try:
            ac = self.get_arctic_client()
            library_name = f"positions/{strategy}"
            
            # Ensure library exists
            if library_name not in ac.list_libraries():
                ac.get_library(library_name, create_if_missing=True)
            
            lib = ac.get_library(library_name)
            
            # Create DataFrame for the position
            position_df = pd.DataFrame([position_data])
            position_df['last_updated'] = pd.to_datetime(position_df['last_updated'])
            
            # Write to ArcticDB
            lib.write(symbol, position_df)
            
        except Exception as e:
            add_log(f"Error saving position to ArcticDB: {e}", "PORTFOLIO", "ERROR")
    
    async def get_strategy_positions(self, strategy: str) -> List[Dict[str, Any]]:
        """Get all positions for a specific strategy"""
        try:
            ac = self.get_arctic_client()
            library_name = f"positions/{strategy}"
            
            if library_name not in ac.list_libraries():
                return []
            
            lib = ac.get_library(library_name)
            symbols = lib.list_symbols()
            
            positions = []
            for symbol in symbols:
                try:
                    position_df = lib.read(symbol).data
                    if not position_df.empty:
                        position = position_df.iloc[-1].to_dict()
                        # Calculate unrealized P&L (would need current market price)
                        position['unrealized_pnl'] = 0.0  # Placeholder
                        positions.append(position)
                except Exception as e:
                    add_log(f"Error reading position {symbol}: {e}", "PORTFOLIO", "ERROR")
            
            return positions
            
        except Exception as e:
            add_log(f"Error getting strategy positions: {e}", "PORTFOLIO", "ERROR")
            return []
    
    async def get_consolidated_positions(self) -> List[Dict[str, Any]]:
        """Get consolidated positions across all strategies"""
        try:
            ac = self.get_arctic_client()
            all_libraries = ac.list_libraries()
            position_libraries = [lib for lib in all_libraries if lib.startswith('positions/')]
            
            consolidated = {}
            
            for lib_name in position_libraries:
                strategy = lib_name.split('/')[-1]
                positions = await self.get_strategy_positions(strategy)
                
                for position in positions:
                    symbol = position['symbol']
                    if symbol not in consolidated:
                        consolidated[symbol] = {
                            'symbol': symbol,
                            'asset_class': position['asset_class'],
                            'exchange': position['exchange'],
                            'currency': position['currency'],
                            'total_quantity': 0.0,
                            'strategies': {},
                            'total_realized_pnl': 0.0,
                            'total_unrealized_pnl': 0.0
                        }
                    
                    consolidated[symbol]['total_quantity'] += position['quantity']
                    consolidated[symbol]['total_realized_pnl'] += position['realized_pnl']
                    consolidated[symbol]['total_unrealized_pnl'] += position.get('unrealized_pnl', 0.0)
                    consolidated[symbol]['strategies'][strategy] = {
                        'quantity': position['quantity'],
                        'avg_cost': position['avg_cost'],
                        'realized_pnl': position['realized_pnl'],
                        'unrealized_pnl': position.get('unrealized_pnl', 0.0)
                    }
            
            return list(consolidated.values())
            
        except Exception as e:
            add_log(f"Error getting consolidated positions: {e}", "PORTFOLIO", "ERROR")
            return []
    
    async def _update_consolidated_portfolio(self, symbol: str):
        """Update consolidated portfolio view for a specific symbol"""
        try:
            # This would update the portfolio/aggregated library
            # For now, we'll implement this as a placeholder
            # The actual implementation would aggregate positions across strategies
            pass
            
        except Exception as e:
            add_log(f"Error updating consolidated portfolio: {e}", "PORTFOLIO", "ERROR")
    
    # =============================================================================
    # Portfolio Analytics
    # =============================================================================
    
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get overall portfolio summary"""
        try:
            consolidated_positions = await self.get_consolidated_positions()
            
            total_realized_pnl = sum(pos['total_realized_pnl'] for pos in consolidated_positions)
            total_unrealized_pnl = sum(pos['total_unrealized_pnl'] for pos in consolidated_positions)
            
            return {
                'total_positions': len(consolidated_positions),
                'total_realized_pnl': total_realized_pnl,
                'total_unrealized_pnl': total_unrealized_pnl,
                'total_pnl': total_realized_pnl + total_unrealized_pnl,
                'positions': consolidated_positions,
                'last_updated': datetime.now(timezone.utc)
            }
            
        except Exception as e:
            add_log(f"Error getting portfolio summary: {e}", "PORTFOLIO", "ERROR")
            return {
                'total_positions': 0,
                'total_realized_pnl': 0.0,
                'total_unrealized_pnl': 0.0,
                'total_pnl': 0.0,
                'positions': [],
                'last_updated': datetime.now(timezone.utc)
            }
    
    async def get_strategy_summary(self, strategy: str) -> Dict[str, Any]:
        """Get summary for a specific strategy"""
        try:
            positions = await self.get_strategy_positions(strategy)
            
            total_realized_pnl = sum(pos['realized_pnl'] for pos in positions)
            total_unrealized_pnl = sum(pos.get('unrealized_pnl', 0.0) for pos in positions)
            
            return {
                'strategy': strategy,
                'total_positions': len(positions),
                'total_realized_pnl': total_realized_pnl,
                'total_unrealized_pnl': total_unrealized_pnl,
                'total_pnl': total_realized_pnl + total_unrealized_pnl,
                'positions': positions,
                'last_updated': datetime.now(timezone.utc)
            }
            
        except Exception as e:
            add_log(f"Error getting strategy summary: {e}", "PORTFOLIO", "ERROR")
            return {
                'strategy': strategy,
                'total_positions': 0,
                'total_realized_pnl': 0.0,
                'total_unrealized_pnl': 0.0,
                'total_pnl': 0.0,
                'positions': [],
                'last_updated': datetime.now(timezone.utc)
            }
    
    # =============================================================================
    # Utility Methods
    # =============================================================================
    
    def clear_cache(self):
        """Clear position cache"""
        self._position_cache.clear()
        print("Position cache cleared", "PORTFOLIO")
    
    async def reconcile_positions(self, ib_client=None):
        """
        Reconcile ArcticDB positions with IB positions (placeholder).
        This would implement the legacy match_ib_positions_with_arcticdb logic.
        """
        # Placeholder for future implementation
        add_log("Position reconciliation not yet implemented", "PORTFOLIO", "WARNING")
        pass
