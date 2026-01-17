import numpy as np
import pandas as pd
import yfinance as yf
import datetime
import time
from pathlib import Path
import warnings
import re
import sys

# Conditionally import tqdm
try:
    from tqdm import tqdm
except ImportError:
    # Simple tqdm alternative if not available
    def tqdm(iterable, **kwargs):
        total = len(iterable) if hasattr(iterable, '__len__') else None
        desc = kwargs.get('desc', '')
        if total:
            print(f"{desc} (Total: {total})")
        return iterable

# Suppress specific FutureWarnings
warnings.filterwarnings("ignore", category=FutureWarning)

BASE_DIR = Path(__file__).resolve().parent
UNIV_CSV_PATH = BASE_DIR / "univ_us_equities.csv"
SECTOR_OUTPUT_DIR = BASE_DIR / "output" / "sectors"
SYMBOL_OUTPUT_DIR = BASE_DIR / "output" / "symbols"

SECTOR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SYMBOL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    return sanitized.strip("_") or "unknown"


def load_universe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0)
    df = df[["Symbol", "Name", "Sector", "Market Cap"]].dropna(subset=["Symbol", "Sector"])
    df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
    df["Name"] = df["Name"].astype(str).str.strip()
    df["Sector"] = df["Sector"].astype(str).str.strip()
    df["Market Cap"] = pd.to_numeric(df["Market Cap"], errors="coerce")
    df = df[df["Symbol"].ne("")]
    return df


def download_sector_data(symbols) -> pd.DataFrame:
    cleaned_symbols = sorted({sym.strip().upper() for sym in symbols if isinstance(sym, str) and sym.strip()})
    if not cleaned_symbols:
        return pd.DataFrame()
        
    try:
        # If too many symbols, break into smaller chunks to avoid rate limits
        if len(cleaned_symbols) > 50:
            print(f"Breaking {len(cleaned_symbols)} symbols into smaller chunks to avoid rate limits")
            chunks = [cleaned_symbols[i:i + 30] for i in range(0, len(cleaned_symbols), 30)]
            all_data = []
            
            for i, chunk in enumerate(chunks):
                print(f"Downloading chunk {i+1}/{len(chunks)} ({len(chunk)} symbols)")
                chunk_data = yf.download(
                    tickers=chunk,
                    group_by="Ticker",
                    period="max",
                    auto_adjust=True,
                    threads=True,
                )
                if not chunk_data.empty:
                    all_data.append(chunk_data)
                # Add delay between chunks to avoid rate limits
                if i < len(chunks) - 1:  # Don't wait after last chunk
                    time.sleep(3)  # 3 second delay between chunks
                    
            # Combine chunks if we got any data
            if all_data:
                data = pd.concat(all_data, axis=1)
            else:
                return pd.DataFrame()
        else:
            data = yf.download(
                tickers=cleaned_symbols,
                group_by="Ticker",
                period="max",
                auto_adjust=True,
                threads=True,
            )
    except Exception as e:
        print(f"Error downloading data: {e}")
        return pd.DataFrame()

    if data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        stacked = data.stack(level=0).rename_axis(['Date', 'Symbol']).reset_index(level=1)
    else:
        stacked = data.copy()
        stacked['Symbol'] = cleaned_symbols[0]
        stacked = stacked.rename_axis('Date')

    return stacked


