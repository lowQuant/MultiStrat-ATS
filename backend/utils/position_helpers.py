"""
Position helper functions for IB Multi-Strategy ATS
Based on the original backend_old/broker/utils.py implementation
"""
import datetime
from typing import Dict, Any
from ib_async import Contract


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
