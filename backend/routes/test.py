"""
Test API routes
"""
from datetime import datetime, timezone, timedelta
import random
import asyncio
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ib_async import *
from core.strategy_manager import StrategyManager
from core.log_manager import add_log
from utils.strategy_table_helpers import initialize_strategy_cash

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


class FillRequest(BaseModel):
    symbol: str = "AAPL"
    side: str = "SLD"
    price: float = 271.56
    quantity: float = 1.0
    strategy: Optional[str] = None


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

@router.post("/fill")
async def test_fill(fill_request: FillRequest):
    """Push a synthetic fill into the StrategyManager queue for UI testing"""
    if not strategy_manager:
        raise HTTPException(status_code=500, detail="Strategy Manager not initialized")
    if not hasattr(strategy_manager, "message_queue"):
        raise HTTPException(status_code=500, detail="Message queue not available on StrategyManager")

    strategy_symbol = (fill_request.strategy or fill_request.symbol).upper()
    side = fill_request.side.upper()
    action = "BUY" if side in {"BOT", "BUY"} else "SELL"

    timestamp = datetime.now(timezone.utc)
    price = float(fill_request.price)
    quantity = float(fill_request.quantity)
    con_id = f"Test{random.randint(1000, 9999)}"
    order_id = random.randint(100, 999)
    perm_id = random.randint(10_000_000, 99_999_999)

    contract = Stock(
        symbol=fill_request.symbol,
        exchange="SMART",
        currency="USD",
    )
    contract.conId = con_id  # mark clearly as synthetic
    contract.primaryExchange = "ISLAND"
    contract.tradingClass = "NMS"
    contract.localSymbol = fill_request.symbol

    order = MarketOrder(action, quantity)
    order.orderId = order_id
    order.clientId = 1
    order.permId = perm_id
    order.orderRef = strategy_symbol
    order.algoStrategy = "Adaptive"
    order.algoParams = [TagValue(tag="adaptivePriority", value="Patient")]

    order_status = OrderStatus(
        orderId=order_id,
        status="Filled",
        filled=quantity,
        remaining=0.0,
        avgFillPrice=price,
        permId=perm_id,
        parentId=0,
        lastFillPrice=price,
        clientId=1,
        whyHeld="",
        mktCapPrice=0.0,
    )

    exec_id = f"test.{uuid4().hex[:8]}"
    execution = Execution(
        execId=exec_id,
        time=timestamp,
        acctNumber="TEST-ACCOUNT",
        exchange="ISLAND",
        side=side,
        shares=quantity,
        price=price,
        permId=perm_id,
        clientId=1,
        orderId=order_id,
        liquidation=0,
        cumQty=quantity,
        avgPrice=price,
        orderRef=strategy_symbol,
        evRule="",
        evMultiplier=0.0,
        modelCode="",
        lastLiquidity=1,
        pendingPriceRevision=False,
    )

    commission_report = CommissionReport(
        execId=exec_id,
        commission=0.0,
        currency="USD",
        realizedPNL=0.0,
        yield_=0.0,
        yieldRedemptionDate=0,
    )

    fill = Fill(
        contract=contract,
        execution=execution,
        commissionReport=commission_report,
        time=timestamp,
    )

    log_entries = [
        TradeLogEntry(
            time=timestamp - timedelta(seconds=5),
            status="Submitted",
            message="Order submitted",
            errorCode=0,
        ),
        TradeLogEntry(
            time=timestamp,
            status="Filled",
            message=f"Fill {quantity}@{price}",
            errorCode=0,
        ),
    ]

    trade = Trade(
        contract=contract,
        order=order,
        orderStatus=order_status,
        fills=[fill],
        log=log_entries,
    )

    # Check if strategy table exists, initialize CASH if needed (test endpoint only)
    try:
        pm = strategy_manager.portfolio_manager
        if pm and pm.account_library:
            table_name = f"strategy_{strategy_symbol}"
            if table_name not in pm.account_library.list_symbols():
                add_log(f"Strategy table {table_name} not found, initializing with CASH", "TEST", "INFO")
                
                # Get available funds from IB
                if pm.ib:
                    print("Getting available funds from IB")
                    account_summary = await pm.ib.accountSummaryAsync()
                    print("account_summary")
                    print(account_summary)
                    available_funds = [item for item in account_summary if item.tag == "AvailableFunds"][0]
                    # Initialize CASH synchronously (function doesn't actually use async operations internally)
                    result = await initialize_strategy_cash(pm, strategy_symbol, float(available_funds.value), available_funds.currency)
                    if result:
                        add_log(f"Initialized {strategy_symbol} with {available_funds.currency} {available_funds.value}", "TEST", "INFO")
                        # Give it a moment to ensure write completes
                        await asyncio.sleep(0.1)
                else:
                    print(f"No IB connection available for CASH initialization")
    except Exception as e:
        print(f"Error checking/initializing strategy table: {e}")

    strategy_manager.message_queue.put(
        {
            "type": "fill",
            "strategy": strategy_symbol,
            "trade": trade,
            "fill": fill,
        }
    )

    

    return {
        "success": True,
        "message": f"Synthetic fill enqueued for {strategy_symbol}",
        "orderId": order_id,
        "execId": exec_id,
    }