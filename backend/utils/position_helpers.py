"""
Position helper functions for IB Multi-Strategy ATS
Based on the original backend_old/broker/utils.py implementation
"""
import datetime
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
        return {
            'symbol': item.contract.symbol,
            'asset_class': get_asset_class(item),
            'position': item.position,  # negative for shorts preserved
            'side': side,
            'timestamp': datetime.datetime.now(datetime.timezone.utc),
            '% of nav': 0.0,  # computed later after FX conversion on marketValue_base
            'averageCost': item.averageCost,
            'marketPrice': item.marketPrice,
            'pnl %': get_pnl(item) * 100,  # percentage
            'strategy': '',  # attribution added later
            'marketValue': item.marketValue,
            'marketValue_base': 0.0,  # will be computed by FXCache
            'currency': item.contract.currency,
            'fx_rate': fx_rate,
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
            'fx_rate': 1.0,
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

        
    