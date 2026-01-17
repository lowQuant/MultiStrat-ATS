"""
Lightweight FX cache for IB Multi-Strategy ATS.

- Print-based diagnostics (no add_log).
- Async-first get_fx_rate() to avoid event-loop issues.
- IB spot first (if connected), yfinance fallback, default 1.0.
- TTL-based caching.
"""

import math
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional

import pandas as pd
import yfinance as yf
from ib_async import Forex


class FXCache:
    def __init__(self, ib_client, base_currency: str = "USD", ttl_minutes: int = 60):
        self.ib = ib_client
        self.base = base_currency
        self.ttl = timedelta(minutes=ttl_minutes)
        self.fx_cache: Dict[Tuple[str, str], float] = {}
        self.fx_ts: Dict[Tuple[str, str], datetime] = {}
        print(f"[FX] FXCache initialized (base={self.base}, ttl={ttl_minutes}m)")

    def _is_fresh(self, key: Tuple[str, str]) -> bool:
        ts = self.fx_ts.get(key)
        return bool(ts and (datetime.utcnow() - ts) < self.ttl)

    async def get_fx_rate(self, currency: str, base_currency: str, ib_client=None) -> float:
        """
        Async: Get FX rate currency/base_currency with TTL cache.
        IB first, then yfinance, else default 1.0.
        """
        key = (currency, base_currency)

        # Cache hit and fresh
        if key in self.fx_cache and self._is_fresh(key):
            return self.fx_cache[key]

        # Identity rate
        if currency == base_currency:
            self.fx_cache[key] = 1.0
            self.fx_ts[key] = datetime.utcnow()
            return 1.0

        ib = ib_client if ib_client else self.ib
        
        # 1) IB spot (non-blocking)
        try:
            is_connected = getattr(ib, "isConnected", None)
            if is_connected and ib.isConnected():
                fx_pair = Forex(f"{base_currency}{currency}")

                # Try a sequence of market data types
                for md_type in (1, 3, 4):  # 1=live, 3=delayed, 4=delayed-frozen
                    try:
                        print("trying mktdatatype ", md_type)
                        ib.reqMarketDataType(md_type)
                        try:
                            await asyncio.wait_for(
                                ib.qualifyContractsAsync(fx_pair),
                                timeout=2.0,
                            )
                        except asyncio.TimeoutError:
                            print(f"[FX] qualifyContracts timeout for {currency}/{base_currency} (md={md_type})")
                            continue

                        ticker = ib.reqMktData(fx_pair, "", False, False)

                        # Poll up to ~1s for first valid price
                        rate = None
                        for _ in range(10):
                            px = ticker.marketPrice()
                            if isinstance(px, (int, float)) and not math.isnan(px):
                                rate = float(px)
                                break
                            await asyncio.sleep(0.1)

                        # Clean up subscription
                        try:
                            ib.cancelMktData(fx_pair)
                        except Exception:
                            pass

                        if rate is not None:
                            self.fx_cache[key] = rate
                            self.fx_ts[key] = datetime.utcnow()
                            print(f"[FX] IB rate {currency}/{base_currency} (md={md_type}) = {rate}")
                            return rate

                    except Exception as e_md:
                        print(f"[FX] IB mdType {md_type} failed for {currency}/{base_currency}: {e_md}")

                print(f"[FX] IB price not available for {currency}/{base_currency}, fallback yfinance")
            else:
                print(f"[FX] IB client not connected, skipping spot for {currency}/{base_currency}")

        except Exception as e:
            print(f"[FX] IB fetch failed for {currency}/{base_currency}: {e}")

        # 2) yfinance fallback (threaded)
        try:
            yf_ticker = f"{base_currency}{currency}=X"
            rate = await asyncio.to_thread(self._fetch_yf_ask, yf_ticker)
            if rate is not None:
                self.fx_cache[key] = rate
                self.fx_ts[key] = datetime.utcnow()
                print(f"[FX] yfinance rate {currency}/{base_currency} = {rate}")
                return rate
        except Exception as e:
            print(f"[FX] yfinance failed for {base_currency}{currency}=X: {e}")

        # 3) Default
        self.fx_cache[key] = 1.0
        self.fx_ts[key] = datetime.utcnow()
        print(f"[FX] Default rate 1.0 used for {currency}/{base_currency}")
        return 1.0

    def _fetch_yf_ask(self, yf_ticker: str) -> Optional[float]:
        info = yf.Ticker(yf_ticker).info
        ask = info.get("ask")
        return float(ask) if ask else None

    async def convert_marketValue_to_base_async(self, df: pd.DataFrame, base_currency: str) -> pd.DataFrame:
        """
        Async conversion: fetch missing rates concurrently, respects TTL.
        
        Expects input column 'marketValue' (IB/SDK camelCase) and writes 'marketValue_base'.
        """
        try:
            df = df.copy()
            # Ensure required input column exists in IB naming
            if "marketValue" not in df.columns:
                raise KeyError("Expected column 'marketValue' not found")

            currencies = df["currency"].fillna(base_currency).astype(str).tolist()
            unique = sorted(set(currencies))
            tasks = [self.get_fx_rate(cur, base_currency) for cur in unique]
            rates = await asyncio.gather(*tasks)
            rate_map = {cur: rate for cur, rate in zip(unique, rates)}
            df["fx_rate"] = df["currency"].map(lambda x: rate_map.get(x, 1.0))
            # Compute base value in IB-style destination column
            df["marketValue_base"] = df["marketValue"] / df["fx_rate"]
            return df
        except Exception as e:
            print(f"[FX] Error (async convert): {e}")
            df = df.copy()
            df["fx_rate"] = 1.0
            # Fall back to native value if available
            df["marketValue_base"] = df.get("marketValue", 0.0)
            return df

    def clear_cache(self) -> None:
        self.fx_cache.clear()
        self.fx_ts.clear()
        print("[FX] FX cache cleared")

    def clear_cache_if_stale(self, max_age_minutes: int = 30) -> bool:
        if not self.fx_ts:
            return False
        try:
            newest = max(self.fx_ts.values())
            if datetime.utcnow() - newest > timedelta(minutes=max_age_minutes):
                self.clear_cache()
                print(f"[FX] FX cache cleared due to staleness > {max_age_minutes}m")
                return True
        except Exception as e:
            print(f"[FX] Error checking staleness: {e}")
        return False

    def get_cache_status(self) -> dict:
        print("[FX] Cache status:", self.fx_cache)
        return {
            "base_currency": self.base,
            "cached_pairs": len(self.fx_cache),
            "pairs": list(self.fx_cache.keys()),
        }