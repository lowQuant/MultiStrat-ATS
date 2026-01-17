# backend/routes/execution.py
"""
Execution routes for IB Multi-Strategy ATS
Provides REST API endpoints for execution data and management
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, Dict, Any

from core.strategy_manager import StrategyManager
from core.trade_manager import TradeManager
from core.log_manager import add_log
from ib_async import Contract  # used to construct contracts for TradeManager

router = APIRouter(prefix="/api/trade", tags=["trade"])

# Injected by main.py
strategy_manager: Optional[StrategyManager] = None

# Module-level reference so routes can use TradeManager directly
trade_manager: Optional[TradeManager] = None

def set_strategy_manager(sm: StrategyManager):
    """Set the strategy manager instance and expose TradeManager"""
    global strategy_manager, trade_manager
    strategy_manager = sm
    trade_manager = sm.trade_manager  # will be None until IB is connected; that's okay

@router.get("/orders")
async def get_open_orders():
    """
    Get list of all open orders (using openTrades for full context).
    """
    global strategy_manager
    
    if strategy_manager is None:
        raise HTTPException(status_code=503, detail="Strategy manager not initialized")
        
    ib = strategy_manager.ib_client
    if not ib or not ib.isConnected():
        raise HTTPException(status_code=503, detail="IB is not connected")
        
    # openTrades() returns list of Trade objects (Contract + Order + OrderStatus)
    trades = ib.openTrades()
    
    results = []
    for t in trades:
        results.append({
            "symbol": t.contract.symbol,
            "conId": t.contract.conId,
            "orderId": t.order.orderId,
            "permId": t.order.permId,
            "action": t.order.action,
            "orderType": t.order.orderType,
            "totalQuantity": t.order.totalQuantity,
            "lmtPrice": t.order.lmtPrice,
            "auxPrice": t.order.auxPrice,
            "status": t.orderStatus.status,
            "filled": t.orderStatus.filled,
            "remaining": t.orderStatus.remaining,
            "avgFillPrice": t.orderStatus.avgFillPrice,
            "lastFillPrice": t.orderStatus.lastFillPrice,
            "clientId": t.order.clientId,
            "orderRef": t.order.orderRef
        })
        
    return results

@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: int):
    """
    Cancel an order by its orderId or permId.
    """
    global strategy_manager
    
    if not strategy_manager or not strategy_manager.ib_client or not strategy_manager.ib_client.isConnected():
        raise HTTPException(status_code=503, detail="IB is not connected")
        
    ib = strategy_manager.ib_client
    
    # Try to find the order in openTrades first (has context)
    trades = ib.openTrades()
    target_order = None
    
    for t in trades:
        if t.order.orderId == order_id or t.order.permId == order_id:
            target_order = t.order
            break
            
    if not target_order:
        # Fallback: Check raw orders list
        orders = ib.orders()
        for o in orders:
            if o.orderId == order_id or o.permId == order_id:
                target_order = o
                break
                
    if target_order:
        ib.cancelOrder(target_order)
        return {"success": True, "message": f"Cancellation request submitted for order {order_id}"}
        
    raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

@router.post("")
async def place_trade(payload: Dict[str, Any]):
    """Place an order via TradeManager.trade using a flexible JSON payload.

    Accepted JSON formats:
    1) Flat (legacy):
       {"symbol":"AAPL","secType":"STK","exchange":"SMART","currency":"USD",
        "side":"buy","quantity":10,"order_type":"MKT","price":null,
        "algo":true,"urgency":"Patient","orderRef":"MANUAL","useRth":false}

    2) Nested:
       {"contract": { ... any ib_async.Contract fields ... },
        "order": {"side":"buy","quantity":10,"order_type":"MKT","price":null,
                   "algo":true,"urgency":"Patient","orderRef":"MANUAL","useRth":false}}
    """
    global strategy_manager, trade_manager

    # Ensure StrategyManager and IB client are ready
    if strategy_manager is None:
        raise HTTPException(status_code=503, detail="Strategy manager not initialized")
    if not getattr(strategy_manager, 'is_connected', False) or strategy_manager.ib_client is None:
        raise HTTPException(status_code=503, detail="IB is not connected")

    # Ensure TradeManager exists and is bound to the current IB client
    if trade_manager is None or trade_manager.ib is not strategy_manager.ib_client:
        trade_manager = TradeManager(strategy_manager.ib_client, strategy_manager)
        print("TradeManager instantiated in execution routes")

    # Extract contract/order data (support both flat and nested formats)
    contract_data: Dict[str, Any] = payload.get("contract", {}) if isinstance(payload.get("contract"), dict) else {}
    order_data: Dict[str, Any] = payload.get("order", {}) if isinstance(payload.get("order"), dict) else {}

    # If flat, merge into our dicts
    if not contract_data:
        # Collect common contract keys from flat payload
        contract_keys = [
            "secType", "symbol", "exchange", "currency", "primaryExchange",
            "conId", "localSymbol", "lastTradeDateOrContractMonth", "multiplier",
            "tradingClass", "strike", "right"
        ]
        contract_data = {k: v for k, v in payload.items() if k in contract_keys}
    if not order_data:
        order_keys = [
            "side", "quantity", "order_type", "price", "algo", "urgency", "orderRef", "useRth"
        ]
        order_data = {k: v for k, v in payload.items() if k in order_keys}

    # Build Contract dynamically from provided fields
    try:
        contract = Contract()
        for k, v in contract_data.items():
            setattr(contract, k, v)
        # Minimal defaults when omitted
        if not getattr(contract, 'secType', None):
            contract.secType = 'STK'
        if not getattr(contract, 'exchange', None):
            contract.exchange = 'SMART'
        if not getattr(contract, 'currency', None):
            contract.currency = 'USD'
        if not getattr(contract, 'symbol', None) and not getattr(contract, 'conId', None):
            raise ValueError("Contract requires either 'symbol' or 'conId'")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid contract parameters: {e}")

    # Validate order basics
    try:
        side = str(order_data.get("side", "")).lower()
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        quantity = int(order_data.get("quantity", 0))
        if quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        order_type = str(order_data.get("order_type", "MKT")).upper()
        limit_price = order_data.get("price") if order_type in ("LMT", "LIMIT") else None
        algo = bool(order_data.get("algo", True))
        urgency = str(order_data.get("urgency", "Patient"))
        order_ref = str(order_data.get("orderRef", "Discretionary"))
        use_rth = bool(order_data.get("useRth", False))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid order parameters: {e}")

    signed_qty = quantity if side == 'buy' else -quantity

    try:
        await trade_manager.trade(
            contract=contract,
            quantity=signed_qty,
            order_type=("LMT" if order_type in ("LMT", "LIMIT") else "MKT"),
            algo=algo,
            urgency=urgency,
            orderRef=order_ref,
            limit=limit_price,
            useRth=use_rth,
        )
        return {
            "success": True,
            "symbol": getattr(contract, 'symbol', None),
            "conId": getattr(contract, 'conId', None),
            "side": side,
            "quantity": quantity,
            "order_type": ("LMT" if limit_price is not None else "MKT"),
            "price": limit_price,
            "orderRef": order_ref,
            "message": "Order submitted",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to place order: {e}")