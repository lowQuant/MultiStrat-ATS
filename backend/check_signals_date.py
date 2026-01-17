import pandas as pd
from core.arctic_manager import get_ac

# Strategy Parameters used for calculation
PARAMS = {
    "multiplier": 2.5,
    "decline_days": 4,
}

def check():
    print("Connecting to ArcticDB...")
    ac = get_ac()
    lib = ac.get_library("us_equities")
    if not lib.has_symbol("ALL_STOCKS"):
        print("ALL_STOCKS not found.")
        return

    print("Reading ALL_STOCKS...")
    df = lib.read("ALL_STOCKS").data
    print(f"Data shape: {df.shape}")
    
    if 'Date' not in df.columns and isinstance(df.index, pd.DatetimeIndex):
        df.reset_index(inplace=True)
    
    if 'Date' not in df.columns:
        print("No Date column found.")
        return

    df['Date'] = pd.to_datetime(df['Date'])
    
    # Logic from FourDayDeclineStrategy
    df.sort_values(['Symbol', 'Date'], inplace=True)
    
    df['Prev_Close'] = df.groupby('Symbol')['Close'].shift(1)
    df['Is_Decline'] = df['Close'] < df['Prev_Close']
    
    s = df['Is_Decline']
    df['Decline_Streak'] = s * (s.groupby([df['Symbol'], (~s).cumsum()]).cumcount() + 1)

    # Mean 4D Return
    if '1d_ret' in df.columns:
        df['Mean_4D_Ret'] = df.groupby('Symbol')['1d_ret'].rolling(window=4).mean().reset_index(level=0, drop=True)
    else:
        df['Daily_Ret'] = df.groupby('Symbol')['Close'].pct_change()
        df['Mean_4D_Ret'] = df.groupby('Symbol')['Daily_Ret'].rolling(window=4).mean().reset_index(level=0, drop=True)

    if '200D_EMA' in df.columns:
        condition = (df['Close'] > df['200D_EMA']) & (df['Market Cap'] > 2e9) & (df['Decline_Streak'] == PARAMS['decline_days'])
        df['Signal'] = condition
        
        # Limit Price
        df['Limit_Price_Target'] = df['Close'] * (1 + (PARAMS['multiplier'] * df['Mean_4D_Ret']))
        
        # Filter for 2025-11-26 specifically
        target_date = pd.Timestamp("2025-11-26")
        signals = df[(df['Date'] == target_date) & (df['Signal'])].copy()
        
        print(f"\n--- Signals for {target_date.date()} ---")
        print(f"Count: {len(signals)}")
        
        if not signals.empty:
            print("\nSymbol | Close | Mean_4D_Ret | Limit Price")
            print("-" * 45)
            for _, row in signals.iterrows():
                symbol = row['Symbol']
                close = row['Close']
                ret = row['Mean_4D_Ret']
                limit = row['Limit_Price_Target']
                print(f"{symbol:<6} | {close:<6.2f} | {ret:<11.4f} | {limit:.2f}")
            print("-" * 45)
            print("You can execute these orders manually or update the strategy parameters to look back.")

    else:
        print("Missing columns for signal generation (200D_EMA).")

if __name__ == "__main__":
    check()
