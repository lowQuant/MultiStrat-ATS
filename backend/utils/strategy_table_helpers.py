"""
Strategy Table Helpers for IB Multi-Strategy ATS
Handles background tasks for periodic strategy position snapshots and strategy initialization
"""
import asyncio
import pandas as pd
from datetime import datetime, timezone
from typing import Optional


async def hourly_strategy_snapshot_task(portfolio_manager):
    """
    Background task to save strategy positions every hour at the top of the hour.
    
    Args:
        portfolio_manager: Reference to PortfolioManager instance
    """
    while True:
        try:
            # Calculate seconds until next run
            now = datetime.now(timezone.utc)
            next_run = (now + pd.Timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            # next_run = (now + pd.Timedelta(minutes=1)).replace(second=0, microsecond=0)
            seconds_until_next = (next_run - now).total_seconds()
            
            print(f"[PORTFOLIO] Next strategy snapshot in {seconds_until_next:.1f} seconds")
            await asyncio.sleep(seconds_until_next)
            
            # Write strategy positions snapshot
            await write_strategy_positions_snapshot(portfolio_manager)

            # 3. Write Account Summary Snapshot (Total Equity/Cash)
            try:
                if portfolio_manager.ib:
                    # Fetch latest account summary from IB
                    # Note: portfolio_manager.total_equity might be stale if we don't refresh, 
                    # but reconcile_positions(force_refresh=True) above likely updated it.
                    # To be safe, let's grab fresh data.
                    acct_summary = await portfolio_manager.ib.accountSummaryAsync()
                    
                    # Extract key metrics
                    net_liq = next((float(e.value) for e in acct_summary if e.tag == 'NetLiquidation'), 0.0)
                    total_cash = next((float(e.value) for e in acct_summary if e.tag == 'TotalCashValue'), 0.0)
                    available_funds = next((float(e.value) for e in acct_summary if e.tag == 'AvailableFunds'), 0.0)
                    buying_power = next((float(e.value) for e in acct_summary if e.tag == 'BuyingPower'), 0.0)
                    currency = next((e.currency for e in acct_summary if e.tag == 'NetLiquidation'), 'USD')
                    
                    summary_row = {
                        'equity': net_liq,
                        'cash': total_cash,
                        'available_funds': available_funds,
                        'buying_power': buying_power,
                        'currency': currency,
                        'timestamp': datetime.now(timezone.utc)
                    }
                    
                    summary_df = pd.DataFrame([summary_row])
                    summary_df.set_index('timestamp', inplace=True)
                    
                    # Write to 'account_summary' table
                    try:
                        if 'account_summary' in portfolio_manager.account_library.list_symbols():
                            portfolio_manager.account_library.append('account_summary', summary_df, prune_previous_versions=True)
                        else:
                            portfolio_manager.account_library.write('account_summary', summary_df, prune_previous_versions=True)
                    except Exception as schema_error:
                        # If append fails (likely due to schema mismatch from legacy table), overwrite it
                        print(f"[PORTFOLIO WARNING] Schema mismatch for account_summary, overwriting table: {schema_error}")
                        portfolio_manager.account_library.write('account_summary', summary_df, prune_previous_versions=True)
                    
                    print(f"[PORTFOLIO] Saved account summary snapshot: Equity={net_liq:,.2f} {currency}")
            except Exception as e:
                print(f"[PORTFOLIO ERROR] Failed to save account summary snapshot: {e}")
            
        except asyncio.CancelledError:
            print("[PORTFOLIO] Hourly snapshot task cancelled")
            break
        except Exception as e:
            print(f"[PORTFOLIO ERROR] Error in hourly snapshot task: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes on error


async def write_strategy_positions_snapshot(portfolio_manager):
    """
    Write current strategy positions to ArcticDB for each strategy in the portfolio.
    
    Args:
        portfolio_manager: Reference to PortfolioManager instance
    """
    try:
        if not portfolio_manager.account_library:
            print("[PORTFOLIO WARNING] No account library available for snapshot")
            return
        
        # 1. Force fresh reconciliation to get live market prices
        print("[PORTFOLIO] Refreshing portfolio data for snapshot...")
        portfolio_df = await portfolio_manager.reconcile_positions(force_refresh=True)
        
        if portfolio_df is None:
            portfolio_df = pd.DataFrame()
        
        # 2. Identify all strategies to snapshot (Active + In Portfolio)
        strategies_to_snapshot = set()
        
        # A) Get Active Strategies from metadata
        try:
            lib = portfolio_manager.ac.get_library('general', create_if_missing=True)
            if lib.has_symbol('strategies'):
                meta_df = lib.read('strategies').data
                if not meta_df.empty:
                    if meta_df.index.name == 'strategy_symbol':
                        meta_df = meta_df.reset_index()
                    
                    if 'active' in meta_df.columns:
                        # Boolean or 1/0 check
                        active_mask = (meta_df['active'] == True) | (meta_df['active'] == 1)
                        active_syms = meta_df[active_mask]['strategy_symbol'].astype(str).tolist()
                        strategies_to_snapshot.update(s.upper() for s in active_syms)
                    else:
                        # If no active col, take all
                        all_syms = meta_df['strategy_symbol'].astype(str).tolist()
                        strategies_to_snapshot.update(s.upper() for s in all_syms)
        except Exception as meta_e:
            print(f"[PORTFOLIO WARNING] Failed to load active strategies from metadata: {meta_e}")

        # B) Add strategies present in portfolio (even if inactive)
        if not portfolio_df.empty and 'strategy' in portfolio_df.columns:
            port_strategies = portfolio_df['strategy'].unique()
            strategies_to_snapshot.update(str(s).upper() for s in port_strategies if s and s != 'Discretionary' and s != '')
        
        if not strategies_to_snapshot:
            print("[PORTFOLIO] No strategies found for snapshot")
            return
        
        snapshot_time = datetime.now(timezone.utc)
        snapshot_count = 0
        
        for strategy in strategies_to_snapshot:
            try:
                # Filter positions for this strategy from the FRESH portfolio
                # Use fallback empty DF if portfolio is empty
                if not portfolio_df.empty and 'strategy' in portfolio_df.columns:
                    strategy_positions = portfolio_df[portfolio_df['strategy'] == strategy].copy()
                else:
                    strategy_positions = pd.DataFrame()
                
                # Even if strategy_positions is empty, we might have CASH, so we proceed.
                
                if not strategy_positions.empty:
                    # Convert portfolio structure to fill-based structure
                    # Portfolio uses 'position', 'averageCost' but fill structure uses 'quantity', 'avg_cost'
                    fill_structure = pd.DataFrame()
                    fill_structure['strategy'] = strategy_positions.get('strategy', strategy)
                    fill_structure['symbol'] = strategy_positions.get('symbol')
                    fill_structure['asset_class'] = strategy_positions.get('asset_class')
                    fill_structure['exchange'] = strategy_positions.get('exchange', '')  # May not exist in portfolio
                    fill_structure['currency'] = strategy_positions.get('currency')
                    fill_structure['quantity'] = strategy_positions.get('position', 0.0)  # 'position' -> 'quantity'
                    fill_structure['avg_cost'] = strategy_positions.get('averageCost', 0.0)  # 'averageCost' -> 'avg_cost'
                    fill_structure['realized_pnl'] = 0.0  # Portfolio doesn't track this, default to 0
                    fill_structure['timestamp'] = snapshot_time
                    
                    # Set timestamp as index
                    fill_structure.set_index('timestamp', inplace=True)
                    
                    # Write/append to strategy table
                    table_name = f"strategy_{strategy}"
                    
                    if table_name in portfolio_manager.account_library.list_symbols():
                        try:
                            portfolio_manager.account_library.append(table_name, fill_structure, prune_previous_versions=True)
                        except:
                            portfolio_manager.account_library.write(table_name, fill_structure, prune_previous_versions=True)
                    else:
                        portfolio_manager.account_library.write(table_name, fill_structure, prune_previous_versions=True)
                
                # Calculate and save equity snapshot
                # CRITICAL: Pass the fresh portfolio_df to use live market prices
                try:
                    equity_value = await calculate_strategy_equity(portfolio_manager, strategy, portfolio_df)
                    
                    # Get CASH and positions value for breakdown (for realized_pnl tracking)
                    positions_df = await get_strategy_positions(portfolio_manager, strategy, current_only=True)
                    realized_pnl_total = 0.0
                    currency_code = 'USD'

                    if positions_df is not None and not positions_df.empty:
                        realized_pnl_total = positions_df['realized_pnl'].sum()
                        # Try to get currency from cash row, else first row
                        cash_row = positions_df[positions_df['asset_class'] == 'CASH']
                        if not cash_row.empty:
                            currency_code = cash_row.iloc[0]['currency']
                        else:
                            currency_code = positions_df.iloc[0]['currency']

                    # Create EQUITY snapshot row
                    equity_snapshot = pd.DataFrame([{
                        'strategy': strategy,
                        'symbol': 'EQUITY',
                        'asset_class': 'EQUITY',
                        'exchange': '',
                        'currency': currency_code,
                        'quantity': equity_value,  # Total equity (Mark-to-Market)
                        'avg_cost': 1.0,
                        'realized_pnl': realized_pnl_total,
                        'timestamp': snapshot_time
                    }])
                    equity_snapshot.set_index('timestamp', inplace=True)
                    
                    # Append EQUITY snapshot to same table
                    table_name = f"strategy_{strategy}"
                    
                    # Ensure table exists (if it was empty positions and just created/accessed)
                    if table_name not in portfolio_manager.account_library.list_symbols():
                         portfolio_manager.account_library.write(table_name, equity_snapshot, prune_previous_versions=True)
                    else:
                        portfolio_manager.account_library.append(table_name, equity_snapshot, prune_previous_versions=True)
                    
                except Exception as equity_error:
                    print(f"[PORTFOLIO WARNING] Could not save equity snapshot for {strategy}: {equity_error}")
                    
                snapshot_count += 1
                
            except Exception as e:
                print(f"[PORTFOLIO ERROR] Error writing snapshot for strategy {strategy}: {e}")
        
        print(f"[PORTFOLIO] Completed hourly snapshot for {snapshot_count} strategies with equity tracking")
        
    except Exception as e:
        print(f"[PORTFOLIO ERROR] Error in strategy positions snapshot: {e}")


def start_hourly_snapshot_task(portfolio_manager) -> Optional[asyncio.Task]:
    """
    Start the background task for hourly strategy position snapshots.
    
    Args:
        portfolio_manager: Reference to PortfolioManager instance
        
    Returns:
        asyncio.Task: The created background task
    """
    try:
        task = asyncio.create_task(hourly_strategy_snapshot_task(portfolio_manager))
        print("[PORTFOLIO] Started hourly strategy snapshot task")
        return task
    except Exception as e:
        print(f"[PORTFOLIO ERROR] Failed to start hourly snapshot task: {e}")
        return None


def stop_hourly_snapshot_task(task: Optional[asyncio.Task]):
    """
    Stop the background task for hourly snapshots.
    
    Args:
        task: The asyncio.Task to cancel
    """
    if task and not task.done():
        task.cancel()
        print("[PORTFOLIO] Stopped hourly strategy snapshot task")


async def initialize_strategy_cash(portfolio_manager, strategy_symbol: str, initial_cash: float, currency: str = 'USD'):
    """
    Initialize CASH position for a new strategy.
    
    This should be called when a strategy is created (not when it starts running).
    Writes the initial CASH position to the strategy_{strategy_symbol} table.
    
    Args:
        portfolio_manager: Reference to PortfolioManager instance
        strategy_symbol: Strategy identifier (e.g., 'momentum', 'aapl_ema')
        initial_cash: Initial cash amount allocated to this strategy
        currency: Currency code (default: 'USD')
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not portfolio_manager.account_library:
            print(f"[PORTFOLIO ERROR] No account library available for strategy {strategy_symbol}")
            return False
            
        # Create CASH position entry
        cash_position = {
            'strategy': strategy_symbol,
            'symbol': currency,
            'asset_class': 'CASH',
            'exchange': '',
            'currency': currency,
            'quantity': initial_cash,
            'avg_cost': 1.0,  # Always 1.0 for CASH
            'realized_pnl': 0.0,
            'timestamp': datetime.now(timezone.utc)
        }
        
        # Create DataFrame with timestamp index
        cash_df = pd.DataFrame([cash_position])
        cash_df['timestamp'] = pd.to_datetime(cash_df['timestamp'])
        cash_df.set_index('timestamp', inplace=True)
        
        # Write to strategy table
        table_name = f"strategy_{strategy_symbol}"
        
        # Check if table already exists
        if table_name in portfolio_manager.account_library.list_symbols():
            # Append to existing table
            portfolio_manager.account_library.append(table_name, cash_df, prune_previous_versions=True)
            print(f"[PORTFOLIO] Appended CASH position to existing strategy {strategy_symbol}: {currency} {initial_cash:,.2f}")
        else:
            # Create new table
            portfolio_manager.account_library.write(table_name, cash_df, prune_previous_versions=True)
            print(f"[PORTFOLIO] Initialized strategy {strategy_symbol} with CASH: {currency} {initial_cash:,.2f}")
        
        return True
        
    except Exception as e:
        print(f"[PORTFOLIO ERROR] Failed to initialize CASH for strategy {strategy_symbol}: {e}")
        return False


async def get_strategy_positions(
    portfolio_manager,
    strategy_symbol: str,
    symbol: Optional[str] = None,
    current_only: bool = True,
    days_lookback: Optional[int] = 7,
    exclude_equity: bool = True
):
    """
    Get strategy positions with flexible query options.
    
    Args:
        portfolio_manager: Reference to PortfolioManager instance
        strategy_symbol: Strategy identifier
        symbol: If provided, returns only this symbol's position (as Dict). If None, returns all symbols (as DataFrame)
        current_only: If True, returns latest entry per symbol. If False, returns full history
        days_lookback: Number of days to look back for efficiency. None = all data
        exclude_equity: If True, excludes EQUITY snapshots (default). Set to False to include equity history
        
    Returns:
        - If symbol is specified: Dict with position data or None if not found
        - If symbol is None: DataFrame with positions
        
    Examples:
        # Get single symbol for fill processing
        pos = await get_strategy_positions(pm, 'MTUM', symbol='AAPL')
        
        # Get current state for all symbols (excluding EQUITY)
        df = await get_strategy_positions(pm, 'MTUM', current_only=True)
        
        # Get equity history only
        equity_df = await get_strategy_positions(pm, 'MTUM', symbol='EQUITY', exclude_equity=False)
        
        # Get full history
        df = await get_strategy_positions(pm, 'MTUM', current_only=False, days_lookback=None)
    """
    try:
        if not portfolio_manager.account_library:
            return None if symbol else pd.DataFrame()
        
        table_name = f"strategy_{strategy_symbol}"
        
        # Check if table exists
        if table_name not in portfolio_manager.account_library.list_symbols():
            return None if symbol else pd.DataFrame()
        
        # Build query
        from arcticdb import QueryBuilder
        from datetime import datetime, timedelta, timezone
        
        q = QueryBuilder()
        
        # Apply date range filter if specified
        if days_lookback is not None:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days_lookback)
            q = q.date_range((start_time, end_time))
        
        # Apply symbol filter if specified
        if symbol is not None:
            q = q[q['symbol'] == symbol]
        
        # Execute query
        try:
            if days_lookback is not None or symbol is not None:
                df = portfolio_manager.account_library.read(table_name, query_builder=q).data
            else:
                df = portfolio_manager.account_library.read(table_name).data
        except Exception as e:
            # Fallback: read without query if it fails
            try:
                df = portfolio_manager.account_library.read(table_name).data
                if symbol:
                    df = df[df['symbol'] == symbol]
            except Exception:
                print(f"[PORTFOLIO ERROR] Failed to read strategy table {table_name}: {e}")
                return None if symbol else pd.DataFrame()
        
        if df.empty:
            return None if symbol else pd.DataFrame()
        
        # Exclude EQUITY snapshots if requested (default behavior)
        if exclude_equity and symbol != 'EQUITY':
            df = df[df['asset_class'] != 'EQUITY']
        
        if df.empty:
            return None if symbol else pd.DataFrame()
        
        # If current_only, get latest entry per symbol
        if current_only:
            df = df.reset_index()
            df = df.sort_values('timestamp')
            df = df.groupby('symbol').last().reset_index()
            df = df.set_index('timestamp')
        
        # Return format depends on whether specific symbol was requested
        if symbol is not None:
            # Return as Dict for single symbol
            if df.empty:
                return None
            # Update cache for performance
            cache_key = f"{strategy_symbol}_{symbol}"
            position = df.iloc[-1].to_dict() if not df.empty else None
            if position and hasattr(portfolio_manager, '_position_cache'):
                portfolio_manager._position_cache[cache_key] = position
            return position
        else:
            # Return as DataFrame for all symbols
            return df
        
    except Exception as e:
        print(f"[PORTFOLIO ERROR] Failed to get strategy positions: {e}")
        import traceback
        traceback.print_exc()
        return None if symbol else pd.DataFrame()


async def get_strategy_equity_history(
    portfolio_manager,
    strategy_symbol: str,
    days_lookback: Optional[int] = 30
) -> pd.DataFrame:
    """
    Get historical equity snapshots for a strategy.
    
    Args:
        portfolio_manager: Reference to PortfolioManager instance
        strategy_symbol: Strategy identifier
        days_lookback: Number of days to look back. None = all history
        
    Returns:
        DataFrame with columns: timestamp (index), equity, realized_pnl
        
    Example:
        # Get last 30 days equity curve
        equity_df = await get_strategy_equity_history(pm, 'MTUM', days_lookback=30)
        
        # Plot equity curve
        import matplotlib.pyplot as plt
        plt.plot(equity_df.index, equity_df['equity'])
        plt.title('Strategy Equity Curve')
    """
    try:
        # Get EQUITY snapshots (exclude_equity=False, symbol='EQUITY')
        equity_df = await get_strategy_positions(
            portfolio_manager, 
            strategy_symbol, 
            symbol='EQUITY',
            current_only=False,
            days_lookback=days_lookback,
            exclude_equity=False
        )
        
        if equity_df.empty:
            return pd.DataFrame()
        
        # Rename 'quantity' to 'equity' for clarity
        equity_df = equity_df.rename(columns={'quantity': 'equity'})
        
        # Return only relevant columns
        return equity_df[['equity', 'realized_pnl', 'currency']].copy()
        
    except Exception as e:
        print(f"[PORTFOLIO ERROR] Failed to get equity history for {strategy_symbol}: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


async def calculate_strategy_equity(portfolio_manager, strategy_symbol: str, portfolio_df: pd.DataFrame = None) -> float:
    """
    Calculate total equity for a strategy in its base currency.
    Equity = CASH + Sum(position_values_in_strategy_currency)
    
    If portfolio_df is provided, uses live market values (Mark-to-Market).
    Otherwise, falls back to avg_cost (Cost Basis).
    
    Args:
        portfolio_manager: Reference to PortfolioManager instance
        strategy_symbol: Strategy identifier
        portfolio_df: Optional DataFrame containing current portfolio with market values
        
    Returns:
        float: Total equity in strategy's base currency
    """
    try:
        # Get current positions (exclude EQUITY snapshots to avoid recursion!)
        # We fetch this to get the CASH position and list of symbols.
        positions_df = await get_strategy_positions(portfolio_manager, strategy_symbol, current_only=True, exclude_equity=True)
        
        if positions_df is None or positions_df.empty:
            return 0.0
        
        # Get CASH position (this is our base currency for the strategy)
        cash_row = positions_df[positions_df['asset_class'] == 'CASH']
        if cash_row.empty:
            # print(f"[PORTFOLIO WARNING] No CASH position for {strategy_symbol}")
            strategy_currency = 'USD'  # Default
            cash_value = 0.0
        else:
            strategy_currency = cash_row.iloc[0]['currency']
            cash_value = float(cash_row.iloc[0]['quantity'])
        
        total_position_value = 0.0
        
        # Calculate value of non-CASH positions
        # If portfolio_df is available, we prioritize Market Value from there.
        
        if portfolio_df is not None and not portfolio_df.empty and 'strategy' in portfolio_df.columns:
            # Filter portfolio for this strategy
            strat_port = portfolio_df[portfolio_df['strategy'] == strategy_symbol]
            
            # Sum market value (converted to strategy currency)
            base_currency = getattr(portfolio_manager, 'base_currency', 'USD')
            
            for _, row in strat_port.iterrows():
                # marketValue in portfolio is usually in Account Base Currency
                # Note: PortfolioManager.reconcile_positions ensures 'marketValue' is in Base Currency for display
                
                mv_base = float(row.get('marketValue', 0.0))
                
                # Convert Account Base -> Strategy Currency
                if base_currency != strategy_currency:
                    if portfolio_manager.fx_cache:
                        # We need Base -> Strategy rate
                        rate = await portfolio_manager.fx_cache.get_fx_rate(base_currency, strategy_currency)
                        total_position_value += mv_base * rate
                    else:
                         # Fallback: assume 1:1 if no FX
                         total_position_value += mv_base
                else:
                    total_position_value += mv_base
                    
        else:
            # Fallback: Use stored avg_cost from positions_df (Cost Basis)
            non_cash = positions_df[(positions_df['asset_class'] != 'CASH') & (positions_df['asset_class'] != 'EQUITY')]
            
            for _, pos in non_cash.iterrows():
                quantity = float(pos['quantity'])
                
                # Skip closed positions (quantity = 0)
                if quantity == 0:
                    continue
                
                # Use avg_cost as the position value
                avg_cost = float(pos['avg_cost'])
                position_currency = pos['currency']
                
                # Position value in its currency
                position_value = quantity * avg_cost
                
                # Convert to strategy currency if different
                if position_currency != strategy_currency:
                    if portfolio_manager.fx_cache:
                        fx_rate = await portfolio_manager.fx_cache.get_fx_rate(position_currency, strategy_currency)
                        position_value = position_value * fx_rate
                    else:
                        # print(f"[PORTFOLIO WARNING] FX cache not available for {pos['symbol']}")
                        pass
                
                total_position_value += position_value
        
        total_equity = cash_value + total_position_value
        
        return total_equity
        
    except Exception as e:
        print(f"[PORTFOLIO ERROR] Failed to calculate equity for {strategy_symbol}: {e}")
        import traceback
        traceback.print_exc()
        return 0.0


async def update_strategy_cash(portfolio_manager, strategy_symbol: str, fill_data: dict):
    """
    Update CASH position after a fill/trade.
    
    BUY/BOT: Decrease cash (pay for asset)
    SELL/SLD: Increase cash (receive payment)
    
    Args:
        portfolio_manager: Reference to PortfolioManager instance
        strategy_symbol: Strategy identifier
        fill_data: Fill data dict with keys: symbol, side, quantity, price, commission, currency
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not portfolio_manager.account_library:
            print(f"[PORTFOLIO ERROR] No account library available for strategy {strategy_symbol}")
            return False
        
        table_name = f"strategy_{strategy_symbol}"
        
        # Check if strategy table exists
        if table_name not in portfolio_manager.account_library.list_symbols():
            print(f"[PORTFOLIO ERROR] Strategy table {table_name} does not exist. Cannot update CASH.")
            return False
        
        # Use QueryBuilder to efficiently read only the latest CASH position
        # Read only last 7 days to avoid loading thousands of historical CASH rows
        from arcticdb import QueryBuilder
        from datetime import datetime, timedelta, timezone
        
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=7)
        
        q = QueryBuilder()
        q = q[q['asset_class'] == 'CASH']
        q = q.date_range((start_time, end_time))
        
        try:
            cash_df = portfolio_manager.account_library.read(table_name, query_builder=q).data
        except Exception as e:
            print(f"[PORTFOLIO ERROR] Failed to query CASH position: {e}")
            return False
        
        # Get latest CASH position
        if cash_df.empty:
            # Fallback: try without date_range (for strategies with no recent fills)
            try:
                q_fallback = QueryBuilder()
                q_fallback = q_fallback[q_fallback['asset_class'] == 'CASH']
                cash_df = portfolio_manager.account_library.read(table_name, query_builder=q_fallback).data
            except Exception:
                pass
            
            if cash_df.empty:
                print(f"[PORTFOLIO WARNING] No CASH position found for {strategy_symbol}. Cannot update CASH without initial position.")
                return False
        
        # Get the most recent entry (index is already sorted by ArcticDB)
        latest_cash = cash_df.iloc[-1]
        current_cash = float(latest_cash['quantity'])
        cash_currency = latest_cash['currency']
        
        # Calculate trade cost
        quantity = float(fill_data.get('quantity', 0))
        price = float(fill_data.get('price', 0))
        commission = float(fill_data.get('commission', 0))
        side = fill_data.get('side', '').upper()  # BOT or SLD
        fill_currency = fill_data.get('currency', cash_currency)
        
        # Trade cost in fill currency
        trade_cost = (quantity * price) + commission
        
        # Convert to CASH currency if different from fill currency
        if fill_currency != cash_currency:
            if portfolio_manager.fx_cache:
                fx_rate = await portfolio_manager.fx_cache.get_fx_rate(fill_currency, cash_currency)
                trade_cost = trade_cost / fx_rate
                print(f"[PORTFOLIO] Converted trade cost from {fill_currency} to {cash_currency}: {trade_cost:,.2f} (rate={fx_rate:.4f})")
            else:
                print(f"[PORTFOLIO WARNING] FX cache not available, using trade cost without conversion")
        
        # Update CASH based on side
        if side in ['BOT', 'BUY']:
            new_cash = current_cash - trade_cost
            print(f"[PORTFOLIO] {strategy_symbol} BUY: CASH {cash_currency} {current_cash:,.2f} - {trade_cost:,.2f} = {new_cash:,.2f}")
        elif side in ['SLD', 'SELL']:
            new_cash = current_cash + trade_cost
            print(f"[PORTFOLIO] {strategy_symbol} SELL: CASH {cash_currency} {current_cash:,.2f} + {trade_cost:,.2f} = {new_cash:,.2f}")
        else:
            print(f"[PORTFOLIO ERROR] Unknown side: {side}")
            return False
        
        # Create new CASH position entry
        cash_position = {
            'strategy': strategy_symbol,
            'symbol': cash_currency,
            'asset_class': 'CASH',
            'exchange': '',
            'currency': cash_currency,
            'quantity': new_cash,
            'avg_cost': 1.0,
            'realized_pnl': float(latest_cash['realized_pnl']),
            'timestamp': datetime.now(timezone.utc)
        }
        
        # Append to strategy table
        cash_df = pd.DataFrame([cash_position])
        cash_df['timestamp'] = pd.to_datetime(cash_df['timestamp'])
        cash_df.set_index('timestamp', inplace=True)
        
        portfolio_manager.account_library.append(table_name, cash_df, prune_previous_versions=True)
        
        return True
        
    except Exception as e:
        print(f"[PORTFOLIO ERROR] Failed to update CASH for strategy {strategy_symbol}: {e}")
        import traceback
        traceback.print_exc()
        return False