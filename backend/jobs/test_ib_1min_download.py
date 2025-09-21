"""
Simple test script to download 1-minute TQQQ data from Interactive Brokers.
Just for testing - no ArcticDB saving.

Usage:
    python test_ib_1min_download.py

Notes:
- Uses pagination approach to fetch maximum historical 1-minute data
- Downloads data in 10-day chunks and combines them
"""
import sys
import os
import time
from datetime import datetime

# Add parent directory to path to fix import issues
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from ib_async import IB, Stock, util


def download_tqqq_1min_data():
    """Download 1-minute TQQQ data for testing using pagination."""
    
    # Connect to IB (synchronous version)
    ib = IB()
    try:
        ib.connect('127.0.0.1', 7497, clientId=9999)
        print("✅ Connected to Interactive Brokers")
        
        # Create TQQQ contract
        contract = Stock('TQQQ', 'SMART', 'USD')
        ib.qualifyContracts(contract)
        print("✅ Contract qualified")
        
        print(f"📊 Requesting historical 1-minute data for TQQQ using pagination...")
        
        # Use pagination to get maximum data
        dt = ''  # Start with current time
        barsList = []
        max_attempts = 50  # Safety limit
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            print(f"   Fetching chunk {attempt}, end date: {dt if dt else 'now'}")
            
            # Request 10-day chunks of 1-minute data
            bars = ib.reqHistoricalData(
                contract,
                endDateTime=dt,
                durationStr='10 D',
                barSizeSetting='1 min',
                whatToShow='TRADES',  # Can also try MIDPOINT if TRADES doesn't work
                useRTH=True,
                formatDate=1
            )
            
            # Break if no more data
            if not bars:
                print("   No more data available")
                break
                
            barsList.append(bars)
            
            # Update end date to the earliest bar for next request
            dt = bars[0].date
            print(f"   Got {len(bars)} bars, earliest: {dt}")
            
            # Avoid hitting rate limits
            time.sleep(1)
        
        if not barsList:
            print("❌ No data received")
            return
            
        # Combine all bars and create DataFrame
        print(f"✅ Received data in {len(barsList)} chunks")
        
        # Flatten the list of lists into a single list
        allBars = [b for bars in reversed(barsList) for b in bars]
        print(f"✅ Total bars: {len(allBars)}")
        
        # Convert to DataFrame using ib_async utility
        df = util.df(allBars)
        
        # Display results
        print(f"\n📈 TQQQ 1-Minute Data Summary:")
        print(f"   Total bars: {len(df):,}")
        print(f"   Date range: {df['date'].min()} to {df['date'].max()}")
        print(f"   Latest close: ${df['close'].iloc[-1]:.2f}")
        
        print(f"\n🔍 First 5 bars:")
        print(df.head())
        
        print(f"\n🔍 Last 5 bars:")
        print(df.tail())
        
        print(f"\n📊 Basic statistics:")
        print(df.describe())
        
        # Optional: Save to CSV
        csv_path = 'tqqq_1min_data.csv'
        df.to_csv(csv_path)
        print(f"\n💾 Data saved to {csv_path}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        
    finally:
        if ib and ib.isConnected():
            ib.disconnect()
            print("🔌 Disconnected from IB")


if __name__ == "__main__":
    print("🚀 Starting TQQQ 1-minute data download test...")
    download_tqqq_1min_data()
