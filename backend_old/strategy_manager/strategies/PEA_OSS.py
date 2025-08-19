# Post Earnings Announcement Option Selling Strategy (PEA-OSS)

from ib_async import *
import asyncio, time, traceback, sys, math
from broker.trademanager import TradeManager
from broker import connect_to_IB, disconnect_from_IB
from data_and_research import get_strategy_allocation_bounds, get_strategy_symbol, fetch_strategy_params
from broker.utilityfunctions import get_earnings, get_vol_data, get_filtered_put_options
from gui.log import add_log
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict

PARAMS = {
    'min_annualized_premium': 0.1,
    'min_safety_margin': 0.05,
    'max_position_margin': 0.08,
    'max_total_margin': 0.70,
    'max_sector_exposure': 0.20
}

strategy = None

def manage_strategy(client_id, strategy_manager, strategy_loops):
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Instantiate the Strategy class
        global strategy
        strategy = Strategy(client_id, strategy_manager)
        strategy.start()
        add_log(f"Thread Started [{strategy.strategy_symbol}]")

        # Store the loop in the shared dictionary
        strategy_loops[client_id] = loop

        loop.run_forever()

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb_frame = traceback.extract_tb(exc_traceback)[-1]
        filename = tb_frame.filename
        line_number = tb_frame.lineno
        
        print(f"Error in {filename}, line {line_number}: {str(e)}")
        print("Full traceback:")
        traceback.print_exc()

    finally:
        disconnect()
        loop.close()
        del strategy_loops[client_id]

def disconnect():
    if strategy:
        strategy.disconnect()

class Strategy:
    def __init__(self, client_id, strategy_manager):
        global PARAMS
        self.client_id = client_id
        self.strategy_manager = strategy_manager
        self.filename = self.__class__.__module__ + ".py"
        self.strategy_symbol = get_strategy_symbol(self.filename)

        self.ib = connect_to_IB(clientid=self.client_id, symbol=self.strategy_symbol)
        self.trade_manager = TradeManager(self.ib, self.strategy_manager)
        
        # Initialize strategy parameters
        self.initialize_strategy()

    def initialize_strategy(self):
        """Initialize strategy parameters"""
        self.params = fetch_strategy_params(self.strategy_symbol) if not None else PARAMS
        
        # Strategy parameters
        self.min_annualized_premium = float(self.params['min_annualized_premium'])
        self.min_safety_margin = float(self.params['min_safety_margin'])
        self.max_position_margin = float(self.params['max_position_margin'])
        self.max_total_margin = float(self.params['max_total_margin'])
        self.max_sector_exposure = float(self.params['max_sector_exposure'])
        
        # Portfolio tracking
        self.positions = {}
        self.sector_exposure = defaultdict(float)
        
        # Get strategy allocation bounds
        self.target_weight, self.min_weight, self.max_weight = get_strategy_allocation_bounds(self.strategy_symbol)

    def update_investment_status(self):
        """Update the investment status of the strategy"""
        self.positions_df = self.strategy_manager.portfolio_manager.match_ib_positions_with_arcticdb()
        self.positions_df = self.positions_df[self.positions_df['strategy'] == self.strategy_symbol]
        
        if not self.positions_df.empty:
            self.current_positions = self.positions_df.groupby('symbol')['position'].sum()
            self.invested_value = self.positions_df['marketValue_base'].sum()
            self.current_weight = self.positions_df['% of nav'].sum()
        else:
            self.current_positions = pd.Series()
            self.invested_value = 0
            self.current_weight = 0

    def on_fill(self, trade, fill):
        """Handle fill event"""
        self.strategy_manager.message_queue.put({
            'type': 'fill',
            'strategy': self.strategy_symbol,
            'trade': trade,
            'fill': fill
        })
        
    def on_status_change(self, trade):
        """Handle status change event"""
        self.strategy_manager.message_queue.put({
            'type': 'status_change',
            'strategy': self.strategy_symbol,
            'trade': trade,
            'status': trade.orderStatus.status,
            'info': f'Status Change message sent from {self.strategy_symbol}'
        })

    async def run(self):
        """Main strategy loop"""
        while True:
            try:
                # Update investment status
                self.update_investment_status()
                
                # Get earnings announcements and opportunities
                earnings = get_earnings()
                print(earnings)
                if not earnings.empty:
                    #vol_data = get_vol_data(earnings['symbol'].tolist())
                    opportunities = await get_filtered_put_options(
                        self.ib, 
                        earnings['symbol'].tolist(),
                        filtered=True
                    )
                    
                    if not opportunities.empty:
                        # Process opportunities
                        for _, opt in opportunities.iterrows():
                            # Skip if we already have a position
                            if opt['Symbol'] in self.current_positions.index:
                                continue
                                
                            # Check margin and sector limits
                            if await self.check_position_limits(opt):
                                trade = self.place_order(
                                    opt['Contract'],
                                    qty=-abs(opt['position']),
                                    ordertype='LMT',
                                    limit_price=opt['Bid'],
                                    orderRef=f"PEA_OSS_{opt['Symbol']}"
                                )
                
                # Check hedging opportunities
                await self.check_hedging_opportunities()
                
            except Exception as e:
                print(f"Error in PEA-OSS strategy: {str(e)}")
                
            await asyncio.sleep(300)  # Check every 5 minutes

    def start(self):
        """Start the strategy"""
        asyncio.ensure_future(self.run())
    
    def place_order(self, con, qty, ordertype, algo=True, urgency='Patient', orderRef="", limit=None, useRth=True):
        trade = self.trade_manager.trade(
            con, 
            quantity=qty,
            order_type=ordertype,
            urgency=urgency,
            orderRef=orderRef,
            useRth=useRth
        )
        trade.fillEvent += self.on_fill
        trade.statusEvent += self.on_status_change
        return trade

    async def check_position_limits(self, opportunity):
        """Check all position limits before placing a trade"""
        # Check margin requirements
        equity = sum(float(v.value) for v in self.ib.accountSummary() 
                    if v.tag == "EquityWithLoanValue")
        
        order = MarketOrder('SELL', abs(opportunity['position']))
        what_if = await self.ib.whatIfOrderAsync(opportunity['Contract'], order)
        
        if what_if is None:
            return False
            
        new_margin = float(what_if.initMarginChange)
        current_margin = sum(float(v.value) for v in self.ib.accountSummary() 
                           if v.tag == "InitMarginReq")
        
        # Check limits
        if (new_margin > equity * self.max_position_margin or
            (current_margin + new_margin) > equity * self.max_total_margin):
            return False
            
        # Check sector exposure
        sector = self.strategy_manager.risk_manager.get_sector_from_contract(
            Stock(opportunity['Symbol'], 'SMART', 'USD'))
        
        if (self.sector_exposure[sector] + new_margin/equity) > self.max_sector_exposure:
            return False
            
        return True

    def disconnect(self):
        """Disconnect from IB"""
        disconnect_from_IB(ib=self.ib, symbol=self.strategy_symbol) 