"""
Simplified async historical data fetcher for Interactive Brokers.
Handles pagination and respects rate limits for maximum speed without timeouts.
"""
import asyncio
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from ib_async import IB, Contract, util


class RateLimiter:
    """Rate limiter for IB historical data requests.
    
    IB Rules:
    - Max 6 identical requests per 2 seconds
    - Max 60 requests per 10 minutes
    - 15 second cooldown for identical requests
    """
    
    def __init__(self):
        self.requests_2s = deque()
        self.requests_10m = deque()
        self.last_request_time = 0
        
    async def wait(self):
        """Wait if necessary to respect rate limits."""
        now = time.time()
        
        # Clean old timestamps
        while self.requests_2s and now - self.requests_2s[0] > 2:
            self.requests_2s.popleft()
        while self.requests_10m and now - self.requests_10m[0] > 600:
            self.requests_10m.popleft()
        
        # Check 2-second limit (max 5 to be safe)
        if len(self.requests_2s) >= 5:
            wait_time = 2.1 - (now - self.requests_2s[0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                now = time.time()
        
        # Check 10-minute limit (max 58 to be safe)
        if len(self.requests_10m) >= 58:
            wait_time = 600.1 - (now - self.requests_10m[0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                now = time.time()
        
        # Minimum spacing between requests (0.4 seconds for safety)
        if now - self.last_request_time < 0.4:
            await asyncio.sleep(0.4 - (now - self.last_request_time))
            now = time.time()
        
        # Record this request
        self.requests_2s.append(now)
        self.requests_10m.append(now)
        self.last_request_time = now


async def fetch_historical_data(
    ib: IB,
    contract: Contract,
    end_date: str = "",
    duration: str = "1 Y",
    bar_size: str = "1 min",
    what_to_show: str = "TRADES",
    use_rth: bool = True,
    chunk_size: str = "10 D",
    max_periods: Optional[int] = None
) -> pd.DataFrame:
    """
    Fetch historical data with automatic pagination.
    
    Args:
        ib: Connected IB instance
        contract: Qualified contract
        end_date: End date for data (empty string = now)
        duration: Total duration to fetch (e.g., "1 Y", "6 M", "30 D")
        bar_size: Bar size (e.g., "1 min", "5 mins", "1 hour")
        what_to_show: Data type ("TRADES", "MIDPOINT", "BID", "ASK")
        use_rth: Regular trading hours only
        chunk_size: Size of each request chunk (e.g., "10 D", "1 W")
        max_periods: Optional limit on number of chunks to fetch
        
    Returns:
        DataFrame with all historical data
    """
    rate_limiter = RateLimiter()
    all_bars = []
    
    # Parse duration to determine number of chunks needed
    chunk_days = _parse_duration_days(chunk_size)
    total_days = _parse_duration_days(duration)
    num_chunks = min((total_days // chunk_days) + 1, max_periods or 1000)
    
    # Start from end_date or now
    current_end = end_date or ""
    
    # Fetch chunks sequentially (most reliable for large datasets)
    for i in range(num_chunks):
        await rate_limiter.wait()
        
        try:
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime=current_end,
                durationStr=chunk_size,
                barSizeSetting=bar_size,
                whatToShow=what_to_show,
                useRTH=use_rth,
                formatDate=1,
                keepUpToDate=False,
                timeout=20  # Increase timeout for stability
            )
            
            if not bars:
                break  # No more data available
                
            all_bars.extend(bars)
            
            # Move end date to the earliest bar's date for next request
            earliest_bar = bars[0]
            current_end = earliest_bar.date.strftime("%Y%m%d %H:%M:%S")
            
            # Small delay between chunks for stability
            await asyncio.sleep(0.1)
            
        except Exception as e:
            print(f"Error fetching chunk {i+1}: {e}")
            break
    
    if not all_bars:
        return pd.DataFrame()
    
    # Convert to DataFrame and sort chronologically
    df = util.df(all_bars)
    df = df.sort_index()
    
    return df


async def fetch_bars_concurrent(
    ib: IB,
    contract: Contract,
    end_dates: list[str],
    duration: str = "10 D",
    bar_size: str = "1 min",
    what_to_show: str = "TRADES",
    use_rth: bool = True
) -> pd.DataFrame:
    """
    Fetch multiple date ranges concurrently for maximum speed.
    Use this when you know specific date ranges you want.
    
    Args:
        ib: Connected IB instance
        contract: Qualified contract
        end_dates: List of end dates to fetch
        duration: Duration for each request
        bar_size: Bar size
        what_to_show: Data type
        use_rth: Regular trading hours only
        
    Returns:
        Combined DataFrame
    """
    rate_limiter = RateLimiter()
    
    async def fetch_single(end_date: str):
        await rate_limiter.wait()
        try:
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime=end_date,
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow=what_to_show,
                useRTH=use_rth,
                formatDate=1,
                keepUpToDate=False,
                timeout=20
            )
            return bars
        except Exception as e:
            print(f"Error fetching {end_date}: {e}")
            return []
    
    # Limit concurrency to avoid overwhelming the API
    semaphore = asyncio.Semaphore(3)
    
    async def fetch_with_semaphore(end_date):
        async with semaphore:
            return await fetch_single(end_date)
    
    # Fetch all concurrently with controlled concurrency
    results = await asyncio.gather(*[fetch_with_semaphore(ed) for ed in end_dates])
    
    # Combine all bars
    all_bars = [bar for bars in results if bars for bar in bars]
    
    if not all_bars:
        return pd.DataFrame()
    
    df = util.df(all_bars)
    return df.sort_index()


def _parse_duration_days(duration: str) -> int:
    """Convert duration string to approximate days."""
    parts = duration.split()
    if len(parts) != 2:
        return 1
    
    value = int(parts[0])
    unit = parts[1].upper()
    
    if unit in ['D', 'DAY', 'DAYS']:
        return value
    elif unit in ['W', 'WEEK', 'WEEKS']:
        return value * 7
    elif unit in ['M', 'MONTH', 'MONTHS']:
        return value * 30
    elif unit in ['Y', 'YEAR', 'YEARS']:
        return value * 365
    else:
        return value


# Simple usage example
async def example():
    """Example of how to use the fetcher."""
    ib = IB()
    await ib.connectAsync('127.0.0.1', 7497, clientId=1)
    
    try:
        from ib_async import Stock
        contract = Stock('AAPL', 'SMART', 'USD')
        await ib.qualifyContractsAsync(contract)
        
        # Fetch 1 month of 1-minute bars
        df = await fetch_historical_data(
            ib=ib,
            contract=contract,
            duration="1 M",
            bar_size="1 min",
            chunk_size="20 D"  # Fetch in 20-day chunks
        )
        
        print(f"Fetched {len(df)} bars")
        print(f"Date range: {df.index.min()} to {df.index.max()}")
        
        return df
        
    finally:
        ib.disconnect()


if __name__ == "__main__":
    # Run the example
    asyncio.run(example())