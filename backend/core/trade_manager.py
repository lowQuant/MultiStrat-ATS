"""
Trade Manager for IB Multi-Strategy ATS
Based on the old project's trademanager.py
"""
from ib_async import *
import asyncio
from typing import Optional
from core.log_manager import add_log


class TradeManager:
    def __init__(self, ib_client, strategy_manager):
        self.ib = ib_client
        self.strategy_manager = strategy_manager

    async def trade(self, contract, quantity: int, order_type: str = 'MKT', algo: bool = True, 
                    urgency: str = 'Patient', orderRef: str = "", limit: Optional[float] = None, 
                    useRth: bool = False):
        """
        Place an Order on the exchange via ib_async.
        :param contract: ib.Contract
        :param quantity: order size as a signed integer (quantity > 0 means 'BUY' and quantity < 0 means 'SELL')
        :param order_type: order type such as 'LMT', 'MKT' etc.
        :param algo: use adaptive algo
        :param urgency: 'Patient' (default), 'Normal', 'Urgent'
        :param orderRef: reference identifier for the order
        :param limit: if order_type 'LMT' state limit as float
        :param useRth: use regular trading hours
        """
        try:
            # Qualify contract using async method
            await self.ib.qualifyContractsAsync(contract)
            
            # Create order object
            action = 'BUY' if quantity > 0 else 'SELL'
            totalQuantity = int(abs(quantity))

            if order_type == 'LMT':
                if not limit:
                    raise ValueError("Limit price must be specified for limit orders.")
                lmtPrice = float(limit)
                order = LimitOrder(action, totalQuantity, lmtPrice)
            elif order_type == 'MKT':
                order = MarketOrder(action, totalQuantity)
            else:
                raise ValueError(f"Unsupported order type: {order_type}")

            # Set algo parameters
            if algo:
                order.algoStrategy = 'Adaptive'
                if urgency == 'Normal':
                    order.algoParams = [TagValue('adaptivePriority', 'Normal')]
                elif urgency == 'Urgent':
                    order.algoParams = [TagValue('adaptivePriority', 'Urgent')]
                else:
                    order.algoParams = [TagValue('adaptivePriority', 'Patient')]

            order.orderRef = orderRef
            order.useRth = useRth

            # Place the order using sync method (placeOrder doesn't have async version)
            trade = self.ib.placeOrder(contract, order)
            await asyncio.sleep(1)

            # Notify the strategy manager about the order placement
            # orderRef should be the strategy symbol for proper logging
            if hasattr(self.strategy_manager, 'message_queue'):
                self.strategy_manager.message_queue.put({
                    'type': 'order',
                    'strategy': orderRef,  # This should be the strategy symbol
                    'trade': trade,
                    'contract': contract,
                    'order': order,
                    'info': 'sent from TradeManager'
                })
            
            return trade

        except Exception as e:
            add_log(f"Trade failed: {str(e)}", "TRADEMANAGER", "ERROR")
            raise e

    async def roll_future(self, current_contract, new_contract, orderRef: str = ""):
        """
        Roll a futures contract by closing the current contract and opening a new one.
        :param current_contract: The current ib_async.Contract to be closed.
        :param new_contract: The new ib_async.Contract to be opened.
        :param orderRef: Reference identifier for the order.
        """
        try:
            # Qualify contracts
            await self.ib.qualifyContractsAsync(current_contract, new_contract)

            # Define quantity based on current position
            portfolio = self.ib.portfolio()
            quantity = 0
            for pos in portfolio:
                if pos.contract.localSymbol == current_contract.localSymbol:
                    quantity = pos.position
                    break

            if quantity == 0:
                add_log(f"No position found for {current_contract.localSymbol}", "TRADEMANAGER", "WARNING")
                return None, None

            # Define the combination contract (bag)
            bag = Contract(
                symbol=current_contract.symbol, 
                secType='BAG', 
                exchange='SMART', 
                currency=current_contract.currency
            )
            bag.comboLegs = [
                ComboLeg(
                    conId=current_contract.conId, 
                    ratio=1, 
                    action="SELL" if quantity > 0 else "BUY",
                    exchange=current_contract.exchange
                ),  # Exiting the current contract
                ComboLeg(
                    conId=new_contract.conId, 
                    ratio=1, 
                    action="BUY" if quantity > 0 else "SELL",
                    exchange=new_contract.exchange
                )   # Entering the new contract
            ]

            # Create the order - here we use a Market order
            order = MarketOrder('BUY', abs(quantity))
            order.orderRef = orderRef

            # Place the order
            trade = self.ib.placeOrder(bag, order)
            
            add_log(f"Future roll executed: {current_contract.localSymbol} -> {new_contract.localSymbol}", 
                   "TRADEMANAGER", "INFO")
            
            return bag, order

        except Exception as e:
            add_log(f"Future roll failed: {str(e)}", "TRADEMANAGER", "ERROR")
            raise e
