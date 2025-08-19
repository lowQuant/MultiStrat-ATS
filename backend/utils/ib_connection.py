"""
Unified IB connection utilities - based on the old backend pattern
Handles connections for both StrategyManager (clientId=0) and individual strategies
"""
import asyncio
from ib_async import IB, Stock, util
from core.log_manager import add_log


async def connect_to_ib(host='127.0.0.1', port=7497, client_id=0, symbol=None):
    """
    Connect to Interactive Brokers
    
    Args:
        host: IB host (default: 127.0.0.1)
        port: IB port (default: 7497)
        client_id: Client ID (0 for StrategyManager, >0 for strategies)
        symbol: Strategy symbol for logging (optional)
    
    Returns:
        IB instance if successful, None if failed
    """
    ib = IB()
    
    try:
        await ib.connectAsync(host, port, clientId=client_id)
        
        # Log based on client_id and symbol
        if client_id == 0:
            add_log(f'IB Connection established with clientId={client_id}', 'StrategyManager')
        else:
            if symbol:
                add_log(f'IB Connection established with clientId={client_id} [{symbol}]', symbol)
            else:
                add_log(f'IB Connection established with clientId={client_id}', 'STRATEGY')
        
        return ib
        
    except Exception as e:
        if client_id == 0:
            add_log(f'Connection failed: {str(e)}', 'StrategyManager', 'ERROR')
        else:
            component = symbol if symbol else 'STRATEGY'
            add_log(f'Connection failed: {str(e)}', component, 'ERROR')
        return None


async def disconnect_from_ib(ib, symbol=None):
    """
    Disconnect from Interactive Brokers
    
    Args:
        ib: IB instance to disconnect
        symbol: Strategy symbol for logging (optional)
    """
    if ib and ib.isConnected():
        client_id = ib.client.clientId
        
        # Log based on client_id and symbol
        if client_id == 0:
            add_log("Disconnected from IB", "StrategyManager")
        else:
            if symbol:
                add_log(f"Disconnected from IB", symbol)
            else:
                add_log(f"Disconnected from IB [clientId {client_id}]", "STRATEGY")
        
        ib.disconnect()


async def test_ib_connection(ib, test_symbol='SPY'):
    """
    Test IB connection with market data request
    
    Args:
        ib: Connected IB instance
        test_symbol: Symbol to test market data (default: SPY)
    
    Returns:
        dict with connection test results
    """
    if not ib or not ib.isConnected():
        raise Exception("IB not connected")
    
    try:
        # Wait for connection to be fully established
        await asyncio.sleep(1)
        
        # Get account summary
        account_summary = await ib.accountSummaryAsync()
        
        # Test market data
        contract = Stock(test_symbol, 'SMART', 'USD')
        await ib.qualifyContractsAsync(contract)
        
        # Request market data
        ticker = ib.reqMktData(contract)
        await asyncio.sleep(2)  # Wait for market data
        
        result = {
            "status": "connected",
            "host": ib.client.host,
            "port": ib.client.port,
            "client_id": ib.client.clientId,
            "account_count": len(account_summary) if account_summary else 0,
            "test_symbol": test_symbol,
            "market_data_available": ticker.last is not None,
            "connection_type": "master" if ib.client.clientId == 0 else "strategy"
        }
        
        # Cancel market data
        ib.cancelMktData(contract)
        
        return result
        
    except Exception as e:
        raise Exception(f"Connection test failed: {e}")


def get_next_client_id(existing_connections):
    """
    Get next available client ID for strategy connections
    
    Args:
        existing_connections: List of existing client IDs
    
    Returns:
        int: Next available client ID (starting from 1)
    """
    used_ids = set(existing_connections)
    for client_id in range(1, 100):  # Support up to 99 strategies
        if client_id not in used_ids:
            return client_id
    raise Exception("No available client IDs (max 99 strategies)")