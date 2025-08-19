# ATS/broker/trade.py
from ib_async import *
from gui.log import add_log


def trade(ib, contract, quantity, order_type='MKT', urgency='Patient', orderRef="", limit=None):
    """
    Place an Order on the exchange via ib_insync.
    
    :param ib: ib insync instance.
    :param contract: ib.Contract
    :param quantity: order size as a signed integer (quantity > 0 means 'BUY' and quantity < 0 means 'SELL')
    :param order_type: order type such as 'LMT', 'MKT' etc.
    :param urgency: 'Patient' (default), 'Normal', 'Urgent'
    :param limit: if order_type 'LMT' state limit as float
    """
    ib.qualifyContracts(contract)

    # Create order object
    action = 'BUY' if quantity > 0 else 'SELL'
    totalQuantity = int(abs(quantity))

    if order_type == 'LMT':
        assert limit, "Limit price must be specified for limit orders."
        lmtPrice = float(limit)
        order = LimitOrder(action, totalQuantity, lmtPrice)
    elif order_type == 'MKT':
        order = MarketOrder(action, totalQuantity)

    order.algoStrategy = 'Adaptive'
    if urgency == 'Normal':
        order.algoParams = [TagValue('adaptivePriority', 'Normal')]
    elif urgency == 'Urgent':
        order.algoParams = [TagValue('adaptivePriority', 'Urgent')]
    else:
        order.algoParams = [TagValue('adaptivePriority', 'Patient')]

    order.orderRef = orderRef

    # Place the order
    trade = ib.placeOrder(contract, order)
    ib.sleep(1)
    return trade

def roll_future(ib, current_contract, new_contract, orderRef=""):
    """
        Roll a futures contract by closing the current contract and opening a new one.

        :param ib: ib insync instance.
        :param current_contract: The current ib_insync.Contract to be closed.
        :param new_contract: The new ib_insync.Contract to be opened.
        :param orderRef: Reference identifier for the order.
    """
    # Qualify contracts
    ib.qualifyContracts(current_contract,new_contract)

    # Define quantity based on current position
    quantity = [pos.position for pos in ib.portfolio() if pos.contract.localSymbol==current_contract.localSymbol][0]

    # Define the combination contract (bag)
    bag = Contract(symbol=current_contract.symbol, secType='BAG', exchange='SMART', currency=current_contract.currency)
    bag.comboLegs = [
        ComboLeg(conId=current_contract.conId, ratio=1, action="SELL" if quantity > 0 else "BUY",exchange=current_contract.exchange),  # Exiting the current contract
        ComboLeg(conId=new_contract.conId, ratio=1, action="BUY" if quantity > 0 else "SELL",exchange=new_contract.exchange)        # Entering the new contract
    ]

    # Create the order - here we use a Market order as an example
    order = MarketOrder('BUY', abs(quantity))
    order.orderRef = orderRef

    # Place the order
    trade = ib.placeOrder(bag, order)
    return bag, order