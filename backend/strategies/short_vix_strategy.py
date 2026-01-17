"""
Short VIX Futures Strategy

This strategy shorts VIX futures based on:
1. Volatility Risk Premium (VRP > 0)
2. Term structure in contango
3. Optimal contract selection based on annualized yield
4. Automatic rolling (both tactical and natural at DTE=5)
"""
import asyncio
import datetime
from typing import Optional, Dict, Any, List
import pandas as pd
import numpy as np
import yfinance as yf

from ib_async import Future
from obj.base_strategy import BaseStrategy, PARAMS as BASE_PARAMS
from core.log_manager import add_log

# Strategy-specific parameters
PARAMS = {
    **BASE_PARAMS,
    "universe": "VXM",  # VIX futures root symbol
    "target_weight": 0.07,
    "min_weight": 0.04,
    "max_weight": 0.10,
    "vix_threshold": 16.5,  # Minimum VIX level to consider shorting
    "min_future_price": 16.0,  # Don't short futures below this price
    "roll_dte": 5,  # Days to expiry to trigger natural roll
    "vrp_lookback_days": 120,  # Days of historical data for VRP calculation
    "vrp_window": 21,  # Rolling window for realized vol calculation
}


class ShortVixStrategy(BaseStrategy):
    """
    Short VIX futures strategy with term structure analysis and tactical rolling.
    """

    def __init__(self, client_id: int, strategy_manager, params: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(client_id=client_id, strategy_manager=strategy_manager, params=params, **kwargs)
        
        # Strategy-specific attributes
        self.instrument_symbol = self.params.get("universe", "VXM")
        self.target_weight = self.params.get("target_weight", 0.07)
        self.min_weight = self.params.get("min_weight", 0.04)
        self.max_weight = self.params.get("max_weight", 0.10)
        self.vix_threshold = self.params.get("vix_threshold", 16.5)
        self.min_future_price = self.params.get("min_future_price", 16.0)
        self.roll_dte = self.params.get("roll_dte", 5)
        self.vrp_lookback_days = self.params.get("vrp_lookback_days", 120)
        self.vrp_window = self.params.get("vrp_window", 21)
        
        # Market data
        self.term_structure: Optional[pd.DataFrame] = None
        self.vrp_df: Optional[pd.DataFrame] = None
        self.volatility_risk_premium: float = 0.0
        self.is_contango: bool = False
        
        # Position tracking
        self.invested_contract: Optional[Future] = None
        self.current_weight: float = 0.0
        self.equity: float = 0.0

    async def initialize_strategy(self):
        """Initialize VIX data and term structure analysis"""
        add_log("Initializing Short VIX Futures Strategy...", self.symbol)
        
        # Request delayed market data (type 3 = delayed, type 4 = delayed-frozen)
        self.ib.reqMarketDataType(3)  # Use delayed market data
        add_log("Requesting delayed market data (type 3)", self.symbol)
        
        # Update account and position info
        await self.update_investment_status()
        await self.update_invested_contract()
        
        # Download VRP data
        self.vrp_df = await self.download_vix_and_spy_data()
        if self.vrp_df is not None and not self.vrp_df.empty:
            self.volatility_risk_premium = self.vrp_df['VRP'].iloc[-1]
            add_log(f"Current VRP: {self.volatility_risk_premium:.2f}", self.symbol)
        
        # Get term structure
        self.term_structure = await self.get_term_structure()
        if self.term_structure is not None and not self.term_structure.empty:
            self.is_contango = self.check_contango()
            add_log(f"Term structure in contango: {self.is_contango}", self.symbol)

    async def run_strategy(self):
        """Main strategy execution loop"""
        add_log("Starting Short VIX Strategy execution", self.symbol)
        
        # Initial check and trade
        await self.check_conditions_and_trade()
        
        # Main loop: check conditions periodically
        while self.is_running:
            await asyncio.sleep(300)  # Check every 5 minutes
            
            try:
                # Refresh data
                await self.update_investment_status()
                await self.update_invested_contract()
                self.term_structure = await self.get_term_structure()
                
                # Check trading conditions
                await self.check_conditions_and_trade()
                
            except Exception as e:
                add_log(f"Error in strategy loop: {e}", self.symbol, "ERROR")

    async def check_conditions_and_trade(self):
        """Check trading conditions and execute trades"""
        try:
            # Get optimal contract to short
            optimal_contract = await self.choose_future_to_short()
            if optimal_contract is None:
                add_log("No suitable contract found to short", self.symbol, "WARNING")
                return
            
            # If not invested, enter position if VRP is positive
            if not self.invested_contract:
                if self.volatility_risk_premium > 0:
                    await self.short_future(optimal_contract)
                else:
                    add_log(f"VRP negative ({self.volatility_risk_premium:.2f}), not entering", self.symbol)
            else:
                # Position management when invested
                current_contract = self.invested_contract
                
                # Check for tactical roll (better yield available)
                if current_contract.localSymbol != optimal_contract.localSymbol:
                    add_log(f"Tactical roll opportunity: {current_contract.localSymbol} -> {optimal_contract.localSymbol}", self.symbol)
                    await self.roll_future(current_contract, optimal_contract)
                
                # Check for natural roll (approaching expiry)
                dte = await self.get_dte(current_contract)
                if dte <= self.roll_dte:
                    next_contract = await self.get_next_contract(current_contract)
                    if next_contract:
                        add_log(f"Natural roll at DTE={dte}: {current_contract.localSymbol} -> {next_contract.localSymbol}", self.symbol)
                        await self.roll_future(current_contract, next_contract)
                
                # Check if rebalancing is needed
                if self.current_weight < self.min_weight or self.current_weight > self.max_weight:
                    await self.rebalance_position(current_contract)
                    
        except Exception as e:
            add_log(f"Error in check_conditions_and_trade: {e}", self.symbol, "ERROR")

    async def download_vix_and_spy_data(self) -> pd.DataFrame:
        """Fetch historical data from Yahoo Finance and calculate VRP"""
        try:
            end_date = datetime.date.today()
            start_date = end_date - datetime.timedelta(days=self.vrp_lookback_days)
            
            # Download SPX data
            spx_df = yf.download("^GSPC", start=start_date, end=end_date, progress=False)
            # Flatten MultiIndex columns if present
            if isinstance(spx_df.columns, pd.MultiIndex):
                spx_df.columns = spx_df.columns.get_level_values(0)
            
            spx_df['Return'] = (spx_df['Close'] - spx_df['Close'].shift(1)) / spx_df['Close'].shift(1)
            spx_df['Realised Volatility'] = spx_df['Return'].rolling(self.vrp_window).std() * np.sqrt(252) * 100
            
            # Download VIX data
            vix_df = yf.download("^VIX", start=start_date, end=end_date, progress=False)
            # Flatten MultiIndex columns if present
            if isinstance(vix_df.columns, pd.MultiIndex):
                vix_df.columns = vix_df.columns.get_level_values(0)
            
            vix_df['VIX'] = vix_df['Close']
            
            # Merge and calculate VRP
            vrp_df = spx_df[['Close', 'Realised Volatility']].merge(
                vix_df[['VIX']], left_index=True, right_index=True, how='inner'
            )
            vrp_df['VRP'] = vrp_df['VIX'].shift(self.vrp_window) - vrp_df['Realised Volatility']
            
            add_log(f"VRP data loaded: {len(vrp_df)} rows", self.symbol)
            return vrp_df
            
        except Exception as e:
            add_log(f"Error downloading VIX/SPY data: {e}", self.symbol, "ERROR")
            return pd.DataFrame()

    async def get_vix_spot_level(self) -> float:
        """Get current VIX index spot level from IB or fallback to yfinance"""
        try:
            # Try to get VIX from IB
            from ib_async import Index
            vix_index = Index('VIX', 'CBOE')
            qualified = await self.ib.qualifyContractsAsync(vix_index)
            
            if qualified:
                self.ib.reqMarketDataType(3)  # Delayed data
                ticker = self.ib.reqMktData(qualified[0], "", False, False)
                await asyncio.sleep(1)
                
                if ticker.last and ticker.last > 0:
                    vix_spot = ticker.last
                elif ticker.close and ticker.close > 0:
                    vix_spot = ticker.close
                else:
                    vix_spot = 0.0
                
                self.ib.cancelMktData(qualified[0])
                
                if vix_spot > 0:
                    add_log(f"VIX spot level (IB): {vix_spot:.2f}", self.symbol)
                    return float(vix_spot)
            
            # Fallback to yfinance
            vix_data = yf.download("^VIX", period="1d", progress=False)
            if isinstance(vix_data.columns, pd.MultiIndex):
                vix_data.columns = vix_data.columns.get_level_values(0)
            
            if not vix_data.empty and 'Close' in vix_data.columns:
                vix_spot = float(vix_data['Close'].iloc[-1])
                add_log(f"VIX spot level (yfinance): {vix_spot:.2f}", self.symbol)
                return vix_spot
            
            add_log("Could not fetch VIX spot level", self.symbol, "WARNING")
            return 0.0
            
        except Exception as e:
            add_log(f"Error fetching VIX spot: {e}", self.symbol, "WARNING")
            return 0.0

    async def get_term_structure(self) -> pd.DataFrame:
        """Build VIX futures term structure"""
        try:
            # Ensure delayed market data is requested
            self.ib.reqMarketDataType(3)
            
            # Get current VIX spot level
            vix_spot = await self.get_vix_spot_level()
            
            contracts = []
            today = datetime.date.today()
            
            # Get next 8 months of VIX futures starting from current month
            for i in range(8):
                future_date = today + datetime.timedelta(days=i*30)  # Approximate month increments
                expiry_str = f"{future_date.year}{future_date.month:02}"
                
                contract = Future(symbol=self.instrument_symbol, lastTradeDateOrContractMonth=expiry_str, exchange="CFE")
                contracts.append(contract)
            
            # Qualify contracts
            qualified = await self.ib.qualifyContractsAsync(*contracts)
            
            # Request market data for each contract
            term_structure_data = []
            for contract in qualified:
                try:
                    ticker = self.ib.reqMktData(contract, "", False, False)
                    await asyncio.sleep(0.5)
                    
                    if ticker.last and ticker.last > 0:
                        last_price = ticker.last
                    elif ticker.bid and ticker.bid > 0:
                        last_price = ticker.bid
                    else:
                        continue
                    
                    # Calculate days to expiry
                    expiry_date = datetime.datetime.strptime(contract.lastTradeDateOrContractMonth, '%Y%m%d')
                    dte = (expiry_date.date() - today).days
                    
                    # Calculate annualized yield for SHORT position
                    # When shorting in contango, we profit as futures converge down to spot
                    # Yield = (Future Price - Spot VIX) / Future Price * (365 / DTE)
                    if dte > 0 and last_price > 0 and vix_spot > 0:
                        premium_over_spot = last_price - vix_spot
                        return_to_expiry = premium_over_spot / last_price  # % gain for short
                        annualized_yield = return_to_expiry * (365.0 / dte) * 100  # Annualized %
                    else:
                        annualized_yield = 0
                    
                    term_structure_data.append({
                        'Contract': contract,
                        'LocalSymbol': contract.localSymbol,
                        'Expiry': contract.lastTradeDateOrContractMonth,
                        'DTE': dte,
                        'LastPrice': last_price,
                        'VIX_Spot': vix_spot,
                        'Premium': last_price - vix_spot,
                        'Contango_pct': ((last_price - vix_spot) / vix_spot * 100) if vix_spot > 0 else 0,
                        'AnnualizedYield_pct': annualized_yield,
                        'VRP': self.volatility_risk_premium,
                        'Multiplier': int(contract.multiplier) if contract.multiplier else 1000
                    })
                    
                    self.ib.cancelMktData(contract)
                    
                except Exception as e:
                    add_log(f"Error fetching data for {contract.localSymbol}: {e}", self.symbol, "WARNING")
            
            df = pd.DataFrame(term_structure_data)
            df.to_csv("term_structure.csv", index=False)
            if not df.empty:
                df = df.sort_values('DTE')
                add_log(f"Term structure loaded: {len(df)} contracts", self.symbol)
            
            return df
            
        except Exception as e:
            add_log(f"Error building term structure: {e}", self.symbol, "ERROR")
            return pd.DataFrame()

    def check_contango(self) -> bool:
        """Check if term structure is in contango"""
        if self.term_structure is None or self.term_structure.empty:
            return False
        return self.term_structure['LastPrice'].is_monotonic_increasing

    async def choose_future_to_short(self) -> Optional[Future]:
        """Choose the optimal VIX future to short based on yield and criteria"""
        if self.term_structure is None or self.term_structure.empty:
            return None
        
        # Filter: price > minimum threshold
        filtered = self.term_structure[self.term_structure['LastPrice'] > self.min_future_price]
        
        if filtered.empty:
            return None
        
        # Sort by annualized yield (highest positive = best for shorting in contango)
        sorted_futures = filtered.sort_values(by='AnnualizedYield_pct', ascending=False)
        
        # Return the contract with highest yield
        chosen = sorted_futures.iloc[0]
        add_log(f"Selected {chosen['LocalSymbol']}: DTE={chosen['DTE']}, Price={chosen['LastPrice']:.2f}, Yield={chosen['AnnualizedYield_pct']:.1f}%", self.symbol)
        return chosen['Contract']

    async def short_future(self, contract: Future):
        """Enter short position in VIX future"""
        try:
            # Calculate position size
            allocated_amount = self.equity * self.target_weight
            
            # Get current cash
            account_summary = await self.ib.accountSummaryAsync()
            cash = sum(float(entry.value) for entry in account_summary if entry.tag == "AvailableFunds")
            
            if cash < allocated_amount:
                add_log(f"Insufficient cash ({cash:.2f}) for allocation ({allocated_amount:.2f})", self.symbol, "WARNING")
                return
            
            # Get contract details
            contract_price = await self.get_contract_price(contract)
            multiplier = int(contract.multiplier) if contract.multiplier else 1000
            
            # Calculate number of contracts
            quantity = self.calculate_number_of_contracts(allocated_amount, contract_price, multiplier)
            
            if quantity > 0:
                add_log(f"Shorting {quantity} {contract.localSymbol} @ {contract_price:.2f}", self.symbol)
                # Use negative quantity for short
                await self.place_order(contract, quantity=-quantity, order_type='MKT')
            else:
                add_log(f"Calculated quantity is 0 for allocation {allocated_amount:.2f}", self.symbol, "WARNING")
                
        except Exception as e:
            add_log(f"Error shorting future: {e}", self.symbol, "ERROR")

    async def roll_future(self, current_contract: Future, new_contract: Future):
        """Roll from current contract to new contract"""
        try:
            # Verify we're rolling forward in time
            current_dte = await self.get_dte(current_contract)
            new_dte = await self.get_dte(new_contract)
            
            if new_dte <= current_dte:
                add_log("Not allowed to roll future down the curve", self.symbol, "WARNING")
                return
            
            # Get current position size
            portfolio = self.ib.portfolio()
            current_position = None
            for pos in portfolio:
                if pos.contract.localSymbol == current_contract.localSymbol:
                    current_position = pos
                    break
            
            if not current_position:
                add_log(f"No position found for {current_contract.localSymbol}", self.symbol, "WARNING")
                return
            
            quantity = abs(int(current_position.position))
            
            # Close current position (buy to cover short)
            add_log(f"Rolling: Closing {current_contract.localSymbol}", self.symbol)
            await self.place_order(current_contract, quantity=quantity, order_type='MKT')
            
            # Open new position (short new contract)
            await asyncio.sleep(2)  # Brief delay between legs
            add_log(f"Rolling: Opening {new_contract.localSymbol}", self.symbol)
            await self.place_order(new_contract, quantity=-quantity, order_type='MKT')
            
        except Exception as e:
            add_log(f"Error rolling future: {e}", self.symbol, "ERROR")

    async def rebalance_position(self, contract: Future):
        """Rebalance position to target weight"""
        try:
            allocated_amount = self.equity * self.target_weight
            contract_price = await self.get_contract_price(contract)
            multiplier = int(contract.multiplier) if contract.multiplier else 1000
            
            target_quantity = self.calculate_number_of_contracts(allocated_amount, contract_price, multiplier)
            
            # Get current position
            portfolio = self.ib.portfolio()
            current_quantity = 0
            for pos in portfolio:
                if pos.contract.localSymbol == contract.localSymbol:
                    current_quantity = abs(int(pos.position))
                    break
            
            rebal_amount = target_quantity - current_quantity
            
            if abs(rebal_amount) > 0:
                add_log(f"Rebalancing: adjusting position by {rebal_amount} contracts", self.symbol)
                # Negative for increasing short, positive for decreasing short
                await self.place_order(contract, quantity=-rebal_amount, order_type='MKT')
                
        except Exception as e:
            add_log(f"Error rebalancing: {e}", self.symbol, "ERROR")

    def calculate_number_of_contracts(self, allocated_amount: float, contract_price: float, contract_size: float) -> int:
        """Calculate number of futures contracts based on allocated amount"""
        if contract_price <= 0 or contract_size <= 0:
            return 0
        total_value = contract_price * contract_size
        return int(allocated_amount // total_value)

    async def get_contract_price(self, contract: Future) -> float:
        """Get current market price for a contract"""
        try:
            # Ensure delayed market data
            self.ib.reqMarketDataType(3)
            
            ticker = self.ib.reqMktData(contract, "", False, False)
            await asyncio.sleep(1)
            
            if ticker.last and ticker.last > 0:
                price = ticker.last
            elif ticker.bid and ticker.bid > 0:
                price = ticker.bid
            else:
                price = 0.0
            
            self.ib.cancelMktData(contract)
            return float(price)
            
        except Exception as e:
            add_log(f"Error getting contract price: {e}", self.symbol, "ERROR")
            return 0.0

    async def get_dte(self, contract: Future) -> int:
        """Get days to expiry for a contract"""
        try:
            today = datetime.datetime.now()
            expiration_date = datetime.datetime.strptime(contract.lastTradeDateOrContractMonth, '%Y%m%d')
            dte = (expiration_date - today).days
            return dte
        except Exception as e:
            add_log(f"Error calculating DTE: {e}", self.symbol, "ERROR")
            return 0

    async def get_next_contract(self, current_contract: Future) -> Optional[Future]:
        """Get the next month's contract"""
        try:
            await self.ib.qualifyContractsAsync(current_contract)
            
            # Parse current expiry
            expiration = current_contract.lastTradeDateOrContractMonth
            year, month = int(expiration[:4]), int(expiration[4:6])
            
            # Calculate next month
            next_month = month + 1
            next_year = year
            if next_month > 12:
                next_month = 1
                next_year += 1
            
            next_month_str = f"{next_year}{next_month:02}"
            
            # Create and qualify next contract
            next_contract = Future(
                symbol=current_contract.symbol,
                lastTradeDateOrContractMonth=next_month_str,
                exchange=current_contract.exchange
            )
            qualified = await self.ib.qualifyContractsAsync(next_contract)
            
            return qualified[0] if qualified else None
            
        except Exception as e:
            add_log(f"Error getting next contract: {e}", self.symbol, "ERROR")
            return None

    async def update_investment_status(self):
        """Update equity and current weight"""
        try:
            account_summary = await self.ib.accountSummaryAsync()
            self.equity = sum(float(entry.value) for entry in account_summary if entry.tag == "EquityWithLoanValue")
            
            # Calculate current weight
            portfolio = self.ib.portfolio()
            market_value = sum(
                abs(pos.marketValue) for pos in portfolio
                if pos.contract.symbol == self.instrument_symbol
            )
            
            self.current_weight = (market_value / self.equity) if self.equity > 0 else 0.0
            
        except Exception as e:
            add_log(f"Error updating investment status: {e}", self.symbol, "ERROR")

    async def update_invested_contract(self):
        """Update the currently invested contract"""
        try:
            portfolio = self.ib.portfolio()
            for pos in portfolio:
                if pos.contract.symbol == self.instrument_symbol and pos.position != 0:
                    self.invested_contract = pos.contract
                    await self.ib.qualifyContractsAsync(self.invested_contract)
                    return
            
            self.invested_contract = None
            
        except Exception as e:
            add_log(f"Error updating invested contract: {e}", self.symbol, "ERROR")

    def on_fill(self, trade, fill):
        """Handle order fill events"""
        super().on_fill(trade, fill)
        add_log(f"Fill: {fill.execution.side} {fill.execution.shares} @ {fill.execution.price:.2f}", self.symbol)

    def on_status_change(self, trade):
        """Handle order status changes"""
        super().on_status_change(trade)
        status = trade.orderStatus.status
        add_log(f"Order status: {status}", self.symbol)
