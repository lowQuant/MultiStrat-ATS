"""
Async historical downloader using pagination for Interactive Brokers via ib_async.
- Fetches 1-minute (or other) bars in chunks (e.g., 10 D) going backwards in time.
- Respects IB pacing rules with an async rate limiter.
- No ArcticDB writes; optional CSV saving via flag.

Examples:
  python backend/jobs/test_download.py --symbol TQQQ --bar-size "1 min" --chunk "10 D" --what TRADES --rth --save-csv tqqq_1min.csv
  python backend/jobs/test_download.py --symbol TSLA --bar-size "1 min" --chunk "10 D" --what MIDPOINT

Notes on IB pacing (for bars <= 30 secs):
- Avoid identical historical requests within 15 seconds.
- No 6 or more historical requests for the same (Contract, Exchange, TickType) in 2 seconds.
- No more than 60 historical requests within any 10 minute period.

We space requests and track recent request timestamps to stay below these limits.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import os
import time
from collections import deque
from typing import List, Optional

import pandas as pd
from ib_async import IB, Stock, util


class IBRatelimiter:
    """Async rate limiter to respect IB historical pacing limits.

    Constraints we enforce conservatively:
    - < 6 requests per rolling 2 seconds window (we cap at 5)
    - < 60 requests per rolling 10 minutes window (we cap at 59)
    """

    def __init__(self, max_per_2s: int = 5, window_2s: float = 2.0,
                 max_per_10m: int = 59, window_10m: float = 600.0) -> None:
        self.last_2s: deque[float] = deque()
        self.last_10m: deque[float] = deque()
        self.max_per_2s = max_per_2s
        self.window_2s = window_2s
        self.max_per_10m = max_per_10m
        self.window_10m = window_10m

    async def wait(self) -> None:
        """Wait until making another request is within pacing rules."""
        while True:
            now = time.monotonic()
            # Evict old timestamps
            while self.last_2s and now - self.last_2s[0] > self.window_2s:
                self.last_2s.popleft()
            while self.last_10m and now - self.last_10m[0] > self.window_10m:
                self.last_10m.popleft()

            ok_2s = len(self.last_2s) < self.max_per_2s
            ok_10m = len(self.last_10m) < self.max_per_10m

            if ok_2s and ok_10m:
                # Record this request time
                self.last_2s.append(now)
                self.last_10m.append(now)
                return

            # Compute the necessary wait time until within limits again
            wait_2s = self.window_2s - (now - self.last_2s[0]) if not ok_2s else 0.0
            wait_10m = self.window_10m - (now - self.last_10m[0]) if not ok_10m else 0.0
            wait_for = max(wait_2s, wait_10m, 0.1)
            await asyncio.sleep(wait_for)


async def fetch_historical_paginated(
    symbol: str = "TQQQ",
    bar_size: str = "1 min",
    chunk: str = "20 D",
    what: str = "TRADES",
    use_rth: bool = True,
    client_id: int = 9999,
    end: str = "",
    max_chunks: Optional[int] = 5,
) -> pd.DataFrame:
    """Simplified, robust async pagination using sequential requests.

    - Uses 20 D with RTH=True (~8k bars) to stay under 10k limit per request
    - Chains endDateTime backwards using earliest bar from prior chunk
    - Formats endDateTime as "YYYYMMDD HH:MM:SS US/Eastern" and steps back 1s to avoid identical requests
    - Adds a small delay between requests to prevent pacing timeouts
    """
    ib = IB()
    try:
        await ib.connectAsync('127.0.0.1', 7497, clientId=client_id)
        print("✅ Connected to Interactive Brokers")

        contract = Stock(symbol.upper(), 'SMART', 'USD')
        await ib.qualifyContractsAsync(contract)
        print("✅ Contract qualified")

        dt = end or ''  # '' means now
        pages = max_chunks or 5
        parts: List[list] = []

        for i in range(pages):
            print(f"   Fetching page {i+1}/{pages}, end: {dt or 'now'}")
            try:
                bars = await ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime=dt,
                    durationStr=chunk,
                    barSizeSetting=bar_size,
                    whatToShow=what,
                    useRTH=use_rth,
                    keepUpToDate=False,
                )
            except Exception as e:
                print(f"   ⚠️ Request failed: {e}. Retrying once after short backoff...")
                await asyncio.sleep(3.0)
                bars = await ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime=dt,
                    durationStr=chunk,
                    barSizeSetting=bar_size,
                    whatToShow=what,
                    useRTH=use_rth,
                    keepUpToDate=False,
                )

            if not bars:
                print("   No more data available")
                break

            parts.append(bars)

            # Determine next endDateTime from earliest bar; convert to US/Eastern and step back 1s
            earliest = getattr(bars[0], 'date', None)
            if earliest is None:
                print("   Earliest bar missing date; stopping")
                break
            ts = pd.to_datetime(earliest)
            if ts.tzinfo is None:
                # Assume current is UTC if tz-naive
                ts = ts.tz_localize('UTC')
            # Convert to US/Eastern and step back 1 second to avoid identical request
            ts_eastern = ts.tz_convert('US/Eastern') - pd.Timedelta(seconds=1)
            dt_next = ts_eastern.strftime('%Y%m%d %H:%M:%S US/Eastern')

            if dt and dt_next == dt:
                print("   No progress in endDateTime; stopping to avoid identical request")
                break
            dt = dt_next

            # Courteous delay between requests
            await asyncio.sleep(1.0)

        if not parts:
            print("❌ No data received")
            return pd.DataFrame()

        all_bars = [b for part in reversed(parts) for b in part]
        print(f"✅ Received {len(parts)} pages, total bars: {len(all_bars)}")
        return util.df(all_bars)

    finally:
        if ib.isConnected():
            ib.disconnect()
            print("🔌 Disconnected from IB")


async def _fetch_truly_concurrent(ib, contract, chunk, bar_size, what, use_rth, num_chunks):
    """Fetch chunks truly concurrently without sequential discovery."""
    from datetime import datetime, timedelta
    
    limiter = IBRatelimiter()
    
    # Calculate date ranges for concurrent requests
    # For 20D chunks, space them 20 days apart going backwards
    end_dates = []
    current_date = datetime.now()
    
    for i in range(num_chunks):
        if i == 0:
            end_dates.append('')  # First request uses current time
        else:
            # Go back 20 days for each chunk
            past_date = current_date - timedelta(days=20 * i)
            end_dates.append(past_date.strftime("%Y%m%d %H:%M:%S US/Eastern"))
    
    async def fetch_single_chunk(end_dt, chunk_idx):
        await limiter.wait()
        try:
            print(f"   🔄 Fetching chunk {chunk_idx+1} concurrently, end: {end_dt or 'now'}")
            bars = await ib.reqHistoricalDataAsync(
                contract,
                endDateTime=end_dt,
                durationStr=chunk,
                barSizeSetting=bar_size,
                whatToShow=what,
                useRTH=use_rth,
                keepUpToDate=False,
            )
            print(f"   ✅ Chunk {chunk_idx+1} completed: {len(bars) if bars else 0} bars")
            return bars, chunk_idx
        except Exception as e:
            print(f"   ❌ Chunk {chunk_idx+1} failed: {e}")
            return None, chunk_idx
    
    # Create all tasks
    tasks = [fetch_single_chunk(end_dt, i) for i, end_dt in enumerate(end_dates)]
    
    # Execute all tasks concurrently
    print(f"🚀 Executing {len(tasks)} requests truly concurrently...")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Sort results by chunk index and filter out None results
    chunks = []
    for result in results:
        if isinstance(result, Exception):
            print(f"   ⚠️ Task raised exception: {result}")
        elif result[0] is not None:  # result is (bars, chunk_idx)
            chunks.append((result[0], result[1]))
    
    # Sort by chunk index to maintain chronological order (newest first)
    chunks.sort(key=lambda x: x[1])
    return [bars for bars, _ in chunks]


async def main():
    parser = argparse.ArgumentParser(description="Async IB historical downloader (simple pagination)")
    parser.add_argument('--symbol', default='TQQQ', help='Symbol, e.g., TQQQ')
    parser.add_argument('--bar-size', default='1 min', help='Bar size, e.g., "1 min", "5 mins", "1 hour"')
    parser.add_argument('--chunk', default='20 D', help='Duration per request, e.g., "20 D"')
    parser.add_argument('--what', default='TRADES', help='whatToShow, e.g., TRADES, MIDPOINT, BID, ASK')
    parser.add_argument('--rth', action='store_true', help='Use regular trading hours only')
    parser.add_argument('--no-rth', dest='rth', action='store_false', help='Include pre/post market (RTH=False)')
    parser.set_defaults(rth=True)
    parser.add_argument('--client-id', type=int, default=9999)
    parser.add_argument('--end', default='', help="endDateTime for first request, '' means now")
    parser.add_argument('--pages', type=int, default=5, help='Number of pages to fetch (pagination depth)')
    parser.add_argument('--save-csv', default=None, help='Optional path to save CSV')

    args = parser.parse_args()

    df = await fetch_historical_paginated(
        symbol=args.symbol,
        bar_size=args.bar_size,
        chunk=args.chunk,
        what=args.what,
        use_rth=args.rth,
        client_id=args.client_id,
        end=args.end,
        max_chunks=args.pages,
    )

    if df.empty:
        print("No data to display")
        return

    # Display
    print("\n📈 Data Summary:")
    print(f"   Total bars: {len(df):,}")
    if 'date' in df.columns:
        print(f"   Date range: {df['date'].min()} to {df['date'].max()}")
    elif 'timestamp' in df.index.names or df.index.name == 'timestamp':
        print(f"   Date range: {df.index.min()} to {df.index.max()}")
    if 'close' in df.columns and not df['close'].empty:
        print(f"   Latest close: ${df['close'].iloc[-1]:.2f}")

    print("\n🔍 First 5 bars:")
    print(df.head())

    print("\n🔍 Last 5 bars:")
    print(df.tail())

    print("\n📊 Basic statistics:")
    print(df.describe())

    if args.save_csv:
        df.to_csv(args.save_csv)
        print(f"\n💾 Data saved to {args.save_csv}")


if __name__ == '__main__':
    asyncio.run(main())
