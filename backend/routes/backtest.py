"""
Backtest routes
- Run a backtest for a given strategy
- Ingest historical OHLCV into ArcticDB (ohlcv library) for a symbol/interval
- Fetch saved backtest results (equity curve)
- Placeholder: fetch strategy parameters (for future UI)
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backtest.backtest_manager import BacktestManager, BacktestConfig
from core.arctic_manager import get_ac

# Optional linkage to the global StrategyManager if needed in the future
strategy_manager = None


def set_strategy_manager(sm):
    global strategy_manager
    strategy_manager = sm


def get_backtest_manager() -> BacktestManager:
    # Lazily create a BacktestManager using the same ArcticDB client and StrategyManager as the app
    ac = strategy_manager.ac if strategy_manager and getattr(strategy_manager, "ac", None) else get_ac()
    return BacktestManager(ac=ac, strategy_manager=strategy_manager)


router = APIRouter(prefix="/backtest", tags=["backtest"])


class RunBacktestRequest(BaseModel):
    strategy_filename: str = Field(..., example="tqqq_strategy.py")
    symbol: str = Field(..., example="TQQQ")
    start_date: str = Field(..., example="2024-09-03")
    end_date: str = Field(..., example="2024-09-06")
    interval: str = Field("minute", description="minute | hourly | daily")
    initial_capital: float = 100_000.0
    commission_per_share: float = 0.005
    slippage_bps: float = 0.0
    params: Optional[Dict[str, Any]] = None


class IngestRequest(BaseModel):
    symbol: str = Field(..., example="TQQQ")
    start_date: str = Field(..., example="2024-09-01")
    end_date: str = Field(..., example="2024-09-10")
    interval: str = Field("minute", description="minute | hourly | daily")


@router.post("/run")
async def run_backtest(req: RunBacktestRequest):
    try:
        bm = get_backtest_manager()
        cfg = BacktestConfig(
            initial_capital=req.initial_capital,
            commission_per_share=req.commission_per_share,
            slippage_bps=req.slippage_bps,
        )
        res = await bm.run_backtest(
            strategy_filename=req.strategy_filename,
            symbol=req.symbol,
            start_date=req.start_date,
            end_date=req.end_date,
            interval=req.interval,
            cfg=cfg,
        )
        return {"success": True, "results": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


@router.post("/ingest")
async def ingest_ohlcv(req: IngestRequest):
    try:
        bm = get_backtest_manager()
        stats = await bm.ensure_data(symbol=req.symbol, start_date=req.start_date, end_date=req.end_date, interval=req.interval)
        return {"success": True, "message": "Data ingested", "data": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


# -------- Asynchronous ingest with progress (for frontend progress bar) --------
_ingest_tasks: Dict[str, Dict[str, Any]] = {}


@router.post("/ingest/start")
async def start_ingest_ohlcv(req: IngestRequest):
    try:
        bm = get_backtest_manager()
        ingest_id = uuid.uuid4().hex
        _ingest_tasks[ingest_id] = {
            "status": "pending",
            "progress": 0.0,
            "message": "queued",
            "data": None,
            "error": None,
        }

        def progress_cb(pct: float, msg: str):
            t = _ingest_tasks.get(ingest_id)
            if t is not None:
                t["progress"] = float(pct)
                t["message"] = str(msg)
                if pct < 100.0:
                    t["status"] = "running"

        async def runner():
            try:
                _ingest_tasks[ingest_id]["status"] = "running"
                stats = await bm.ensure_data(symbol=req.symbol, start_date=req.start_date, end_date=req.end_date, interval=req.interval, progress_cb=progress_cb)
                _ingest_tasks[ingest_id]["data"] = stats
                _ingest_tasks[ingest_id]["status"] = "done"
                _ingest_tasks[ingest_id]["progress"] = 100.0
                _ingest_tasks[ingest_id]["message"] = f"Completed with {stats['rows']} rows"
            except Exception as e:
                _ingest_tasks[ingest_id]["status"] = "error"
                _ingest_tasks[ingest_id]["error"] = str(e)
                _ingest_tasks[ingest_id]["message"] = "failed"

        asyncio.create_task(runner())
        return {"success": True, "ingest_id": ingest_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start ingestion: {e}")


@router.get("/ingest/progress/{ingest_id}")
async def get_ingest_progress(ingest_id: str):
    t = _ingest_tasks.get(ingest_id)
    if not t:
        raise HTTPException(status_code=404, detail="Ingest job not found")
    return {
        "success": True,
        "ingest_id": ingest_id,
        "status": t.get("status"),
        "progress": t.get("progress", 0.0),
        "message": t.get("message", ""),
        "data": t.get("data"),
        "error": t.get("error"),
    }


@router.get("/result/{backtest_id}")
async def get_backtest_result(backtest_id: str):
    try:
        ac = strategy_manager.ac if strategy_manager and getattr(strategy_manager, "ac", None) else get_ac()
        lib = ac.get_library("backtests", create_if_missing=True)
        if not lib.has_symbol(backtest_id):
            raise HTTPException(status_code=404, detail="Backtest result not found")
        df = lib.read(backtest_id).data
        df = df.reset_index().rename(columns={"index": "timestamp"}) if "timestamp" not in df.columns else df
        points = [
            {"timestamp": (row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"])),
             "equity": float(row["equity"]) }
            for _, row in df.iterrows()
        ]
        return {"success": True, "backtest_id": backtest_id, "points": points}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch result: {e}")


@router.get("/trades/{backtest_id}")
async def get_backtest_trades(backtest_id: str):
    try:
        ac = strategy_manager.ac if strategy_manager and getattr(strategy_manager, "ac", None) else get_ac()
        lib = ac.get_library("backtests", create_if_missing=True)
        trades_symbol = f"{backtest_id}_trades"
        if not lib.has_symbol(trades_symbol):
            # Return empty trades instead of 404
            return {"success": True, "backtest_id": backtest_id, "summary": {}, "trades": []}
        df = lib.read(trades_symbol).data
        # Compute summary
        try:
            wins = df[df["won"]]
            losses = df[~df["won"]]
            win_count = int(len(wins))
            loss_count = int(len(losses))
            gross_profit = float(wins["pnl"].sum()) if win_count else 0.0
            gross_loss = float(losses["pnl"].sum()) if loss_count else 0.0
            profit_factor = float(gross_profit / abs(gross_loss)) if loss_count and gross_loss != 0 else (float("inf") if win_count and loss_count == 0 else 0.0)
            avg_win_ret = float(wins["return_pct"].mean()) if win_count else 0.0
            avg_loss_ret = float(losses["return_pct"].mean()) if loss_count else 0.0
            summary = {
                "total_trades": int(win_count + loss_count),
                "wins": win_count,
                "losses": loss_count,
                "profit_factor": profit_factor,
                "avg_win_return_pct": avg_win_ret,
                "avg_loss_return_pct": avg_loss_ret,
            }
        except Exception:
            summary = {}

        # Serialize trades rows
        trades = []
        for _, row in df.reset_index(drop=True).iterrows():
            trades.append({
                "trade_id": str(row.get("trade_id")),
                "symbol": str(row.get("symbol")),
                "side": str(row.get("side")),
                "qty": int(row.get("qty", 0)),
                "entry_time": row.get("entry_time").isoformat() if hasattr(row.get("entry_time"), "isoformat") else str(row.get("entry_time")),
                "entry_price": float(row.get("entry_price", 0.0)),
                "exit_time": row.get("exit_time").isoformat() if hasattr(row.get("exit_time"), "isoformat") else str(row.get("exit_time")),
                "exit_price": float(row.get("exit_price", 0.0)),
                "pnl": float(row.get("pnl", 0.0)),
                "return_pct": float(row.get("return_pct", 0.0)),
                "won": bool(row.get("won", False)),
            })
        return {"success": True, "backtest_id": backtest_id, "summary": summary, "trades": trades}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch trades: {e}")


@router.get("/strategy-params/{strategy_filename}")
async def get_strategy_params(strategy_filename: str):
    """Placeholder endpoint for fetching strategy parameters. Returns empty for now."""
    return {"success": True, "strategy": strategy_filename, "params": {}}
