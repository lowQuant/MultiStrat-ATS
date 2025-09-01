"""
Position helper functions for IB Multi-Strategy ATS
Based on the original backend_old/broker/utils.py implementation
"""
import datetime
from typing import Dict, Any
from ib_async import Contract


def get_asset_class(item):
    """
    Get asset class from portfolio item.
    
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
        dict: Position data dictionary
    """
    try:
        # Defer FX conversion to PortfolioManager async pipeline.
        # Use placeholder here to avoid awaiting inside sync context.
        fx_rate = 1.0
        
        # Calculate % of NAV
        nav_percentage = 0.0
        if hasattr(portfolio_manager, 'total_equity') and portfolio_manager.total_equity != 0:
            nav_percentage = (item.marketValue / portfolio_manager.total_equity) * 100
        
        # Determine if position is long or short for grouping
        side = 'Long' if item.position > 0 else 'Short'
        
        return {
            'symbol': item.contract.symbol,
            'asset class': get_asset_class(item),
            'position': item.position,  # Keep original position (negative for shorts)
            'side': side,  # Add side for grouping
            'timestamp': datetime.datetime.now(),
            '% of nav': nav_percentage,
            'averageCost': item.averageCost,
            'marketPrice': item.marketPrice,
            'pnl %': get_pnl(item) * 100,  # Convert to percentage
            'strategy': '',  # Will be populated later with strategy attribution
            'contract': item.contract,
            'trade': '',
            'trade_context': '',
            'open_dt': datetime.date.today().isoformat(),
            'close_dt': '',
            'deleted': False,
            'delete_dt': '',
            'marketValue': item.marketValue,
            'unrealizedPNL': item.unrealizedPNL,
            'currency': item.contract.currency,
            'realizedPNL': item.realizedPNL,
            'account': item.account,
            'marketValue_base': 0.0,  # Will be calculated by FXCache
            'fx_rate': fx_rate
        }
    except Exception as e:
        # Return minimal position dict if error occurs
        position = getattr(item, 'position', 0)
        side = 'Long' if position > 0 else 'Short'
        
        return {
            'symbol': getattr(item.contract, 'symbol', 'Unknown') if hasattr(item, 'contract') else 'Unknown',
            'asset class': 'Unknown',
            'position': position,
            'side': side,
            'timestamp': datetime.datetime.now(),
            '% of nav': 0.0,
            'averageCost': getattr(item, 'averageCost', 0.0),
            'marketPrice': getattr(item, 'marketPrice', 0.0),
            'pnl %': 0.0,
            'strategy': '',
            'contract': getattr(item, 'contract', None),
            'trade': '',
            'trade_context': '',
            'open_dt': datetime.date.today().isoformat(),
            'close_dt': '',
            'deleted': False,
            'delete_dt': '',
            'marketValue': getattr(item, 'marketValue', 0.0),
            'unrealizedPNL': getattr(item, 'unrealizedPNL', 0.0),
            'currency': getattr(item.contract, 'currency', 'USD') if hasattr(item, 'contract') else 'USD',
            'realizedPNL': getattr(item, 'realizedPNL', 0.0),
            'account': getattr(item, 'account', ''),
            'marketValue_base': 0.0,
            'fx_rate': 1.0
        }