def compute_indicators(df: pd.DataFrame, symbol_to_name, symbol_to_sector, symbol_to_mktcap) -> pd.DataFrame:
    if df.empty:
        return df
        
    # Make sure we have a clean index without duplicates
    df = df.sort_index()
    
    # Check for and handle duplicate indices
    if df.index.duplicated().any():
        print(f"Warning: Found {df.index.duplicated().sum()} duplicate index entries. Using first occurrence.")
        df = df[~df.index.duplicated(keep='first')]
    
    # Add metadata columns
    df["Name"] = df["Symbol"].map(symbol_to_name)
    df["Sector"] = df["Symbol"].map(symbol_to_sector)
    df["Market Cap"] = df["Symbol"].map(symbol_to_mktcap)

    # Calculate price change periods
    df['1M'] = df.groupby('Symbol')['Close'].pct_change(21)
    df['3M'] = df.groupby('Symbol')['Close'].pct_change(63)
    df['6M'] = df.groupby('Symbol')['Close'].pct_change(126)
    df['12M'] = df.groupby('Symbol')['Close'].pct_change(252)
    
    # Calculate RS indicators
    df['RS IBD'] = 2 * df['3M'] + df['6M'] + df['12M']
    
    # Handle potential issues with rank calculation
    try:
        df['RS Rank'] = df.groupby(df.index)['RS IBD'].rank(pct=True)
        df["RS Rank 20D MA"] = df.groupby("Symbol")["RS Rank"].transform(lambda x: x.rolling(window=20).mean())
    except Exception as e:
        print(f"Warning: Error calculating RS Rank: {e}")
        df['RS Rank'] = np.nan
        df['RS Rank 20D MA'] = np.nan

    # Calculate EMAs using pandas ewm
    df["20D_EMA"] = df.groupby("Symbol")["Close"].transform(lambda x: x.ewm(span=20, adjust=False).mean())
    df["50D_EMA"] = df.groupby("Symbol")["Close"].transform(lambda x: x.ewm(span=50, adjust=False).mean())
    df["200D_EMA"] = df.groupby("Symbol")["Close"].transform(lambda x: x.ewm(span=200, adjust=False).mean())

    # Calculate ATR for each symbol directly
    df_with_tr = df.copy()
    
    # Calculate true range components for each symbol
    for symbol in df_with_tr['Symbol'].unique():
        mask = df_with_tr['Symbol'] == symbol
        high = df_with_tr.loc[mask, 'High']
        low = df_with_tr.loc[mask, 'Low']
        close = df_with_tr.loc[mask, 'Close']
        
        # Calculate true range
        tr1 = (high - low).abs()
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        
        # Get maximum of the three
        df_with_tr.loc[mask, 'TR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Now calculate ATR using transform for each symbol
    df['ATR'] = df_with_tr.groupby('Symbol')['TR'].transform(lambda x: x.rolling(window=20).mean())
    df['STD'] = df.groupby('Symbol')['Close'].rolling(window=20).std().reset_index(level=0, drop=True)

    # Calculate Keltner Channels directly
    df['KC_Upper_raw'] = df['20D_EMA'] + (df['ATR'] * 1.5)
    df['KC_Lower_raw'] = df['20D_EMA'] - (df['ATR'] * 1.5)
    
    # Apply shift by symbol
    df['KC_Upper'] = df.groupby('Symbol')['KC_Upper_raw'].transform(lambda x: x.shift(1))
    df['KC_Lower'] = df.groupby('Symbol')['KC_Lower_raw'].transform(lambda x: x.shift(1))
    
    # Drop intermediate columns
    df = df.drop(['KC_Upper_raw', 'KC_Lower_raw'], axis=1)

    df['DC_Upper'] = df.groupby('Symbol')['High'].rolling(window=20).max().shift(1).reset_index(level=0, drop=True)
    df['DC_Lower'] = df.groupby('Symbol')['Low'].rolling(window=20).min().shift(1).reset_index(level=0, drop=True)

    # Calculate Bollinger Bands directly
    df['BB_Upper_raw'] = df['20D_EMA'] + (df['STD'] * 2)
    df['BB_Lower_raw'] = df['20D_EMA'] - (df['STD'] * 2)
    
    # Apply shift by symbol
    df['BB_Upper'] = df.groupby('Symbol')['BB_Upper_raw'].transform(lambda x: x.shift(1))
    df['BB_Lower'] = df.groupby('Symbol')['BB_Lower_raw'].transform(lambda x: x.shift(1))
    
    # Drop intermediate columns
    df = df.drop(['BB_Upper_raw', 'BB_Lower_raw'], axis=1)

    df['1d'] = df.groupby('Symbol')['Close'].pct_change(1)

    df.sort_index(inplace=True)
    return df


def save_outputs(sector: str, df: pd.DataFrame) -> None:
    if df.empty:
        print(f"Warning: Empty dataframe for sector {sector}, no files will be saved.")
        return
        
    try:
        sector_filename = sanitize_filename(sector)
        sector_output_path = SECTOR_OUTPUT_DIR / f"{sector_filename}.csv"

        # Reset index and prepare for output
        output_df = df.reset_index()
        
        # Handle different index column names
        if 'index' in output_df.columns:
            output_df = output_df.rename(columns={'index': 'Date'})
        
        # Sort for consistency
        output_df = output_df.sort_values(['Symbol', 'Date'])

        # Save sector data
        print(f"Writing sector data to {sector_output_path}")
        output_df.to_csv(sector_output_path, index=False)

        # Save individual symbol data
        symbols_in_data = sorted(output_df['Symbol'].unique())
        for symbol in tqdm(symbols_in_data, desc=f"Writing {sector} symbols", leave=False):
            symbol_data = output_df[output_df['Symbol'] == symbol]
            if symbol_data.empty:
                continue
            symbol_output_path = SYMBOL_OUTPUT_DIR / f"{symbol}.csv"
            symbol_data.to_csv(symbol_output_path, index=False)
    except Exception as e:
        print(f"Error saving outputs for sector {sector}: {e}")


def main():
    print(f"{datetime.datetime.now()}: Loading universe from CSV")
    try:
        univ_df = load_universe(UNIV_CSV_PATH)
    except Exception as e:
        print(f"Error loading universe: {e}")
        return

    symbol_to_name = dict(zip(univ_df["Symbol"], univ_df["Name"]))
    symbol_to_sector = dict(zip(univ_df["Symbol"], univ_df["Sector"]))
    symbol_to_mktcap = dict(zip(univ_df["Symbol"], univ_df["Market Cap"]))

    # Get unique sectors, handling potential NaN values safely
    sectors = sorted(univ_df['Sector'].dropna().unique())
    
    # Optional: allow processing just one sector for testing
    selected_sector = None
    if len(sys.argv) > 1:
        selected_sector = sys.argv[1]
        if selected_sector in sectors:
            print(f"Processing only sector: {selected_sector}")
            sectors = [selected_sector]
        else:
            print(f"Warning: Sector '{selected_sector}' not found in universe. Processing all sectors.")
    
    for sector in sectors:
        try:
            print(f'{datetime.datetime.now()}: Downloading {sector} data')
            sector_symbols = univ_df.loc[univ_df.Sector == sector, 'Symbol'].tolist()
            
            # Skip empty sectors
            if not sector_symbols:
                print(f"No symbols found for sector: {sector}, skipping.")
                continue

            sector_data = download_sector_data(sector_symbols)
            if sector_data.empty:
                print(f"{datetime.datetime.now()}: No data returned for {sector}, skipping.")
                continue

            print(f'{datetime.datetime.now()}: {sector} data downloaded. Continue with indicator calculations.')

            # Process the data to add indicators
            sector_data = compute_indicators(sector_data, symbol_to_name, symbol_to_sector, symbol_to_mktcap)
            
            # Save the processed data
            save_outputs(sector, sector_data)

            print(f'{datetime.datetime.now()}: {sector} data written to CSV files')
            
        except Exception as e:
            print(f"Error processing sector {sector}: {e}")
            continue


if __name__ == "__main__":
    main()
