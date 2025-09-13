"""
Scanner routes: expose scanner options from ArcticDB and run scans via StrategyManager's IB client.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List, Optional
import pandas as pd

# StrategyManager will be injected by main.py
strategy_manager = None

def set_strategy_manager(sm):
    global strategy_manager
    strategy_manager = sm

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


def get_sm():
    if strategy_manager is None:
        raise HTTPException(status_code=503, detail="Strategy manager not initialized")
    return strategy_manager


@router.get("/options")
async def get_scanner_options(sm = Depends(get_sm)) -> Dict[str, Any]:
    """Return scanner codes and filters from ArcticDB library 'scanners'."""
    try:
        ac = sm.get_arctic_client()
        lib = ac.get_library('scanners')
        out: Dict[str, Any] = {"success": True, "codes": [], "filters": []}
        if lib.has_symbol('codes'):
            codes_df = lib.read('codes').data
            codes_df = codes_df.fillna("")
            mask = ~(
                codes_df['code'].str.contains('bond', case=False, na=False) |
                codes_df['display_name'].str.contains('bond', case=False, na=False)
            )
            out["codes"] = codes_df[mask].to_dict(orient='records')
        if lib.has_symbol('filters'):
            filters_df = lib.read('filters').data
            filters_df = filters_df.fillna("")
            mask = ~(
                filters_df['code'].str.contains('bond', case=False, na=False) |
                filters_df['display_name'].str.contains('bond', case=False, na=False)
            )
            out["filters"] = filters_df[mask].to_dict(orient='records')
        return out
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/scan")
async def run_scan(payload: Dict[str, Any], sm = Depends(get_sm)) -> Dict[str, Any]:
    """
    Run a scanner using the master IB connection.

    Expected JSON body:
    {
      "instrument": "STK",
      "locationCode": "STK.US.MAJOR",
      "scanCode": "HIGH_OPEN_GAP",
      "filters": [{"tag": "usdPriceAbove", "value": "10"}, ...],
      "top_n": 10
    }
    """
    try:
        if not sm.is_connected or not sm.ib_client:
            raise HTTPException(status_code=503, detail="IB not connected")

        from ib_async import ScannerSubscription, TagValue
        from ib_async.contract import Contract

        ib = sm.ib_client

        instrument = payload.get("instrument", "STK")
        locationCode = payload.get("locationCode", "STK.US.MAJOR")
        scanCode = payload.get("scanCode")
        if not scanCode:
            raise HTTPException(status_code=400, detail="scanCode is required")
        filters_in = payload.get("filters", []) or []

        sub = ScannerSubscription()
        sub.instrument = instrument
        sub.locationCode = locationCode
        sub.scanCode = scanCode

        tag_values = [TagValue(f.get("tag"), str(f.get("value", ""))) for f in filters_in if f.get("tag")]

        # Request scanner data (async)
        scan_data = await ib.reqScannerDataAsync(sub, scannerSubscriptionFilterOptions=tag_values)
        print(f"[SCANNER] Received {len(scan_data)} rows for scanCode='{scanCode}', instrument='{instrument}', location='{locationCode}'")
        print(scan_data)
        rows = scan_data
        print(rows)
        # Return basic fields without extra historical computations
        results = []
        for idx, d in enumerate(rows):
            c = d.contractDetails.contract
            item = {
                "rank": getattr(d, 'rank', None),
                "symbol": getattr(c, 'symbol', None),
            }
            # Optional metadata if present on the scanner row
            for key in ("distance", "benchmark", "projection", "legs"):
                val = getattr(d, key, None)
                if val is not None:
                    item[key] = val
            results.append(item)

            # Debug print of raw fields to validate what we might be missing
            try:
                debug_keys = {k: getattr(d, k) for k in ("rank", "distance", "benchmark", "projection", "legs") if hasattr(d, k)}
                debug_sym = getattr(c, 'symbol', None)
                print(f"[SCANNER][{idx}] symbol={debug_sym} attrs={debug_keys}")
            except Exception as _e:
                # Best-effort debug
                print(f"[SCANNER][{idx}] debug print failed: {_e}")

        return {"success": True, "data": results}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/history")
async def get_history(symbol: str, sm = Depends(get_sm)) -> Dict[str, Any]:
    """
    Return 1Y daily OHLC for a given stock symbol using the master IB connection.
    """
    try:
        if not sm.is_connected or not sm.ib_client:
            raise HTTPException(status_code=503, detail="IB not connected")

        from ib_async.contract import Stock

        ib = sm.ib_client
        # Resolve a basic stock contract on SMART/US
        contract = Stock(symbol, 'SMART', 'USD')
        details = await ib.reqContractDetailsAsync(contract)
        if not details:
            raise HTTPException(status_code=404, detail=f"No contract details for {symbol}")
        contract = details[0].contract

        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime='',
            durationStr='1 Y',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            keepUpToDate=False
        )

        # Convert to JSON-friendly arrays
        dates: List[str] = []
        opens: List[float] = []
        highs: List[float] = []
        lows: List[float] = []
        closes: List[float] = []
        for b in bars:
            # b.date is dt or str depending on library; ensure ISO string
            d = b.date.isoformat() if hasattr(b.date, 'isoformat') else str(b.date)
            dates.append(d)
            opens.append(float(b.open) if b.open is not None else None)
            highs.append(float(b.high) if b.high is not None else None)
            lows.append(float(b.low) if b.low is not None else None)
            closes.append(float(b.close) if b.close is not None else None)

        print(f"[SCANNER][HISTORY] {symbol} -> {len(dates)} daily bars")
        return {"success": True, "data": {"symbol": symbol, "dates": dates, "open": opens, "high": highs, "low": lows, "close": closes}}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}
