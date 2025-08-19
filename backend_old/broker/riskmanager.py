# IB-Multi-Strategy-ATS/broker/riskmanager.py
from ib_async import *
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import asyncio

from data_and_research import ac

class RiskManager:
    def __init__(self, ib_client: IB, portfolio_manager = None, arctic = None):
        self.ib = ib_client
        self.arctic = arctic if arctic else ac
        lib = self.arctic.get_library('univ')
        self.uni = lib.read('us_equities').data
        if portfolio_manager:
            self.portfolio_manager = portfolio_manager
            self.fx_cache = self.portfolio_manager.fx_cache
            self.base = self.portfolio_manager.base
            self.account_id = self.portfolio_manager.account_id

    def pre_trade_check(self, contract, order):
        return self.ib.whatIfOrder(contract,order)
    
    def get_portfolio_data(self):
        portfolio = pd.DataFrame(self.ib.portfolio())
        portfolio['symbol'] = portfolio['contract'].apply(lambda x: x.symbol)
        portfolio['asset_class'] = portfolio['contract'].apply(lambda x: type(x))
        return portfolio

    async def fetch_price_async(self, contract):
        self.ib.qualifyContracts(contract)
        [ticker] = await self.ib.reqTickersAsync(contract)
        price = ticker.marketPrice() if ticker.marketPrice() is not None else ticker.close
        return contract.symbol, price

    async def get_short_put_exposure_async(self, exclude_ETFs=True):
        ''' Function that retrieves short put exposure data.
        Param: exclude_ETFs: If True, ETFs are excluded from the analysis.
        
        Output: DataFrame with short put exposure data and a dictionary with total exposure, exposure at risk and expected dollar return.
        '''
        self.portfolio = self.get_portfolio_data()

        put_option_rows = [row for _, row in self.portfolio.iterrows() if row['contract'].right == 'P' and np.sign(row['position']) == -1]
        short_put_df = pd.DataFrame(put_option_rows)

        def get_sector(symbol, source='yf' or 'universe'):
            if source == 'yf':
                info = yf.Ticker(symbol).info
                try:
                    sector = info['sector']
                    return sector
                except KeyError:
                    return None
            elif source == 'universe':
                if symbol in self.uni['Symbol'].values:
                    sector = self.uni.loc[self.uni['Symbol'] == symbol, 'Sector'].values[0]
                    return sector
                else:
                    return None

        short_put_df['sector'] = short_put_df['symbol'].apply(lambda x: get_sector(x, source='universe'))

        if exclude_ETFs:
            short_put_df = short_put_df[short_put_df['sector'].notna()].reset_index(drop=True)

        contracts = [Stock(symbol, 'SMART', 'USD') for symbol in short_put_df['symbol'].unique()]
        tasks = [self.fetch_price_async(con) for con in contracts]
        prices = await asyncio.gather(*tasks)

        prices_dict = dict(prices)
        short_put_df['stockprice'] = short_put_df['symbol'].map(prices_dict)
        short_put_df['strike'] = short_put_df['contract'].apply(lambda x: x.strike)
        short_put_df['exposure_level1'] = abs(short_put_df['position']) * short_put_df['strike'] * 100
        short_put_df['exposure_level2'] = np.where(short_put_df['strike'] >= short_put_df['stockprice'] * 0.95, short_put_df['exposure_level1'], 0)
        short_put_df['expected_dollar_return'] = np.where(short_put_df['strike'] <= short_put_df['stockprice'], abs(short_put_df['marketValue']), short_put_df['marketValue'] + (short_put_df['averageCost']))

        self.short_put_df = short_put_df[['contract', 'symbol', 'sector', 'strike', 'stockprice', 'position', 'marketValue', 'averageCost', 'exposure_level1', 'exposure_level2', 'expected_dollar_return']]
        return self.short_put_df, {'Total Exposure': self.short_put_df.exposure_level1.sum(), 'Total Exposure at Risk': self.short_put_df.exposure_level2.sum(), 'Total Expected Dollar Return': self.short_put_df.expected_dollar_return.sum()}

    def get_short_put_exposure(self,exclude_ETFs=True):
        ''' Function that retrieves short put exposure data.
        Param: exclude_ETFs: If True, ETFs are excluded from the analysis.
        
        Output: DataFrame with short put exposure data and a dictionary with total exposure, exposure at risk and expected dollar return.'''

        self.portfolio = self.get_portfolio_data()

        put_option_rows = [row for _,row in self.portfolio.iterrows() if row['contract'].right == 'P' and np.sign(row['position']) == -1]
        short_put_df = pd.DataFrame(put_option_rows)

        def get_sector(symbol, source='yf' or 'universe'):
            if source == 'yf':
                info = yf.Ticker(symbol).info
                try:
                    sector = info['sector']
                    return sector
                except KeyError:
                    return None
            elif source == 'universe':
                # Check if the symbol exists in the DataFrame
                if symbol in self.uni['Symbol'].values:
                    sector = self.uni.loc[self.uni['Symbol'] == symbol, 'Sector'].values[0]
                    return sector
                else:
                    return None
        
        short_put_df['sector'] = short_put_df['symbol'].apply(lambda x: get_sector(x,source='universe'))
        
        if exclude_ETFs:
            short_put_df = short_put_df[short_put_df['sector'].notna()].reset_index(drop=True)
        
        prices = {}
        for symbol in short_put_df['symbol'].unique():
            # Create Stock contract
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            [ticker] = self.ib.reqTickers(contract)

            price = ticker.marketPrice() if ticker.marketPrice() is not None else ticker.close
            prices[symbol] = price
            
            self.ib.sleep(0.1)

        # Map prices to the stocks_only dataframe
        short_put_df['stockprice'] = short_put_df['symbol'].map(prices)
        short_put_df['strike'] = short_put_df['contract'].apply(lambda x: x.strike)
        short_put_df['exposure_level1'] = abs(short_put_df['position']) * short_put_df['strike'] * 100
        short_put_df['exposure_level2'] = np.where(short_put_df['strike'] >= short_put_df['stockprice']*0.95, short_put_df['exposure_level1'], 0)
        short_put_df['expected_dollar_return'] = np.where(short_put_df['strike'] <= short_put_df['stockprice'], abs(short_put_df['marketValue']), short_put_df['marketValue'] + (short_put_df['averageCost']))

        self.short_put_df =short_put_df[['contract','symbol','sector','strike','stockprice','position','marketValue','averageCost','exposure_level1','exposure_level2','expected_dollar_return']]
        return self.short_put_df, {'Total Exposure': self.short_put_df.exposure_level1.sum(), 'Total Exposure at Risk': self.short_put_df.exposure_level2.sum(), 'Total Expected Dollar Return': self.short_put_df.expected_dollar_return.sum()}

    def calculate_portfolio_var(self, confidence_level=0.95, time_horizon=1):
        # Implement Value at Risk calculation
        pass

    def calculate_position_correlations(self):
        # Implement correlation calculation between positions
        pass

    def analyze_sector_exposure(self):
        portfolio = self.get_portfolio_data()
        sector_exposure = {}
        total_value = 0

        for _, row in portfolio[portfolio['asset_class'] == Stock].iterrows():
            contract = row['contract']
            contract = Stock(contract.symbol, 'SMART', contract.currency)
            print(contract)
            sector = self.get_sector_from_contract(contract)
            position_value = row['position'] * row['marketPrice']
            
            if sector not in sector_exposure:
                sector_exposure[sector] = 0
            sector_exposure[sector] += position_value
            total_value += position_value

        # Calculate percentage exposure for each sector
        for sector in sector_exposure:
            sector_exposure[sector] = (sector_exposure[sector] / total_value) * 100

        # Sort sectors by exposure percentage in descending order
        sorted_exposure = sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True)

        # Create a DataFrame for better visualization
        exposure_df = pd.DataFrame(sorted_exposure, columns=['Sector', 'Exposure (%)'])
        exposure_df.set_index('Sector', inplace=True)

        return exposure_df
            
    def get_sector_from_contract(self,contract):
        ''' Function that tries to retrieve sector information. Starts with ArcticDB, then tries to retrieve data from IB and Yahoo Finance as a fallback.'''
        def get_sector_from_uni(contract):
            try:
                sector = self.uni[self.uni.Symbol==contract.symbol].Sector.values[0]
                return sector
            except:
                return None
        
        def get_isin_from_contract(contract):
            import xml.etree.ElementTree as ET
            fundamentals = self.ib.reqFundamentalData(contract, reportType='ReportSnapshot')
            root = ET.fromstring(fundamentals)
            for elem in root.iter():
                prev_elem = None
                for elem in root.iter():
                    if prev_elem is not None:
                        if prev_elem.text == contract.symbol:
                            isin = elem.text
                            return isin
                    prev_elem = elem

        def get_sector_from_yf(contract):
            try:
                isin = get_isin_from_contract(contract)
                ticker =yf.utils.get_ticker_by_isin(isin)
                sector = yf.Ticker(ticker).info['sector']
                return sector
            except:
                try:
                    sector = yf.Ticker(contract.symbol).info['category']
                except:
                    ticker =yf.utils.get_ticker_by_isin(isin)
                    sector = yf.Ticker(contract.symbol).info['category']
                return sector
        
        sector = ''
        sector = get_sector_from_uni(contract) 
        if not sector:
            sector = get_sector_from_yf(contract)
        return sector

    def calculate_beta(self):
        # Calculate portfolio beta
        pass

    def stress_test_portfolio(self, scenarios):
        # Implement stress testing for various market scenarios
        pass

    def calculate_sharpe_ratio(self):
        # Calculate Sharpe ratio for the portfolio
        pass

    def monitor_position_limits(self):
        # Check if any positions exceed predefined limits
        pass

    def analyze_liquidity_risk(self):
        # Analyze the liquidity risk of the portfolio
        pass

    def generate_risk_report(self):
        # Generate a comprehensive risk report
        pass

    def get_clean_contract(self, contract):
        if isinstance(contract, Stock):
            contract = type(contract)(symbol=contract.symbol, exchange='SMART', currency=contract.currency)
        return contract
    

    def get_historical_data(self, contract, duration='1 Y', bar_size='1 day'):
        if isinstance(contract, Stock):
            contract = type(contract)(symbol=contract.symbol, exchange='SMART', currency=contract.currency)
            bars = self.ib.reqHistoricalData(contract, endDateTime='', durationStr=duration,
                                        barSizeSetting=bar_size, whatToShow='ADJUSTED_LAST', useRTH=True)
        if isinstance(contract, Option):
            contract = type(contract)(symbol=contract.symbol, exchange='SMART', currency=contract.currency)
            bars = self.ib.reqHistoricalData(contract, endDateTime='', durationStr=duration,
                                    barSizeSetting=bar_size, whatToShow='ADJUSTED_LAST', useRTH=True)
        return pd.DataFrame(bars)

    def calculate_position_correlations(self):
        spy = Stock('SPY', 'SMART', 'USD')
        tlt = Stock('TLT', 'SMART', 'USD')

        spy_data = self.get_historical_data(spy)
        tlt_data = self.get_historical_data(tlt)

        spy_returns = spy_data['close'].pct_change().dropna()
        tlt_returns = tlt_data['close'].pct_change().dropna()

        correlations = {}

        # Get the portfolio positions
        portfolio = pd.DataFrame(self.ib.portfolio())
        portfolio['symbol'] = portfolio['contract'].apply(lambda x: x.symbol)

        for _, row in portfolio.iterrows():
            try:
                contract = row['contract']
                hist_data = self.get_historical_data(contract)
                returns = hist_data['close'].pct_change().dropna()
                
                aligned_data = pd.concat([returns, spy_returns, tlt_returns], axis=1, join='inner')
                aligned_data.columns = ['asset', 'SPY', 'TLT']
                
                corr_spy = aligned_data['asset'].corr(aligned_data['SPY'])
                corr_tlt = aligned_data['asset'].corr(aligned_data['TLT'])
                
                position_sign = np.sign(row['position'])
                correlations[row['symbol']] = {
                    'SPY': corr_spy * position_sign,
                    'TLT': corr_tlt * position_sign}
            except Exception as e:
                print(f"Error processing {row['symbol']}: {str(e)}")
        if not correlations:
            print("No correlations were calculated. Check the contracts and data availability.")
            return None
        else:
            corr_df = pd.DataFrame(correlations).T
            corr_df.columns = ['Equity-like (SPY)', 'Bond-like (TLT)']
            corr_df['Character'] = np.where(corr_df['Equity-like (SPY)'].abs() > corr_df['Bond-like (TLT)'].abs(), 'Equity-like', 'Bond-like')
            return corr_df

    def analyze_portfolio_character(self):
        self.corr_df = self.calculate_position_correlations()
        portfolio = pd.DataFrame(self.ib.portfolio())
        portfolio['symbol'] = portfolio['contract'].apply(lambda x: x.symbol)
        
        portfolio_analysis = portfolio.merge(self.corr_df, left_on='symbol', right_index=True, how='left')
        total_market_value = portfolio_analysis['marketValue'].abs().sum()
        portfolio_analysis['% of Portfolio'] = portfolio_analysis['marketValue'].abs() / total_market_value * 100
        
        concentration = portfolio_analysis.groupby('Character')['% of Portfolio'].sum()
        print(f"Portfolio concentration by asset class: {concentration}")
        print(portfolio_analysis)
        return portfolio_analysis, concentration

    def visualize_portfolio_character(self):
        portfolio_analysis, concentration = self.analyze_portfolio_character()

        import matplotlib.pyplot as plt

        plt.figure(figsize=(12, 6))
        plt.scatter(self.corr_df['Equity-like (SPY)'], self.corr_df['Bond-like (TLT)'], s=portfolio_analysis['% of Portfolio']*20, alpha=0.6)
        for idx, row in self.corr_df.iterrows():
            plt.annotate(idx, (row['Equity-like (SPY)'], row['Bond-like (TLT)']))
        plt.xlabel('Correlation with SPY (Equity-like)')
        plt.ylabel('Correlation with TLT (Bond-like)')
        plt.title('Portfolio Assets: Equity-like vs Bond-like Characteristics')
        plt.axhline(y=0, color='r', linestyle='--', alpha=0.3)
        plt.axvline(x=0, color='r', linestyle='--', alpha=0.3)
        plt.grid(True, alpha=0.3)
        plt.show()

        return plt

if __name__ == "__main__":
    ib_client = IB()
    ib_client.connect('127.0.0.1', 7497, clientId=2)
    risk_manager = RiskManager(ib_client)
    risk_manager.visualize_portfolio_character()