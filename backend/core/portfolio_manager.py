"""
Portfolio Manager for IB Multi-Strategy ATS
Handles per-strategy position tracking, fills, and portfolio consolidation with ArcticDB
"""
import asyncio
import arcticdb as adb
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from ib_async import *
from .log_manager import add_log
from utils.fx_cache import FXCache
from utils.position_helpers import create_position_dict, extract_fill_data, calculate_avg_cost, extract_order_data, create_portfolio_row_from_fill
from utils.persistence_utils import normalize_timestamp_index
from utils.strategy_table_helpers import start_hourly_snapshot_task, stop_hourly_snapshot_task, update_strategy_cash
from utils.strategy_table_helpers import get_strategy_positions as get_positions_helper, calculate_strategy_equity as calculate_equity_helper, get_strategy_equity_history as get_equity_history_helper
from .arctic_manager import get_ac, defragment_account_portfolio

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
        self.message_queue_ib = None  # Separate IB client for message queue thread operations
        self.account_id: Optional[str] = None
        self.account_library = None
        if self.ib:
            try:
                accounts = self.ib.managedAccounts()
                print(f"from init of portfolio manager: {accounts}")
                if accounts:
                    self.account_id = accounts[0]
                    self.account_library = self.ac.get_library(self.account_id,create_if_missing=True)
                    defragment_account_portfolio(self.account_library)
            except Exception as exc:
                add_log(f"Failed to initialize account library: {exc}", "PORTFOLIO", "WARNING")


        # Set default base currency - will be updated when IB data is available
        self.base_currency = "EUR"
        self.fx_cache = None
        
        self._position_cache = {}  # Cache for frequently accessed positions
        self._batch_writes = []  # Buffer for batch ArcticDB writes
        self._batch_size = 10  # Number of operations to batch before writing
        
        # Memory cache for positions endpoint (60 second TTL)
        self._positions_memory_cache = None
        self._positions_cache_timestamp = None
        self._positions_cache_ttl = 60  # seconds
        
        # Background task for hourly strategy positions snapshot
        self._hourly_snapshot_task = None
        
        print("PortfolioManager initialized")
    
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
            self.total_equity = sum(float(entry.value) for entry in account_summary if entry.tag == "EquityWithLoanValue")
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
        # TODO: move this function to routes/portfolio.py
        """
        Get IB positions formatted for frontend display.
        Uses cached reconciled positions (60s TTL via reconcile_positions).
        
        Returns:
            pd.DataFrame: Formatted positions sorted by symbol and % of NAV
        """
        try:
            # Get reconciled positions (uses cache internally)
            df_ib = await self.reconcile_positions()
            
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

            # Ensure 'exchange' column exists, default to 'SMART' if missing
            if 'exchange' not in df_sorted.columns:
                df_sorted['exchange'] = 'SMART'
            if 'contract' not in df_sorted.columns:
                df_sorted['contract'] = ''
            if 'conId' not in df_sorted.columns:
                df_sorted['conId'] = 0
            
            # Fill any NaN exchanges with 'SMART'
            df_sorted['exchange'] = df_sorted['exchange'].fillna('SMART')
            df_sorted['contract'] = df_sorted['contract'].fillna('')
            df_sorted['conId'] = df_sorted['conId'].fillna(0)

            # Select columns for frontend (excluding 'side' from final output)
            columns_for_frontend = [
                'symbol', 'asset_class', 'position', '% of nav',
                'marketPrice', 'averageCost', 'marketValue', 'pnl %', 'strategy',
                'currency', 'exchange', 'contract', 'conId'
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
                df_final['strategy'] = df_final['strategy'].fillna('Discretionary').replace('', 'Discretionary')
            
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
            fill_data = extract_fill_data(strategy, trade, fill)
            
            # Record the fill in ArcticDB
            await self._record_fill(fill_data)
            
            # Update position for this strategy/symbol
            await self._update_position_from_fill(strategy, fill_data)
            
            # Update consolidated portfolio view (use message queue IB client)
            await self._update_portfolio_on_fill(strategy, trade, fill, ib_client=self.message_queue_ib)
            print("fill processed")
        except Exception as e:
            add_log(f"Error processing fill event: {e}", "PORTFOLIO", "ERROR")
        
    async def _record_fill(self, fill_data: Dict[str, Any]):
        """Record fill in ArcticDB fills table"""
        try:
            # Create DataFrame for the fill
            fill_df = pd.DataFrame([fill_data])
            fill_df['timestamp'] = pd.to_datetime(fill_df['timestamp'])
            fill_df.set_index('timestamp', inplace=True)
            fill_df.index.name = 'timestamp'  # Match existing table index name
            
            # Write to ArcticDB
            try:
                self.account_library.append("fills", fill_df,prune_previous_versions=True)
            except:
                self.account_library.write("fills", fill_df,prune_previous_versions=True)
            
        except Exception as e:
            add_log(f"Error recording fill to ArcticDB: {e}", "PORTFOLIO", "ERROR")
    
    async def _update_position_from_fill(self, strategy: str, fill_data: Dict[str, Any]):
        """Update strategy_{strategy_symbol} data based on fill"""
        try:
            table_name = f"strategy_{strategy}"
            symbol = fill_data['symbol']
            quantity = fill_data['quantity']
            price = fill_data['price']
            side = fill_data['side']
            commission = fill_data['commission']

            print("print from _update_position_from_fill")
            print(" ")
            print(fill_data)
            
            # Get current position (returns None if new)
            current_position = await self._get_position(strategy, symbol)
            
            print("current_position")
            print(current_position)
            # If no existing position, create new position entry with proper schema
            if not current_position:
                position_row = {
                    'strategy': strategy,
                    'symbol': fill_data['symbol'],
                    'asset_class': fill_data['asset_class'],
                    'exchange': fill_data['exchange'],
                    'currency': fill_data['currency'],
                    'quantity': quantity if side == 'BOT' else -quantity,  # BOT = positive, SLD = negative
                    'avg_cost': price,  # First fill price = avg_cost
                    'realized_pnl': 0.0,  # No realized PnL on opening position
                    'timestamp': fill_data['timestamp']
                }
                
                new_position = pd.DataFrame([position_row])
                new_position['timestamp'] = pd.to_datetime(new_position['timestamp'])
                new_position.set_index('timestamp', inplace=True)
                
                # Write to ArcticDB
                try:
                    self.account_library.append(table_name, new_position, prune_previous_versions=True)
                except:
                    self.account_library.write(table_name, new_position, prune_previous_versions=True)
                return

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
                'timestamp': datetime.now(timezone.utc)
            }
            
            # Save updated position
            await self._save_position(strategy, updated_position)
            
            # Update CASH position after fill
            try:
                await update_strategy_cash(self,strategy,fill_data)
            except Exception as cash_error:
                add_log(f"Error updating CASH for strategy {strategy}: {cash_error}", "PORTFOLIO", "WARNING")
            
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
            order_data = extract_order_data(strategy, trade, status)
            
            # Record status change in ArcticDB
            await self._record_order_status(order_data)
            
            add_log(f"Recorded status change: {status} for {order_data['symbol']}", 
                   f"{strategy}")
            
        except Exception as e:
            add_log(f"Error processing status change: {e}", "PORTFOLIO", "ERROR")
    
    async def _record_order_status(self, order_data: Dict[str, Any]):
        """Record order status in ArcticDB orders library"""
        try:
            # Create DataFrame for the order status
            order_df = pd.DataFrame([order_data])
            order_df['timestamp'] = pd.to_datetime(order_df['timestamp'])
            order_df.set_index('timestamp', inplace=True)
            order_df.index.name = 'index'  # Match existing 'orders' table index name
            
            ac_orders_df = self.account_library.read("orders", row_range=(0,1)).data

            if ac_orders_df is None or ac_orders_df.empty:
                self.account_library.write("orders", order_df, prune_previous_versions=True)
            else:
                self.account_library.append("orders", order_df, prune_previous_versions=True)
            
        except Exception as e:
            add_log(f"Error recording order status to ArcticDB: {e}", "PORTFOLIO", "ERROR")
    
    # =============================================================================
    # Position Management
    # =============================================================================
    
    async def _get_position(self, strategy_symbol: str, symbol: str) -> Dict[str, Any]:
        """Get current position for strategy/symbol combination."""
        return await get_positions_helper(self, strategy_symbol, symbol=symbol, current_only=True)
    
    async def _save_position(self, strategy_symbol: str, position_data: Dict[str, Any]):
        """Save position data to strategy_{strategy_symbol} table"""
        try:
            table_name = f"strategy_{strategy_symbol}"
            
            # Create DataFrame for the position
            position_df = pd.DataFrame([position_data])
            position_df['timestamp'] = pd.to_datetime(position_df['timestamp'])
            position_df.set_index('timestamp', inplace=True)
            
            # Write to ArcticDB
            try:
                self.account_library.append(table_name, position_df, prune_previous_versions=True)
            except:
                self.account_library.write(table_name, position_df, prune_previous_versions=True)

        except Exception as e:
            add_log(f"Error saving position to ArcticDB: {e}", "PORTFOLIO", "ERROR")
    
    async def get_strategy_positions(self, strategy_symbol: str, symbol: Optional[str] = None, current_only: bool = True, days_lookback: Optional[int] = 7, exclude_equity: bool = True):
        """Get strategy positions. Wrapper for utils.strategy_table_helpers.get_strategy_positions"""
        return await get_positions_helper(self, strategy_symbol, symbol, current_only, days_lookback, exclude_equity)
        
    async def calculate_strategy_equity(self, strategy_symbol: str) -> float:
        """Calculate total equity for a strategy. Wrapper for utils.strategy_table_helpers.calculate_strategy_equity"""
        return await calculate_equity_helper(self, strategy_symbol)
    
    async def get_strategy_equity_history(self, strategy_symbol: str, days_lookback: Optional[int] = 30) -> pd.DataFrame:
        """Get historical equity snapshots. Wrapper for utils.strategy_table_helpers.get_strategy_equity_history"""
        return await get_equity_history_helper(self, strategy_symbol, days_lookback)

    async def _update_portfolio_on_fill(self, strategy: str, trade: Trade, fill: Fill, ib_client=None):
        """Incrementally update portfolio for THIS strategy's position only.
        Does NOT handle residuals or cross-strategy logic - that's for reconciliation.
        
        Args:
            strategy: Strategy name
            trade: Trade object
            fill: Fill object
            ib_client: Optional IB client to use (defaults to self.ib). Use self.message_queue_ib for message queue thread calls.
        """
        try:
            # Use provided ib_client or fall back to main client
            ib = ib_client if ib_client else self.ib
            if not ib:
                print("_update_portfolio_on_fill: No IB client available, skipping consolidated update")
                return
            
            self.account_library = self.ac.get_library(self.account_id, create_if_missing=True)
            # Load current portfolio
            if 'portfolio' in self.account_library.list_symbols():
                portfolio_df = self.account_library.read('portfolio').data
            else:
                portfolio_df = pd.DataFrame()

            new_row = await create_portfolio_row_from_fill(self, trade, fill, strategy, ib)
            
            # Key: Match on (symbol, asset_class, strategy)
            mask = ((portfolio_df['symbol'] == new_row['symbol']) &
                   (portfolio_df['asset_class'] == new_row['asset_class']) &
                   (portfolio_df['strategy'] == strategy))

            existing = portfolio_df[mask]
            
            if existing.empty: # New position
                # Add new row to in-memory DataFrame
                portfolio_df = pd.concat([portfolio_df, pd.DataFrame([new_row])], ignore_index=True)
            else: # Update existing position
                idx = existing.index[0]
                old_qty = float(portfolio_df.loc[idx, 'position'])
                old_avg = float(portfolio_df.loc[idx, 'averageCost'])

                # new_row['position'] is already signed (+ for BOT, - for SLD)
                fill_qty = float(new_row['position'])
                new_qty = old_qty + fill_qty

                if abs(new_qty) < 0.01:  # Position closed
                    # Remove this row
                    portfolio_df = portfolio_df.drop(idx).reset_index(drop=True)
                else:
                    # Update quantity and avg cost
                    new_avg = calculate_avg_cost(old_qty, old_avg, fill_qty, new_row['marketPrice'])
                    portfolio_df.loc[idx, 'position'] = new_qty
                    portfolio_df.loc[idx, 'averageCost'] = new_avg
                    portfolio_df.loc[idx, 'marketPrice'] = new_row['marketPrice']
                    portfolio_df.loc[idx, 'timestamp'] = datetime.now(timezone.utc)
                    # Recalculate market values...

            # Save
            portfolio_df['timestamp'] = datetime.now(timezone.utc)
            self.account_library.write('portfolio', portfolio_df, prune_previous_versions=True)

        except Exception as e:
            add_log(f"Error updating portfolio on fill: {e}", "PORTFOLIO", "ERROR")
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
                'timestamp': datetime.now(timezone.utc)
            }
            
        except Exception as e:
            add_log(f"Error getting portfolio summary: {e}", "PORTFOLIO", "ERROR")
            return {
                'total_positions': 0,
                'total_realized_pnl': 0.0,
                'total_unrealized_pnl': 0.0,
                'total_pnl': 0.0,
                'positions': [],
                'timestamp': datetime.now(timezone.utc)
            }
    
    async def get_strategy_summary(self, strategy: str) -> Dict[str, Any]:
        """Get summary for a specific strategy"""
        try:
            positions_df = await self.get_strategy_positions(strategy, current_only=True)
            
            if positions_df.empty:
                return {
                    'strategy': strategy,
                    'total_positions': 0,
                    'total_realized_pnl': 0.0,
                    'total_unrealized_pnl': 0.0,
                    'total_pnl': 0.0,
                }
            
            total_realized_pnl = positions_df['realized_pnl'].sum()
            total_unrealized_pnl = positions_df.get('unrealized_pnl', pd.Series([0.0])).sum()
            
            return {
                'strategy': strategy,
                'total_positions': len(positions_df),
                'total_realized_pnl': float(total_realized_pnl),
                'total_unrealized_pnl': float(total_unrealized_pnl),
                'total_pnl': float(total_realized_pnl + total_unrealized_pnl),
                'timestamp': datetime.now(timezone.utc)
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
                'timestamp': datetime.now(timezone.utc)
            }
    
    # =============================================================================
    # Utility Methods
    # =============================================================================
    
    def clear_cache(self):
        """
        Clear all portfolio caches:
        - Strategy/symbol position cache (_position_cache)
        - Reconciled positions memory cache (_positions_memory_cache)
        """
        self._position_cache.clear()
        self._positions_memory_cache = None
        self._positions_cache_timestamp = None
    
    async def reconcile_positions(self, ib_client=None, force_refresh: bool = False) -> pd.DataFrame:
        """
        Reconcile IB positions into a current-state portfolio table with memory cache (60s TTL).
        
        Args:
            ib_client: Optional IB client (unused, kept for compatibility)
            force_refresh: If True, bypass cache and force a fresh reconciliation
        """
        try:
            # Check memory cache first (unless force_refresh is True)
            if not force_refresh:
                now = datetime.now(timezone.utc)
                if (self._positions_memory_cache is not None and 
                    self._positions_cache_timestamp is not None):
                    cache_age = (now - self._positions_cache_timestamp).total_seconds()
                    if cache_age < self._positions_cache_ttl:
                        print(f"Returning cached reconciled positions (age: {cache_age:.1f}s)")
                        return self._positions_memory_cache.copy()
                
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

            # 1) Fetch current IB positions (no strategy attribution)
            df_ib = await self._get_positions_from_ib()
            if df_ib is None or df_ib.empty:
                add_log("No IB positions found for reconciliation", "PORTFOLIO", "WARNING")
                empty_df = pd.DataFrame(columns=[
                    'symbol', 'asset_class', 'strategy', 'position', 'averageCost',
                    'marketPrice', 'marketValue', 'marketValue_base', '% of nav',
                    'currency', 'fx_rate', 'pnl %', 'timestamp', 'exchange', 'contract', 'conId'
                ])
                empty_df.reset_index(drop=True, inplace=True)
                self.account_library.write('portfolio', empty_df, prune_previous_versions=True)
                return empty_df.copy()

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
                # Identify symbols in Arctic that were NOT in IB (df_ib_std)
                # Note: df_ib_std might be empty if IB has no positions
                ib_symbols = set(zip(df_ib_std['symbol'], df_ib_std['asset_class'])) if not df_ib_std.empty else set()
                
                # Group Arctic by symbol/asset_class to handle them collectively
                grouped_ac = df_ac_std.groupby(['symbol', 'asset_class'])
                
                for (sym, ac_type), group in grouped_ac:
                    if (sym, ac_type) not in ib_symbols:
                        # This symbol exists in Arctic but IB says quantity is 0 (closed or gone).
                        # We must reflect this by creating a residual so that Net Position = 0.
                        
                        # 1. Filter out existing 'Discretionary' rows from the group
                        # We only want to sum up the ACTUAL strategy allocations to see what's left over
                        # If we include old Discretionary rows, we double-count the residual
                        strategy_only_group = group[group['strategy'] != 'Discretionary']
                        
                        # 2. Calculate the total allocated to REAL strategies
                        total_allocated = strategy_only_group['position'].sum()
                        
                        # 3. IB quantity is effectively 0. Residual = IB - Allocated = 0 - Allocated.
                        residual_qty = 0.0 - total_allocated
                        
                        # 4. Add the strategy attribution rows back to the merged dataframe
                        if not strategy_only_group.empty:
                            df_merged = pd.concat([df_merged, strategy_only_group], ignore_index=True)
                        
                        # 5. If there is a discrepancy (allocated != 0), create a balancing Discretionary position
                        if abs(residual_qty) > 1e-9:
                            # Use market data from the Arctic row
                            last_row = group.iloc[-1]
                            
                            residual_row = {
                                'symbol': sym,
                                'asset_class': ac_type,
                                'strategy': 'Discretionary',  # Assign mismatch to Discretionary
                                'position': residual_qty,
                                'averageCost': 0.0,  # Cost of residual is technically N/A or 0
                                'marketPrice': last_row.get('marketPrice', 0.0),
                                'marketValue': last_row.get('marketPrice', 0.0) * residual_qty, # Approx
                                'marketValue_base': last_row.get('marketPrice', 0.0) * residual_qty, # Approx
                                '% of nav': 0.0,
                                'currency': last_row.get('currency', 'USD'),
                                'fx_rate': last_row.get('fx_rate', 1.0),
                                'pnl %': 0.0,
                                'timestamp': datetime.now(timezone.utc)
                            }
                            
                            print(f"[PORTFOLIO] Reconciling closed position {sym}: Strat={total_allocated}, IB=0 -> Adding Discretionary={residual_qty}")
                            df_merged = pd.concat([df_merged, pd.DataFrame([residual_row])], ignore_index=True)

            if df_merged.empty:
                add_log("Reconciliation produced no rows", "PORTFOLIO", "WARNING")
                return pd.DataFrame()

            # AGGREGATION STEP: Ensure no duplicate strategy rows (e.g. multiple Discretionary entries)
            # This merges +25 and -25 Discretionary rows into a single 0 row, which is then filtered out
            # if quantity is effectively zero.

            # Normalize strategy column to ensure 'Discretionary' matches '' or None before grouping
            if 'strategy' in df_merged.columns:
                df_merged['strategy'] = df_merged['strategy'].fillna('Discretionary').replace('', 'Discretionary')
            else:
                df_merged['strategy'] = 'Discretionary'
            
            # Columns to group by
            group_cols = ['symbol', 'asset_class', 'strategy', 'currency', 'exchange', 'contract', 'conId']
            
            # Aggregation logic
            agg_dict = {
                'position': 'sum',
                'marketValue': 'sum',
                'marketValue_base': 'sum',
                'averageCost': 'mean', # Weighted avg would be better but complex
                'marketPrice': 'last',
                '% of nav': 'sum',
                'pnl %': 'mean',
                'fx_rate': 'last',
                'timestamp': 'last'
            }
            # Handle columns that might be missing
            valid_agg = {k: v for k, v in agg_dict.items() if k in df_merged.columns}
            
            df_merged = df_merged.groupby(group_cols, as_index=False).agg(valid_agg)
            
            # Remove rows with zero quantity (after aggregation)
            df_merged = df_merged[df_merged['position'].abs() > 1e-9].reset_index(drop=True)

            # 5) Stamp snapshot timestamp and persist to 'portfolio'
            snapshot_ts = datetime.now(timezone.utc)
            df_merged['timestamp'] = snapshot_ts
            df_to_save = df_merged[
                [
                    'timestamp', 'symbol', 'asset_class', 'strategy', 'position', 'averageCost',
                    'marketPrice', 'marketValue', 'marketValue_base', '% of nav', 'currency', 'fx_rate', 'pnl %',
                    'exchange', 'contract', 'conId'
                ]
            ].copy()
            df_to_save = df_to_save.reset_index(drop=True)
            self.account_library.write('portfolio', df_to_save, prune_previous_versions=True)

            # 6) Save account summary (equity)
            try:
                total_equity = getattr(self, 'total_equity', None)
                if total_equity is not None:
                    self._save_account_summary(float(total_equity))
            except Exception:
                pass

            # 7) Update memory cache
            self._positions_memory_cache = df_to_save.copy()
            self._positions_cache_timestamp = datetime.now(timezone.utc)

            # 8) Return the merged standardized snapshot
            return df_to_save.copy()

        except Exception as e:
            add_log(f"Error during reconciliation: {e}", "PORTFOLIO", "ERROR")
            return pd.DataFrame()

    def _load_last_portfolio_snapshot(self) -> pd.DataFrame:
        """Load latest portfolio snapshot (numeric index)"""
        try:
            if self.account_library is None or 'portfolio' not in self.account_library.list_symbols():
                return pd.DataFrame()

            start_time = datetime.now()
            df = self.account_library.read('portfolio').data
            end_time = datetime.now()
            print(f"Loaded portfolio snapshot in {(end_time - start_time).total_seconds():.2f} seconds")

            if df is None or df.empty:
                return pd.DataFrame()
            return df.copy()
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
            'marketValue', 'marketValue_base', '% of nav', 'currency', 'fx_rate', 'pnl %',
            'exchange', 'contract', 'conId'
        ]
        out_cols = [c for c in cols if c in df.columns]
        return df[out_cols].copy()

    def _update_and_aggregate_data(self, df_ac: pd.DataFrame, ib_row: pd.Series) -> pd.DataFrame:
        """Update ArcticDB strategy entries with current market data and reconcile quantities/costs (IB-style columns)."""
        #TODO: Verify the logic of this function!!
        
        output = df_ac.copy()
        
        # Handle Multiplier for Futures - extract from contract string
        multiplier = 1.0
        if ib_row.get('asset_class') == 'FUT' and 'contract' in ib_row:
            contract_str = str(ib_row['contract'])
            # Parse "multiplier='0.1'" from contract string
            if "multiplier='" in contract_str:
                try:
                    start = contract_str.find("multiplier='") + len("multiplier='")
                    end = contract_str.find("'", start)
                    multiplier = float(contract_str[start:end])
                except:
                    multiplier = 1.0
        
        # Update market metrics to IB snapshot
        # For Futures, adjust marketPrice by multiplier for display purposes
        if ib_row.get('asset_class') == 'FUT':
            output['marketPrice'] = ib_row['marketPrice'] * multiplier
        else:
            output['marketPrice'] = ib_row['marketPrice']
        
        output['marketValue'] = output['marketPrice'] * output['position']
        
        # Update static fields if missing or changed (to keep them current)
        if 'exchange' in ib_row:
            output['exchange'] = ib_row['exchange']
        if 'contract' in ib_row:
            output['contract'] = ib_row['contract']
        if 'conId' in ib_row:
            output['conId'] = ib_row['conId']
            
        fx_rate = float(ib_row.get('fx_rate', 1.0))
        output['marketValue_base'] = output['marketValue'] / fx_rate if fx_rate else output['marketValue']

        total_equity = getattr(self, 'total_equity', None)
        if total_equity:
            output['% of nav'] = (output['marketValue_base'] / float(total_equity)) * 100.0
        else:
            output['% of nav'] = 0.0

        # Simple PnL % approximation
        # Long: (Price / Cost) - 1
        # Short: (Cost / Price) - 1
        avg_cost = output['averageCost'].replace(0, np.nan)
        market_price = output['marketPrice'].replace(0, np.nan)
        
        # Default Long calc
        pnl_raw = (market_price / avg_cost) - 1.0
        
        # Override for Shorts
        short_mask = output['position'] < 0
        if short_mask.any():
            pnl_raw.loc[short_mask] = (avg_cost.loc[short_mask] / market_price.loc[short_mask]) - 1.0
            
        pnl_pct = pnl_raw.replace([np.inf, -np.inf], np.nan).fillna(0.0) * 100.0
        output['pnl %'] = pnl_pct

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
                # Recompute market values (marketPrice already includes multiplier if FUT)
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

        # Handle Multiplier for Futures - extract from contract string
        multiplier = 1.0
        if ib_row.get('asset_class') == 'FUT' and 'contract' in ib_row:
            contract_str = str(ib_row['contract'])
            if "multiplier='" in contract_str:
                try:
                    start = contract_str.find("multiplier='") + len("multiplier='")
                    end = contract_str.find("'", start)
                    multiplier = float(contract_str[start:end])
                except:
                    multiplier = 1.0
        
        # Adjust market price for Futures
        market_price = float(ib_row['marketPrice']) * multiplier if ib_row.get('asset_class') == 'FUT' else float(ib_row['marketPrice'])
        
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
            'exchange': ib_row.get('exchange', 'SMART'),
            'contract': ib_row.get('contract', ''),
            'conId': ib_row.get('conId', 0),
            'fx_rate': fx_rate,
            'pnl %': ((((market_price / residual_avg_cost) - 1) if residual_position >= 0 else ((residual_avg_cost / market_price) - 1)) * 100.0) if (residual_avg_cost and market_price) else 0.0,
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
                # print(f"from update_ib_connection of portfolio manager: {accounts}")
                if accounts:
                    self.account_id = accounts[0]
                    self.account_library = self.ac.get_library(self.account_id, create_if_missing=True)
                    defragment_account_portfolio(self.account_library)
                
                # Initialize FX cache when IB connection is established
                if not self.fx_cache:
                    self.fx_cache = FXCache(self.ib, self.base_currency)
                    
            except Exception as exc:
                add_log(f"Failed to initialize account library: {exc}", "PORTFOLIO", "WARNING")
    
    # =============================================================================
    # Background Tasks for Hourly Snapshots
    # =============================================================================
    
    def start_hourly_snapshots(self):
        """Start the background task for hourly strategy position snapshots"""
        if self._hourly_snapshot_task is None or self._hourly_snapshot_task.done():
            self._hourly_snapshot_task = start_hourly_snapshot_task(self)
            print("Hourly strategy snapshot task started")
    
    def stop_hourly_snapshots(self):
        """Stop the background task for hourly strategy position snapshots"""
        if self._hourly_snapshot_task and not self._hourly_snapshot_task.done():
            stop_hourly_snapshot_task(self._hourly_snapshot_task)
            self._hourly_snapshot_task = None
            print("Hourly strategy snapshot task stopped")
