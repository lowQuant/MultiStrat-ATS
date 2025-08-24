"""
Test API routes
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ib_async import Stock, Contract
from core.strategy_manager import StrategyManager
from core.log_manager import add_log

# Create router for test endpoints
router = APIRouter(prefix="/api/test", tags=["test"])

# This will be injected by main.py
strategy_manager: StrategyManager = None

def set_strategy_manager(sm: StrategyManager):
    """Set the strategy manager instance"""
    global strategy_manager
    strategy_manager = sm


class TradeRequest(BaseModel):
    symbol: str
    quantity: int
    order_type: str = "MKT"
    algo: bool = True
    urgency: str = "Patient"
    orderRef: str = ""
    limit: Optional[float] = None
    useRth: bool = False
    exchange: str = "SMART"
    currency: str = "USD"
    secType: str = "STK"


@router.post("/logs")
async def test_logs():
    """Generate test logs for frontend testing"""
    add_log("This is an error message", "TESTCOMPONENT", "ERROR")
    add_log("This is an info message", "TESTCOMPONENT", "INFO")
    add_log("This is a warning message", "TESTCOMPONENT", "WARNING")
    add_log("Strategy-specific log message", "AAPL", "INFO")
    add_log("StrategyManager system log", "CORE", "INFO")
    
    return {"message": "Test logs generated successfully"}


@router.post("/trade")
async def test_trade(trade_request: TradeRequest):
    """Test trade execution using TradeManager"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    
    if not hasattr(strategy_manager, 'trade_manager') or not strategy_manager.trade_manager:
        raise HTTPException(status_code=500, detail="TradeManager not initialized")
    
    try:
        # Create contract based on request
        if trade_request.secType == "STK":
            contract = Stock(
                symbol=trade_request.symbol,
                exchange=trade_request.exchange,
                currency=trade_request.currency
            )
        else:
            # Generic contract for other security types
            contract = Contract(
                symbol=trade_request.symbol,
                secType=trade_request.secType,
                exchange=trade_request.exchange,
                currency=trade_request.currency
            )
        
        # Execute trade using TradeManager
        trade = await strategy_manager.trade_manager.trade(
            contract=contract,
            quantity=trade_request.quantity,
            order_type=trade_request.order_type,
            algo=trade_request.algo,
            urgency=trade_request.urgency,
            orderRef=trade_request.orderRef,
            limit=trade_request.limit,
            useRth=trade_request.useRth
        )
        
        return {
            "success": True,
            "message": f"Trade executed: {trade_request.quantity} {trade_request.symbol}",
            "trade_id": trade.order.orderId if trade and trade.order else None,
            "contract": {
                "symbol": trade_request.symbol,
                "secType": trade_request.secType,
                "exchange": trade_request.exchange,
                "currency": trade_request.currency
            },
            "order": {
                "action": "BUY" if trade_request.quantity > 0 else "SELL",
                "totalQuantity": abs(trade_request.quantity),
                "orderType": trade_request.order_type,
                "orderRef": trade_request.orderRef
            }
        }
        
    except Exception as e:
        add_log(f"Test trade failed: {str(e)}", "TEST", "ERROR")
        return {"success": False, "error": str(e)}
