"""
Position helper functions for IB Multi-Strategy ATS
Based on the original backend_old/broker/utils.py implementation
"""
import datetime
from datetime import timezone, timedelta
import pandas as pd
from typing import Dict, Any
from ib_async import *


def get_asset_class(item):
    """
    Get asset_class from portfolio item.
    
    Args:
        item: IB portfolio item
        
    Returns:
        str: Asset class description
    """
    try:
        if hasattr(item, 'contract') and hasattr(item.contract, 'secType'):
            sec_type = item.contract.secType
            if sec_type == 'STK':
                return 'Stock'
            elif sec_type == 'OPT':
                return 'Option'
            elif sec_type == 'FUT':
                return 'Future'
            elif sec_type == 'CASH':
                return 'Forex'
            elif sec_type == 'BOND':
                return 'Bond'
            elif sec_type == 'CFD':
                return 'CFD'
            elif sec_type == 'CMDTY':
                return 'Commodity'
            else:
                return sec_type
        return 'Unknown'
    except Exception:
        return 'Unknown'

def get_pnl(item):
    """
    Calculate P&L percentage from portfolio item.
    
    Args:
        item: IB portfolio item
        
    Returns:
        float: P&L percentage (as decimal, not percentage)
    """
    try:
        if hasattr(item, 'unrealizedPNL') and hasattr(item, 'marketValue'):
            if item.marketValue != 0:
                return item.unrealizedPNL / abs(item.marketValue)
        return 0.0
    except Exception:
        return 0.0


def get_multiplier(item):
    """
    Get multiplier from portfolio item contract.
    Returns 1.0 if not present or invalid.
    """
    try:
        if hasattr(item, 'contract') and hasattr(item.contract, 'multiplier'):
            m = item.contract.multiplier
            if m and str(m).strip():
                return float(m)
    except:
        pass
    return 1.0

def create_position_dict(portfolio_manager, item):
    """
    Create position dictionary from IB portfolio item.
    
    Args:
        portfolio_manager: PortfolioManager instance with fx_cache and total_equity
        item: IB portfolio item
        
    Returns:
        dict: Position data dictionary (IB-style column names)
    """
    try:
        fx_rate = 1.0  # placeholder; set by FXCache upstream
        side = 'Long' if item.position > 0 else 'Short'
        
        # Handle multiplier for Futures/Options
        multiplier = 1.0
        if hasattr(item, 'contract'):
            multiplier = get_multiplier(item)
            
        market_value = item.marketValue
        # If IB doesn't provide correct marketValue for Futures (sometimes it's price * qty), apply multiplier manually
        # However, item.marketValue from IB usually includes multiplier.
        # But the user specifically asked to "multiply marketPrice and marketValue by multiplier"
        # Typically: MarketValue = Price * Qty * Multiplier.
        # If marketValue looks wrong in the UI, we might need to recalc it.
        # Let's trust IB's marketValue first, but if it's inconsistent with price*qty*mult, we might need logic.
        # User request: "marketPrice and marketValue need to be multiplied by the multiplier"
        # Usually marketPrice is per-unit price. marketValue should be Total Value.
        
        # Re-calculating based on User Request logic for Futures
        sec_type = getattr(item.contract, 'secType', '')
        if sec_type == 'FUT':
             # Adjusted calculation as requested
             # Note: item.marketPrice is usually the raw price.
             # item.marketValue from IB *should* be correct, but if the user says it needs adjustment:
             market_value = item.marketPrice * item.position * multiplier
        
        return {
            'symbol': item.contract.symbol,
            'asset_class': item.contract.secType,
            'position': item.position,  # negative for shorts preserved
            'side': side,
            'timestamp': datetime.datetime.now(datetime.timezone.utc),
            '% of nav': 0.0,  # computed later after FX conversion on marketValue_base
            'averageCost': item.averageCost,
            'marketPrice': item.marketPrice,
            'pnl %': get_pnl(item) * 100,  # percentage
            'strategy': '',  # attribution added later
            'marketValue': market_value,
            'marketValue_base': 0.0,  # will be computed by FXCache
            'currency': item.contract.currency,
            'exchange': getattr(item.contract, 'primaryExchange', '') or getattr(item.contract, 'exchange', 'SMART'),
            'contract': str(item.contract),
            'conId': item.contract.conId,
            'fx_rate': fx_rate,
            'multiplier': multiplier
        }
    except Exception:
        position = getattr(item, 'position', 0)
        side = 'Long' if position > 0 else 'Short'
        return {
            'symbol': getattr(item.contract, 'symbol', 'Unknown') if hasattr(item, 'contract') else 'Unknown',
            'asset_class': 'Unknown',
            'position': position,
            'side': side,
            'timestamp': datetime.datetime.now(datetime.timezone.utc),
            '% of nav': 0.0,
            'averageCost': getattr(item, 'averageCost', 0.0),
            'marketPrice': getattr(item, 'marketPrice', 0.0),
            'pnl %': 0.0,
            'strategy': '',
            'marketValue': getattr(item, 'marketValue', 0.0),
            'marketValue_base': 0.0,
            'currency': getattr(item.contract, 'currency', 'USD') if hasattr(item, 'contract') else 'USD',
            'exchange': 'SMART',
            'contract': '',
            'conId': 0,
            'fx_rate': 1.0,
            'multiplier': 1.0
        }

