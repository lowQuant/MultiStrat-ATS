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
from utils.persistence_utils import normalize_timestamp_index
try:
    # Available in ArcticDB >= 5.x
    from arcticdb import defragment_symbol_data  # type: ignore
except Exception:
    def defragment_symbol_data(*args, **kwargs):  # fallback no-op
        return


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
        self.ac = self.strategy_manager.ac if self.strategy_manager else get_ac()
        self.ib = self.strategy_manager.ib_client if self.strategy_manager else None
        self.account_id: Optional[str] = None
        self.account_library = None
        if self.ib:
            try:
                accounts = self.ib.managedAccounts()
                print(f"from init of portfolio manager: {accounts}")
                if accounts:
                    self.account_id = accounts[0]
                    self.account_library = self.ac.get_library(
                        self.account_id,
                        create_if_missing=True
                    )
                    self._defragment_account_portfolio()
            except Exception as exc:
                add_log(f"Failed to initialize account library: {exc}", "PORTFOLIO", "WARNING")


        # Set default base currency - will be updated when IB data is available
        self.base_currency = "USD"
        self.fx_cache = None
        
        self._position_cache = {}  # Cache for frequently accessed positions
        self._batch_writes = []  # Buffer for batch ArcticDB writes
        self._batch_size = 10  # Number of operations to batch before writing
        
        print("PortfolioManager initialized")

    def _defragment_account_portfolio(self) -> None:
        """
        Defragment the account-level 'portfolio' symbol stored in the
        account_id library, if present. Safe no-op on errors.
        """
        try:
            if not self.account_library:
                return
            # The symbol name is 'portfolio' as per architecture.md
            symbol = "portfolio"
            if symbol in self.account_library.list_symbols():
                defragment_symbol_data(self.account_library, symbol)
                add_log(f"Defragmented '{symbol}' in account library '{self.account_id}'", "PORTFOLIO")
        except Exception as e:
            # Never block initialization due to maintenance
            add_log(f"Defragmentation skipped for account '{self.account_id}': {e}", "PORTFOLIO", "WARNING")

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
            # Reconcile and (if stale) persist a snapshot, then use that snapshot for UI
            df_ib = await self.reconcile_positions(ttl_minutes=60, write_if_stale=True)
            
            if df_ib is None or df_ib.empty:
                add_log("No positions to display. Make sure IB is connected and positions are loaded.", "PORTFOLIO")
                return pd.DataFrame()
            
            # Display marketValue in base currency
            if 'marketValue_base' in df_ib.columns:
                df_ib['marketValue'] = df_ib['marketValue_base']

            # Add side for sorting based on position sign
            if 'position' in df_ib.columns:
                df_ib['side'] = df_ib['position'].apply(lambda q: 'Long' if float(q) > 0 else 'Short')

            # Convert '% of nav' to numeric for sorting
            df_ib['% of nav'] = pd.to_numeric(df_ib['% of nav'], errors='coerce')

            # Sort by side (Long first, then Short) and then by symbol
            df_sorted = df_ib.sort_values(by=['side', 'symbol'], ascending=[False, True])

            # Select columns for frontend (excluding 'side' from final output)
            columns_for_frontend = [
                'symbol', 'asset_class', 'position', '% of nav',
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
                   f"{strategy}")
            
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
            # library_name = f"fills/{fill_data['strategy']}"
            
            # # Ensure library exists
            # if library_name not in ac.list_libraries():
            #     ac.get_library(library_name, create_if_missing=True)
            
            lib = ac.get_library(self.account_id)
            
            # Create DataFrame for the fill
            fill_df = pd.DataFrame([fill_data])
            fill_df['timestamp'] = pd.to_datetime(fill_df['timestamp'])
            
            # Use fill_id as symbol for unique identification
            # symbol = f"{fill_data['symbol']}_{fill_data['fill_id']}"
            
            # Write to ArcticDB
            lib.append("fills", fill_df,prune_previous_versions=True)
            
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
    
    async def reconcile_positions(self, ib_client=None, ttl_minutes: int = 60, write_if_stale: bool = True, force_write: bool = False) -> pd.DataFrame:
        """
        Reconcile ArcticDB positions with IB positions.
        Adapted from legacy match_ib_positions_with_arcticdb() to the new architecture:
        - account_id is the ArcticDB library
        - snapshots are appended to the 'portfolio' symbol (time-indexed)
        """
        try:
            # Ensure account library is available

            if self.account_library is None:
                if self.ac is None:
                    self.ac = get_ac()
                if self.ib and not self.account_id:
                    accounts = self.ib.managedAccounts()
                    self.account_id = accounts[0] if accounts else None
                if not self.account_id:
                    add_log("No account_id available for reconciliation", "PORTFOLIO", "ERROR")
                    return pd.DataFrame()
                self.account_library = self.ac.get_library(self.account_id, create_if_missing=True)

            # TTL gate: decide write vs. no-write, but always compute a fresh reconciliation to return
            last_snapshot = self._load_last_portfolio_snapshot()
            if last_snapshot is not None and not last_snapshot.empty:
                try:
                    last_ts = pd.to_datetime(last_snapshot.index.max(), utc=True)
                    age_min = (pd.Timestamp.utcnow() - last_ts).total_seconds() / 60.0
                except Exception:
                    age_min = float('inf')
            else:
                age_min = float('inf')

            is_stale = age_min >= float(ttl_minutes)

            # 1) Fetch current IB positions (no strategy attribution)
            df_ib = await self._get_positions_from_ib()
            if df_ib is None or df_ib.empty:
                add_log("No IB positions found for reconciliation", "PORTFOLIO", "WARNING")
                return last_snapshot.copy() if last_snapshot is not None and not last_snapshot.empty else pd.DataFrame()

            # Standardize to IB-style schema (also handles legacy snake_case if present)
            df_ib_std = self._standardize_portfolio_columns(df_ib)

            # 2) Load last saved Arctic snapshot (if any)
            df_ac_last = self._load_last_portfolio_snapshot()
            df_ac_std = self._standardize_portfolio_columns(df_ac_last) if df_ac_last is not None and not df_ac_last.empty else pd.DataFrame()

            # 3) Build merged snapshot
            df_merged = pd.DataFrame()
            for _, ib_row in df_ib_std.iterrows():
                symbol = ib_row['symbol']
                asset_class = ib_row['asset_class']
                currency = ib_row['currency']

                if not df_ac_std.empty:
                    # Match on symbol, asset_class and currency if present (IB-style)
                    cur_mask = (df_ac_std['symbol'] == symbol)
                    if 'asset_class' in df_ac_std.columns:
                        cur_mask = cur_mask & (df_ac_std['asset_class'] == asset_class)
                    if 'currency' in df_ac_std.columns:
                        cur_mask = cur_mask & (df_ac_std['currency'] == currency)
                    strat_entries = df_ac_std[cur_mask]
                else:
                    strat_entries = pd.DataFrame()

                if strat_entries.empty:
                    # No existing Arctic entries -> take IB row (no strategy attribution)
                    df_merged = pd.concat([df_merged, pd.DataFrame([ib_row])], ignore_index=True)
                else:
                    # Update strategy entries with current market data and recomputed metrics
                    updated = self._update_and_aggregate_data(strat_entries, ib_row)
                    df_merged = pd.concat([df_merged, updated], ignore_index=True)

                    # Residual handling if sums don't match
                    qty_diff = float(ib_row['position']) - float(updated['position'].sum())
                    if abs(qty_diff) > 1e-9:
                        residual = self._handle_residual(strat_entries, ib_row)
                        if residual is not None and not residual.empty:
                            df_merged = pd.concat([df_merged, residual], ignore_index=True)

            # 4) Arctic-only positions not present in IB (e.g., net-zero at broker, attribution retained)
            if df_ac_std is not None and not df_ac_std.empty:
                for _, ac_row in df_ac_std.iterrows():
                    mask = (
                        (df_merged['symbol'] == ac_row['symbol'])
                        & (df_merged['asset_class'] == ac_row['asset_class'])
                    )
                    if df_merged[mask].empty:
                        # Optionally refresh market data here; for now, keep as-is to preserve attribution
                        df_merged = pd.concat([df_merged, pd.DataFrame([ac_row])], ignore_index=True)

            if df_merged.empty:
                add_log("Reconciliation produced no rows", "PORTFOLIO", "WARNING")
                return pd.DataFrame()

            # 5) Stamp snapshot timestamp and (conditionally) persist to 'portfolio'
            snapshot_ts = datetime.now(timezone.utc)
            df_merged['timestamp'] = snapshot_ts
            df_to_save = df_merged[
                [
                    'timestamp', 'symbol', 'asset_class', 'strategy', 'position', 'averageCost',
                    'marketPrice', 'marketValue', 'marketValue_base', '% of nav', 'currency', 'fx_rate', 'pnl %'
                ]
            ].copy()
            df_to_save = normalize_timestamp_index(df_to_save, index_col='timestamp', tz='UTC', ensure_unique=True, add_ns_offsets_on_collision=True)
            should_write = force_write or (write_if_stale and is_stale)
            if should_write:
                if 'portfolio' in self.account_library.list_symbols():
                    self.account_library.append('portfolio', df_to_save, validate_index=True)
                else:
                    self.account_library.write('portfolio', df_to_save)

            # 6) Save account summary (equity)
            try:
                total_equity = getattr(self, 'total_equity', None)
                if total_equity is not None:
                    self._save_account_summary(float(total_equity))
            except Exception:
                pass

            # 7) Return the merged standardized snapshot
            return df_to_save.copy()

        except Exception as e:
            add_log(f"Error during reconciliation: {e}", "PORTFOLIO", "ERROR")
            return pd.DataFrame()

    def _load_last_portfolio_snapshot(self) -> pd.DataFrame:
        """Load the latest portfolio snapshot from the account library's 'portfolio' symbol."""
        try:
            if self.account_library is None or 'portfolio' not in self.account_library.list_symbols():
                return pd.DataFrame()
            # Try last 10 days first, else fallback to last N rows
            try:
                today = pd.Timestamp.utcnow().normalize()
                df = self.account_library.read('portfolio', date_range=(today - pd.Timedelta(days=10), None)).data
            except Exception:
                df = self.account_library.read('portfolio', row_range=(-5000, None)).data
            if df is None or df.empty:
                return pd.DataFrame()
            # Select the most recent snapshot timestamp
            last_ts = df.index.max()
            return df.loc[df.index == last_ts].copy()
        except Exception:
            return pd.DataFrame()

    def _standardize_portfolio_columns(self, df_in: pd.DataFrame) -> pd.DataFrame:
        """Standardize column names/shape to IB-style schema for 'portfolio'. Accepts legacy snake_case and IB-style."""
        if df_in is None or df_in.empty:
            return pd.DataFrame()
        df = df_in.copy()

        # Ensure essential columns exist (IB-style)
        for col, default in [
            ('strategy', ''),
            ('marketValue_base', df.get('marketValue_base', df.get('marketValue', pd.Series([0]*len(df))).astype(float) if 'marketValue' in df.columns else 0.0)),
            ('% of nav', 0.0),
            ('fx_rate', 1.0),
            ('pnl %', 0.0),
        ]:
            if col not in df.columns:
                df[col] = default
        # Keep only relevant columns
        cols = [
            'symbol', 'asset_class', 'strategy', 'position', 'averageCost', 'marketPrice',
            'marketValue', 'marketValue_base', '% of nav', 'currency', 'fx_rate', 'pnl %'
        ]
        out_cols = [c for c in cols if c in df.columns]
        return df[out_cols].copy()

    def _update_and_aggregate_data(self, df_ac: pd.DataFrame, ib_row: pd.Series) -> pd.DataFrame:
        """Update ArcticDB strategy entries with current market data and reconcile quantities/costs (IB-style columns)."""
        output = df_ac.copy()
        # Update market metrics to IB snapshot
        output['marketPrice'] = ib_row['marketPrice']
        output['marketValue'] = output['marketPrice'] * output['position']
        fx_rate = float(ib_row.get('fx_rate', 1.0))
        output['marketValue_base'] = output['marketValue'] / fx_rate if fx_rate else output['marketValue']

        total_equity = getattr(self, 'total_equity', None)
        if total_equity:
            output['% of nav'] = (output['marketValue_base'] / float(total_equity)) * 100.0
        else:
            output['% of nav'] = 0.0

        # Simple PnL % approximation (without contract context)
        with pd.option_context('mode.use_inf_as_na', True):
            output['pnl %'] = ((output['marketPrice'] - output['averageCost']) / output['averageCost']).replace([pd.NA], 0.0) * 100.0

        # If only one strategy entry exists and IB total differs, adjust that entry to match IB total
        qty_diff = float(ib_row['position']) - float(output['position'].sum())
        if abs(qty_diff) > 1e-9 and len(output) == 1:
            total_cost_ib = float(ib_row['averageCost']) * abs(float(ib_row['position']))
            total_cost_existing = float(output['averageCost'].iloc[0]) * abs(float(output['position'].iloc[0]))
            missing_amount = float(qty_diff)
            if missing_amount != 0:
                res_avg_cost = (total_cost_ib - total_cost_existing) / abs(missing_amount)
                # Weighted new avg cost
                new_qty = float(output['position'].iloc[0]) + missing_amount
                if abs(new_qty) > 1e-12:
                    new_avg_cost = (
                        (output['averageCost'].iloc[0] * abs(output['position'].iloc[0]) + res_avg_cost * abs(missing_amount))
                        / abs(new_qty)
                    )
                else:
                    new_avg_cost = ib_row['averageCost']
                output.loc[output.index[0], 'averageCost'] = float(new_avg_cost)
                output.loc[output.index[0], 'position'] = new_qty
                # Recompute market values
                output.loc[output.index[0], 'marketValue'] = float(output.loc[output.index[0], 'marketPrice']) * new_qty
                output.loc[output.index[0], 'marketValue_base'] = float(output.loc[output.index[0], 'marketValue']) / fx_rate if fx_rate else float(output.loc[output.index[0], 'marketValue'])
                if total_equity:
                    output.loc[output.index[0], '% of nav'] = (float(output.loc[output.index[0], 'marketValue_base']) / float(total_equity)) * 100.0

        return output.reset_index(drop=True)

    def _handle_residual(self, strategy_entries_in_ac: pd.DataFrame, ib_row: pd.Series) -> pd.DataFrame:
        """Create a residual row when IB position != sum of strategy entries (IB-style columns)."""
        total_position = float(ib_row['position'])
        assigned_sum = float(strategy_entries_in_ac['position'].sum()) if not strategy_entries_in_ac.empty else 0.0
        residual_position = total_position - assigned_sum
        if abs(residual_position) == 0:
            return pd.DataFrame()

        # Weighted average cost calc
        weighted_assigned = float((strategy_entries_in_ac['averageCost'] * strategy_entries_in_ac['position']).sum()) if not strategy_entries_in_ac.empty else 0.0
        total_weighted_ib = float(ib_row['averageCost']) * total_position
        try:
            residual_avg_cost = (total_weighted_ib - weighted_assigned) / residual_position
        except ZeroDivisionError:
            residual_avg_cost = float(ib_row['averageCost'])

        market_price = float(ib_row['marketPrice'])
        residual_market_value = residual_position * market_price
        fx_rate = float(ib_row.get('fx_rate', 1.0))
        total_equity = float(getattr(self, 'total_equity', 0.0) or 0.0)
        residual_row = {
            'symbol': ib_row['symbol'],
            'asset_class': ib_row['asset_class'],
            'strategy': '',
            'position': residual_position,
            'averageCost': residual_avg_cost,
            'marketPrice': market_price,
            'marketValue': residual_market_value,
            'marketValue_base': residual_market_value / fx_rate if fx_rate else residual_market_value,
            '% of nav': ((residual_market_value / fx_rate) / total_equity * 100.0) if (fx_rate and total_equity) else 0.0,
            'currency': ib_row.get('currency', 'USD'),
            'fx_rate': fx_rate,
            'pnl %': ((market_price - residual_avg_cost) / residual_avg_cost * 100.0) if residual_avg_cost else 0.0,
        }
        return pd.DataFrame([residual_row])

    def _save_account_summary(self, equity: float, cash: float = 0.0, market_value: float = None):
        """Append a row to 'account_summary' with current equity (and optional fields)."""
        try:
            if self.account_library is None:
                return
            ts = datetime.now(timezone.utc)
            data = {
                'timestamp': ts,
                'equity': float(equity),
                'pnl': 0.0,
                'cash': float(cash),
                'market_value': float(market_value) if market_value is not None else float(equity),
            }
            df = pd.DataFrame([data])
            df = normalize_timestamp_index(df, index_col='timestamp', tz='UTC', ensure_unique=True, add_ns_offsets_on_collision=True)
            if 'account_summary' in self.account_library.list_symbols():
                self.account_library.append('account_summary', df, validate_index=True)
            else:
                self.account_library.write('account_summary', df)
        except Exception:
            pass

    def update_ib_connection(self, ib_client):
        """Update IB connection after it's established and retrieve account information"""
        self.ib = ib_client
        if self.ib:
            try:
                accounts = self.ib.managedAccounts()
                print(f"from update_ib_connection of portfolio manager: {accounts}")
                if accounts:
                    self.account_id = accounts[0]
                    self.account_library = self.ac.get_library(self.account_id, create_if_missing=True)
                    self._defragment_account_portfolio()
            except Exception as exc:
                add_log(f"Failed to initialize account library: {exc}", "PORTFOLIO", "WARNING")
