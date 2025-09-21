"""
BacktestManager orchestrates a single-strategy backtest with minimal refactors.
- Loads historical data (ArcticDB if available, else yfinance)
- Instantiates a strategy without starting its thread
- Injects a BacktestIB mock and runs the strategy using the `on_bar` hook
- Uses BacktestEngine to process orders, fills, and equity
"""
from __future__ import annotations

import asyncio
import inspect
import importlib.util
from types import SimpleNamespace
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Callable

import numpy as np
import pandas as pd

from core.arctic_manager import get_ac
from utils.ib_connection import connect_to_ib, disconnect_from_ib
from utils.ib_historical_downloader import download_ib_historical_paginated
from ib_async import Stock
from backtest.backtest_engine import BacktestEngine
from backtest.mock_ib import BacktestIB, MockRealTimeBar
from broker.backtest_broker import BacktestBroker


@dataclass
class BacktestConfig:
    initial_capital: float = 100_000.0
    commission_per_share: float = 0.005
    slippage_bps: float = 0.0


class BacktestManager:
    def __init__(self, ac=None, strategy_manager=None) -> None:
        self.ac = ac or get_ac()
        self.strategy_manager = strategy_manager

    # ------------------- Strategy loading -------------------
    def load_strategy_class(self, filename: str) -> Optional[Type]:
        strategies_dir = Path(__file__).resolve().parent.parent / "strategies"
        path = strategies_dir / filename
        if not path.exists():
            return None
        module_name = filename[:-3]
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)  # type: ignore
        candidates = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and attr_name.endswith("Strategy") and attr_name != "BaseStrategy":
                candidates.append((attr_name, attr))
        if not candidates:
            return None
        preferred = [c for c in candidates if "Backtest" not in c[0]]
        return (preferred[0][1] if preferred else candidates[0][1])

    # ------------------- Data loading -------------------
    def _interval_mapping(self, interval: str) -> Dict[str, str]:
        interval = (interval or "minute").lower()
        if interval in {"minute", "1m", "1min"}:
            return {"alias": "minute", "yf": "1m", "ib": "1 min"}
        if interval in {"hour", "hourly", "60m", "1h"}:
            return {"alias": "hourly", "yf": "60m", "ib": "1 hour"}
        if interval in {"day", "daily", "1d"}:
            return {"alias": "daily", "yf": "1d", "ib": "1 day"}
        # default minute
        return {"alias": "minute", "yf": "1m", "ib": "1 min"}

    async def _load_or_download_data(self, symbol: str, start_date: str, end_date: str, interval: str, progress_cb: Optional[Callable[[float, str], None]] = None) -> pd.DataFrame:
        m = self._interval_mapping(interval)
        alias = m["alias"]
        yf_interval = m["yf"]
        ib_bar_size = m["ib"]
        sym_key = f"{symbol.lower()}_{alias}"

        # Normalize dates and support special end_date values
        start_ts = pd.to_datetime(start_date)
        if not end_date or str(end_date).strip().lower() in {"max", "today"}:
            # Use US/Eastern today for consistency with IB time
            try:
                end_ts = pd.Timestamp.now(tz="US/Eastern").normalize().tz_convert(None)
            except Exception:
                end_ts = pd.to_datetime(pd.Timestamp.today().date())
        else:
            end_ts = pd.to_datetime(end_date)
        start_str = start_ts.strftime("%Y-%m-%d")
        end_str = end_ts.strftime("%Y-%m-%d")

        # Prefer ArcticDB 'market_data' library (architecture.md) with interval-suffixed symbol
        lib = self.ac.get_library("market_data", create_if_missing=True)
        try:
            if lib.has_symbol(sym_key):
                existing = lib.read(sym_key).data
                if existing is not None and not existing.empty:
                    # Ensure datetime index and tz-naive for reliable comparisons
                    try:
                        if not isinstance(existing.index, pd.DatetimeIndex):
                            existing.index = pd.to_datetime(existing.index)
                        if getattr(existing.index, 'tz', None) is not None:
                            existing.index = existing.index.tz_convert(None)
                    except Exception:
                        pass
                    existing = existing.sort_index()
                    exist_min = existing.index.min()
                    exist_max = existing.index.max()
                    need_before = start_ts < exist_min
                    need_after = end_ts > exist_max
                    frames: List[pd.DataFrame] = []
                    # Missing older segment
                    if need_before:
                        if progress_cb:
                            progress_cb(0.0, f"Downloading older segment up to {exist_min}")
                        older = await download_ib_historical_paginated(
                            symbol=symbol,
                            interval=alias,
                            start_date=start_ts.strftime("%Y-%m-%d"),
                            end_date=str(exist_min),
                            use_rth=True,
                            what_to_show="TRADES",
                            chunk=None,
                            client_id=9999,
                            progress_cb=progress_cb,
                        )
                        if older is not None and not older.empty:
                            frames.append(older)
                    # Existing
                    frames.append(existing)
                    # Missing newer segment
                    if need_after:
                        if progress_cb:
                            progress_cb(0.0, f"Downloading newer segment from {exist_max}")
                        newer = await download_ib_historical_paginated(
                            symbol=symbol,
                            interval=alias,
                            start_date=str(exist_max),
                            end_date=end_ts.strftime("%Y-%m-%d"),
                            use_rth=True,
                            what_to_show="TRADES",
                            chunk=None,
                            client_id=9999,
                            progress_cb=progress_cb,
                        )
                        if newer is not None and not newer.empty:
                            frames.append(newer)
                    merged = pd.concat(frames).sort_index()
                    merged = merged[~merged.index.duplicated(keep="last")]
                    merged = merged.loc[start_ts:end_ts]
                    # Write back merged
                    try:
                        lib.write(sym_key, merged)
                    except Exception:
                        pass
                    if not merged.empty:
                        return merged
                    # Fall through to fetch fresh if somehow empty
        except Exception:
            pass

        # Try to fetch via Interactive Brokers using the unified downloader (with optional progress)
        try:
            df = await download_ib_historical_paginated(
                symbol=symbol,
                interval=alias,
                start_date=start_str,
                end_date=end_str,
                use_rth=True,
                what_to_show="TRADES",
                chunk=None,
                client_id=9999,
                progress_cb=progress_cb,
            )
            if df is not None and not df.empty:
                # Cache to ArcticDB
                try:
                    lib.write(sym_key, df)
                except Exception:
                    pass
                return df
        except Exception:
            pass

        # Fallback to yfinance if IB unavailable/failed (chunked for 1m limit)
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        frames: List[pd.DataFrame] = []
        if alias == "minute":
            yf_chunk = 7
        elif alias == "hourly":
            yf_chunk = 90
        else:
            yf_chunk = 3650

        cursor = start_ts
        while cursor <= end_ts:
            chunk_end = min(cursor + pd.Timedelta(days=yf_chunk), end_ts)
            # yfinance end is exclusive, extend by 1 day to include last day
            chunk_end_exc = chunk_end + pd.Timedelta(days=1)
            part = ticker.history(start=cursor, end=chunk_end_exc, interval=yf_interval)
            if part is not None and not part.empty:
                # Normalize columns to lowercase
                cols = {c: c.lower() for c in part.columns}
                part = part.rename(columns=cols)
                # Some yfinance use 'adj close'; we stick to 'close'
                if "adj close" in part.columns and "close" not in part.columns:
                    part["close"] = part["adj close"]
                keep = [c for c in ["open", "high", "low", "close", "volume"] if c in part.columns]
                part = part[keep]
                frames.append(part)
            cursor = chunk_end + pd.Timedelta(days=1)

        if frames:
            df = pd.concat(frames).sort_index()
            df = df.loc[start_str:end_str]
            df = df[~df.index.duplicated(keep="last")]
            # Cache to ArcticDB under 'market_data'
            try:
                lib.write(sym_key, df)
            except Exception:
                pass
            return df

        raise ValueError(f"No data available for {symbol} {start_str}..{end_str}")

    async def ensure_data(self, symbol: str, start_date: str, end_date: str, interval: str, progress_cb: Optional[Callable[[float, str], None]] = None) -> Dict[str, Any]:
        """
        Ensure OHLCV data exists in ArcticDB 'ohlcv' for symbol & interval; download if missing.
        Returns basic stats about the ingested/available data.
        """
        df = await self._load_or_download_data(symbol, start_date, end_date, interval, progress_cb=progress_cb)
        alias = self._interval_mapping(interval)["alias"]
        sym_key = f"{symbol.lower()}_{alias}"
        return {
            "symbol": symbol.upper(),
            "interval": alias,
            "rows": int(len(df)),
            "start": str(df.index[0]) if len(df) else None,
            "end": str(df.index[-1]) if len(df) else None,
            "library": "market_data",
            "symbol_key": sym_key,
        }

    # ------------------- Run backtest -------------------
    async def run_backtest(
        self,
        strategy_filename: str,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "minute",
        cfg: Optional[BacktestConfig] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cfg = cfg or BacktestConfig()

        # 1) Load data
        df = await self._load_or_download_data(symbol, start_date, end_date, interval)
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()

        # 2) Init engine and IB mock
        engine = BacktestEngine(
            initial_capital=cfg.initial_capital,
            commission_per_share=cfg.commission_per_share,
            slippage_bps=cfg.slippage_bps,
        )
        engine.load_data(symbol, df)

        # 3) Load strategy class and instantiate without starting thread
        strat_cls = self.load_strategy_class(strategy_filename)
        if strat_cls is None:
            raise ValueError(f"Strategy class not found in {strategy_filename}")
        # Pass minimal params and explicit symbol/broker context
        # Load module-level PARAMS defaults and merge with overrides; ensure symbol is present
        try:
            strategies_dir = Path(__file__).resolve().parent.parent / "strategies"
            strat_path = strategies_dir / strategy_filename
            module_name = strategy_filename[:-3]
            spec2 = importlib.util.spec_from_file_location(module_name, str(strat_path))
            mod2 = importlib.util.module_from_spec(spec2) if spec2 and spec2.loader else None
            if spec2 and spec2.loader and mod2:
                spec2.loader.exec_module(mod2)  # type: ignore
                default_params = getattr(mod2, 'PARAMS', {})
                if not isinstance(default_params, dict):
                    default_params = {}
            else:
                default_params = {}
        except Exception:
            default_params = {}

        merged_params: Dict[str, Any] = {**default_params, **(params or {})}
        merged_params.setdefault("symbol", symbol)
        # Provide defaults commonly assumed by legacy strategies for contract construction
        merged_params.setdefault("exchange", "SMART")
        merged_params.setdefault("currency", "USD")

        # Build kwargs and filter to strategy __init__ signature to support legacy strategies
        # Provide an actual strategy_manager if available; otherwise, a light stub sharing the same Arctic client instance
        strategy_manager_stub = self.strategy_manager or SimpleNamespace(ac=self.ac)

        desired_kwargs = {
            "client_id": 0,
            "strategy_manager": strategy_manager_stub,
            "params": merged_params,
            "broker_type": "backtest",
            "backtest_engine": engine,
            "strategy_symbol": symbol,
        }
        try:
            sig = inspect.signature(strat_cls.__init__)
            params = sig.parameters
            has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            if has_var_kw:
                # If strategy accepts **kwargs, pass all desired kwargs
                init_kwargs = dict(desired_kwargs)
            else:
                allowed = {name for name in params.keys() if name != "self"}
                init_kwargs = {k: v for k, v in desired_kwargs.items() if k in allowed}
        except Exception:
            init_kwargs = {"client_id": 0, "strategy_manager": None, "params": merged_params}

        strategy = strat_cls(**init_kwargs)
        # Ensure backtest attributes exist even if not accepted in __init__
        if not hasattr(strategy, "broker_type"):
            try:
                setattr(strategy, "broker_type", "backtest")
            except Exception:
                pass
        else:
            try:
                strategy.broker_type = "backtest"
            except Exception:
                pass
        if not hasattr(strategy, "backtest_engine"):
            try:
                setattr(strategy, "backtest_engine", engine)
            except Exception:
                pass
        else:
            try:
                strategy.backtest_engine = engine
            except Exception:
                pass
        # Respect requested symbol
        try:
            strategy.symbol = symbol.upper()
        except Exception:
            pass

        # Pre-compute backtest_id for persistence and broker naming
        backtest_id = f"{Path(strategy_filename).stem}_{symbol}_{self._interval_mapping(interval)['alias']}_{datetime.utcnow().isoformat()}"

        # Provide a BacktestBroker so strategy.place_order() works; align broker's artifacts with our backtest_id
        try:
            strategy.broker = BacktestBroker(
                engine=engine,
                strategy_symbol=symbol,
                backtest_name=backtest_id,
            )
        except Exception:
            # If broker fails to init, continue; strategy may still run read-only
            strategy.broker = None

        # Inject mock IB (with broker so ib.placeOrder mirrors records) and mark connected
        mock_ib = BacktestIB(engine, broker=strategy.broker)
        strategy.ib = mock_ib
        strategy.is_connected = True

        # 4) Initialize strategy
        await strategy.initialize_strategy()

        # 5) Drive bar updates via strategy.on_bar and process fills via engine
        equity_curve: List[Dict[str, Any]] = []
        i = 0
        # Register a ticker so engine.step() processes orders for this symbol
        # Choose barSize seconds for the simulated RT stream based on interval
        bar_size_sec = 60 if self._interval_mapping(interval)["alias"] == "minute" else 3600 if self._interval_mapping(interval)["alias"] == "hourly" else 24 * 3600
        ticker = mock_ib.reqRealTimeBars(contract=type("C", (), {"symbol": symbol})(), barSize=bar_size_sec, whatToShow="TRADES", useRTH=True)
        # Wire strategy handler so each engine.step() emits bars to the strategy
        # Prefer generic on_bar; fallback to handle_realtime_bars for older strategies
        handler = getattr(strategy, "on_bar", None)
        if callable(handler):
            ticker.updateEvent += handler
        else:
            fallback = getattr(strategy, "handle_realtime_bars", None)
            if callable(fallback):
                ticker.updateEvent += fallback

        while engine.step():
            # Allow scheduled tasks (from on_bar) to execute before the next step
            await asyncio.sleep(0)
            ts = df.index[i]
            equity_curve.append({"timestamp": ts, "equity": engine.equity()})
            i += 1

        # 6) Build report and persist
        curve_df = pd.DataFrame(equity_curve).set_index("timestamp")
        rets = curve_df["equity"].pct_change().dropna()
        # Scale Sharpe by bar frequency (approximation): minute ~ 252*390, hourly ~ 252*6.5, daily ~ 252
        alias = self._interval_mapping(interval)["alias"]
        periods_per_year = 252 * 390 if alias == "minute" else 252 * 6.5 if alias == "hourly" else 252
        sharpe = float(np.sqrt(periods_per_year) * rets.mean() / (rets.std() if rets.std() != 0 else 1.0)) if len(rets) > 1 else 0.0
        total_return = float(curve_df["equity"].iloc[-1] / curve_df["equity"].iloc[0] - 1.0) if len(curve_df) > 1 else 0.0

        # Trades (collect fills recorded by BacktestBroker if available) and compute entry/exit pairs
        trades_df = None
        try:
            broker_data = getattr(getattr(strategy, 'broker', None), '_backtest_data', None)
            fills = (broker_data or {}).get('fills', []) if isinstance(broker_data, dict) else []
            if fills:
                fdf = pd.DataFrame(fills)
                # Normalize columns
                if 'timestamp' in fdf.columns:
                    fdf = fdf.sort_values('timestamp')
                # Build trade pairs
                rows = []
                position_side = None  # 'long' or 'short'
                entry_px = None
                entry_ts = None
                qty = None
                for _, r in fdf.iterrows():
                    action = str(r.get('side') or r.get('action', '')).upper()
                    px = float(r.get('price', r.get('entry_price', 0.0)) or 0.0)
                    ts = r.get('timestamp', r.get('entry_time'))
                    q = float(r.get('quantity', r.get('qty', 0)) or 0)
                    if position_side is None:
                        if action == 'BUY':
                            position_side = 'long'
                            entry_px, entry_ts, qty = px, ts, q
                        elif action == 'SELL':
                            position_side = 'short'
                            entry_px, entry_ts, qty = px, ts, q
                        continue
                    # We are in a position; look for opposite to close
                    if position_side == 'long' and action == 'SELL':
                        pnl = (px - entry_px) * qty
                        ret = (px - entry_px) / max(entry_px, 1e-9)
                        rows.append({
                            'symbol': symbol,
                            'side': position_side,
                            'qty': int(qty),
                            'entry_time': entry_ts,
                            'entry_price': float(entry_px),
                            'exit_time': ts,
                            'exit_price': float(px),
                            'pnl': float(pnl),
                            'return_pct': float(ret),
                            'won': bool(pnl > 0),
                        })
                        position_side = None
                        entry_px = entry_ts = qty = None
                    elif position_side == 'short' and action == 'BUY':
                        pnl = (entry_px - px) * qty
                        ret = (entry_px - px) / max(entry_px, 1e-9)
                        rows.append({
                            'symbol': symbol,
                            'side': position_side,
                            'qty': int(qty),
                            'entry_time': entry_ts,
                            'entry_price': float(entry_px),
                            'exit_time': ts,
                            'exit_price': float(px),
                            'pnl': float(pnl),
                            'return_pct': float(ret),
                            'won': bool(pnl > 0),
                        })
                        position_side = None
                        entry_px = entry_ts = qty = None
                # If position remains open at the end, close at last bar close for stats
                if position_side is not None and entry_px is not None and len(df) > 0:
                    last_ts = df.index[-1]
                    last_px = float(df['close'].iloc[-1])
                    if position_side == 'long':
                        pnl = (last_px - entry_px) * qty
                        ret = (last_px - entry_px) / max(entry_px, 1e-9)
                    else:
                        pnl = (entry_px - last_px) * qty
                        ret = (entry_px - last_px) / max(entry_px, 1e-9)
                    rows.append({
                        'symbol': symbol,
                        'side': position_side,
                        'qty': int(qty),
                        'entry_time': entry_ts,
                        'entry_price': float(entry_px),
                        'exit_time': last_ts,
                        'exit_price': float(last_px),
                        'pnl': float(pnl),
                        'return_pct': float(ret),
                        'won': bool(pnl > 0),
                    })
                if rows:
                    trades_df = pd.DataFrame(rows)
        except Exception:
            trades_df = None

        # Compute trades summary metrics
        trades_summary: Dict[str, Any] = {}
        try:
            if trades_df is not None and not trades_df.empty:
                wins_df = trades_df[trades_df.get("pnl", 0) > 0]
                losses_df = trades_df[trades_df.get("pnl", 0) <= 0]
                win_count = int(len(wins_df))
                loss_count = int(len(losses_df))
                gross_profit = float(wins_df.get("pnl", pd.Series(dtype=float)).sum()) if win_count else 0.0
                gross_loss = float(losses_df.get("pnl", pd.Series(dtype=float)).sum()) if loss_count else 0.0
                profit_factor = float(gross_profit / abs(gross_loss)) if loss_count and gross_loss != 0 else (float("inf") if win_count and loss_count == 0 else 0.0)
                avg_win_ret = float(wins_df.get("return_pct", pd.Series(dtype=float)).mean()) if win_count else 0.0
                avg_loss_ret = float(losses_df.get("return_pct", pd.Series(dtype=float)).mean()) if loss_count else 0.0
                trades_summary = {
                    "total_trades": int(len(trades_df)),
                    "wins": win_count,
                    "losses": loss_count,
                    "profit_factor": profit_factor,
                    "avg_win_return_pct": avg_win_ret,
                    "avg_loss_return_pct": avg_loss_ret,
                }
        except Exception:
            trades_summary = {}

        # Persist to ArcticDB
        backtests_lib = self.ac.get_library("backtests", create_if_missing=True)
        try:
            backtests_lib.write(backtest_id, curve_df)
            if trades_df is not None:
                backtests_lib.write(f"{backtest_id}_trades", trades_df)
        except Exception:
            pass

        return {
            "strategy": Path(strategy_filename).stem,
            "symbol": symbol,
            "interval": self._interval_mapping(interval)["alias"],
            "start": str(df.index[0]),
            "end": str(df.index[-1]),
            "initial_capital": cfg.initial_capital,
            "final_equity": float(curve_df["equity"].iloc[-1]) if len(curve_df) else cfg.initial_capital,
            "total_return": total_return,
            "sharpe_ratio": sharpe,
            "num_bars": int(len(curve_df)),
            "backtest_id": backtest_id,
            "trades_summary": trades_summary,
        }