def extract_fill_data(strategy: str, trade: Trade, fill: Fill) -> Dict[str, Any]:
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
        'timestamp': datetime.datetime.now(datetime.timezone.utc),
        'order_id': trade.order.orderId,
        'perm_id': trade.order.permId
    }

def extract_order_data(strategy: str, trade: Trade, status: str) -> Dict[str, Any]:
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
        'timestamp': datetime.datetime.now(datetime.timezone.utc)
    }
        
def calculate_avg_cost(existing_qty: float,
                       existing_avg_cost: float,
                       delta_qty: float,
                       trade_price: float) -> float:
    """
    existing_qty: signed position before trade (>0 long, <0 short, 0 flat)
    existing_avg_cost: average price of existing position (positive)
    delta_qty: signed trade size (+ buy, - sell)
    trade_price: execution price

    Returns: new average cost (positive price). If position is closed, returns 0.0.
    """
    # No trade -> nothing changes
    if delta_qty == 0:
        return existing_avg_cost

    # Opening from flat -> set avg to trade price
    if existing_qty == 0:
        return trade_price

    new_qty = existing_qty + delta_qty

    # Same-direction add (both have same sign) -> weighted average
    if existing_qty * delta_qty > 0:
        return (existing_avg_cost * existing_qty + trade_price * delta_qty) / new_qty

    # Opposite-direction trade (reduce/close/reverse)
    abs_existing = abs(existing_qty)
    abs_delta = abs(delta_qty)
    eps = 1e-12  # tolerance for float comparisons

    # Partial reduction only (did not cross zero) -> avg cost unchanged
    if abs_delta < abs_existing - eps:
        return existing_avg_cost

    # Exact close -> no position; avg cost not defined (return 0.0 sentinel)
    if abs(abs_delta - abs_existing) <= eps or abs(new_qty) <= eps:
        return 0.0

    # Reversal (crossed zero) -> new position opened at trade_price
    # e.g., long +100 sell 150 => new short -50 at trade_price
    #       short -100 buy 150 => new long +50 at trade_price
    return trade_price

async def create_portfolio_row_from_fill(portfolio_manager, trade: Trade, fill: Fill, strategy: str, ib: IB) -> pd.DataFrame:
    """Create a portfolio row from a fill object"""
    
    fx_cache = portfolio_manager.fx_cache
    base_currency = portfolio_manager.base_currency

    total_equity = sum(float(entry.value) for entry in await ib.accountSummaryAsync() if entry.tag == "EquityWithLoanValue")

    fx_rate = await fx_cache.get_fx_rate(trade.contract.currency, base_currency,ib_client=ib)
    price = float(fill.execution.price)
    qty = float(fill.execution.shares)
    side = fill.execution.side

    # Create row for fill
    return {'timestamp': datetime.datetime.now(timezone.utc),
        'symbol': str(trade.contract.symbol),
        'asset_class': trade.contract.secType,
        'strategy': strategy,
        'position': qty if side == 'BOT' else -qty,
        'averageCost': float(fill.execution.avgPrice),
        'marketPrice': price,
        'marketValue': price * qty,
        'marketValue_base': price * qty / fx_rate,
        '% of nav': float(price * qty / fx_rate / total_equity),
        'currency': str(trade.contract.currency),
        'exchange': trade.contract.exchange or 'SMART',
        'contract': str(trade.contract),
        'conId': trade.contract.conId,
        'fx_rate': fx_rate,
        'pnl %': float(price * qty / fx_rate / total_equity),}


    