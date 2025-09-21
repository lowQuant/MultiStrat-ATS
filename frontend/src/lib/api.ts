/**
 * API utility functions for MATS backend communication
 */

const API_BASE_URL = 'http://localhost:8000';

export interface PortfolioPosition {
  symbol: string;
  'asset class': string;
  position: number;
  '% of nav': number;
  currency: string;
  marketPrice: number;
  averageCost: number;
  'pnl %': number;
  strategy: string;
}

// =============================
// Strategies API
// =============================

export interface StrategiesResponse {
  strategies: Array<{
    strategy_symbol: string;
    filename: string;
    target_weight?: number | null;
    params?: string | null;
    running?: boolean;
  }>;
  discovered_strategies: string[];
  active_only: boolean;
}

export async function fetchStrategies(active_only = false): Promise<StrategiesResponse> {
  const response = await fetch(`${API_BASE_URL}/api/strategies?active_only=${active_only ? 'true' : 'false'}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Failed to fetch strategies: ${response.status} ${text}`);
  }
  return response.json();
}

// Async ingest with progress
export interface StartIngestResponse { success: boolean; ingest_id: string }
export interface IngestProgressResponse {
  success: boolean;
  ingest_id: string;
  status: 'pending' | 'running' | 'done' | 'error' | string;
  progress: number;
  message: string;
  data?: IngestResponse['data'] | null;
  error?: string | null;
}

export async function startIngestOHLCV(payload: IngestRequest): Promise<StartIngestResponse> {
  const response = await fetch(`${API_BASE_URL}/backtest/ingest/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Ingest start failed: ${response.status} ${text}`);
  }
  return response.json();
}

export async function getIngestProgress(ingest_id: string): Promise<IngestProgressResponse> {
  const response = await fetch(`${API_BASE_URL}/backtest/ingest/progress/${encodeURIComponent(ingest_id)}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Ingest progress failed: ${response.status} ${text}`);
  }
  return response.json();
}

export interface PortfolioResponse {
  success: boolean;
  message: string;
  data: {
    positions: PortfolioPosition[];
    total_positions: number;
    total_equity: number;
    base_currency: string;
  };
}

export interface PortfolioSummaryResponse {
  success: boolean;
  message: string;
  data: {
    total_positions: number;
    total_realized_pnl: number;
    total_unrealized_pnl: number;
    total_pnl: number;
    positions: any[];
    last_updated: string;
  };
}

/**
 * Fetch portfolio positions from backend
 */
export async function fetchPortfolioPositions(): Promise<PortfolioResponse> {
  const response = await fetch(`${API_BASE_URL}/portfolio/positions`);
  if (!response.ok) {
    throw new Error(`Failed to fetch positions: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Fetch portfolio summary from backend
 */
export async function fetchPortfolioSummary(): Promise<PortfolioSummaryResponse> {
  const response = await fetch(`${API_BASE_URL}/portfolio/summary`);
  if (!response.ok) {
    throw new Error(`Failed to fetch portfolio summary: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Refresh portfolio positions (clears caches)
 */
export async function refreshPortfolioPositions(): Promise<{ success: boolean; message: string }> {
  const response = await fetch(`${API_BASE_URL}/portfolio/refresh-positions`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to refresh positions: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Fetch FX rates information
 */
export async function fetchFXRates(): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/portfolio/fx-rates`);
  if (!response.ok) {
    throw new Error(`Failed to fetch FX rates: ${response.statusText}`);
  }
  return response.json();
}

// =============================
// Backtest API
// =============================

export type Interval = 'minute' | 'hourly' | 'daily';

export interface RunBacktestRequest {
  strategy_filename: string; // e.g., "tqqq_strategy.py"
  symbol: string;            // e.g., "TQQQ"
  start_date: string;        // ISO date, e.g., "2024-09-03"
  end_date: string;          // ISO date
  interval?: Interval;       // default minute
  initial_capital?: number;  // default 100000
  commission_per_share?: number; // default 0.005
  slippage_bps?: number;     // default 0
  params?: Record<string, any>;
}

export interface RunBacktestResponse {
  success: boolean;
  results: {
    strategy: string;
    symbol: string;
    interval: Interval;
    start: string;
    end: string;
    initial_capital: number;
    final_equity: number;
    total_return: number;
    sharpe_ratio: number;
    num_bars: number;
    backtest_id: string;
  };
}

export async function runBacktest(payload: RunBacktestRequest): Promise<RunBacktestResponse> {
  const response = await fetch(`${API_BASE_URL}/backtest/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Backtest failed: ${response.status} ${text}`);
  }
  return response.json();
}

export interface IngestRequest {
  symbol: string;
  start_date: string;
  end_date: string;
  interval?: Interval;
}

export interface IngestResponse {
  success: boolean;
  message: string;
  data: {
    symbol: string;
    interval: Interval;
    rows: number;
    start: string | null;
    end: string | null;
    library: string; // 'ohlcv'
    symbol_key: string; // e.g., 'tqqq_minute'
  };
}

export async function ingestOHLCV(payload: IngestRequest): Promise<IngestResponse> {
  const response = await fetch(`${API_BASE_URL}/backtest/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Ingest failed: ${response.status} ${text}`);
  }
  return response.json();
}

export interface BacktestPoint {
  timestamp: string;
  equity: number;
}

export interface BacktestResultResponse {
  success: boolean;
  backtest_id: string;
  points: BacktestPoint[];
}

export async function getBacktestResult(backtest_id: string): Promise<BacktestResultResponse> {
  const response = await fetch(`${API_BASE_URL}/backtest/result/${encodeURIComponent(backtest_id)}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Result fetch failed: ${response.status} ${text}`);
  }
  return response.json();
}

export async function getStrategyParams(strategy_filename: string): Promise<{ success: boolean; strategy: string; params: Record<string, any>}> {
  const response = await fetch(`${API_BASE_URL}/backtest/strategy-params/${encodeURIComponent(strategy_filename)}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Param fetch failed: ${response.status} ${text}`);
  }
  return response.json();
}

export interface BacktestTradeRow {
  trade_id: string;
  symbol: string;
  side: 'long' | 'short' | string;
  qty: number;
  entry_time: string;
  entry_price: number;
  exit_time: string;
  exit_price: number;
  pnl: number;
  return_pct: number;
  won: boolean;
}

export interface BacktestTradesResponse {
  success: boolean;
  backtest_id: string;
  summary: {
    total_trades: number;
    wins: number;
    losses: number;
    profit_factor: number;
    avg_win_return_pct: number;
    avg_loss_return_pct: number;
  } | Record<string, never>;
  trades: BacktestTradeRow[];
}

export async function getBacktestTrades(backtest_id: string): Promise<BacktestTradesResponse> {
  const response = await fetch(`${API_BASE_URL}/backtest/trades/${encodeURIComponent(backtest_id)}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Trades fetch failed: ${response.status} ${text}`);
  }
  return response.json();
}

// ---- IB historical download with progress ----
export interface StartIbDownloadRequest {
  symbol: string;
  interval: Interval;
  start_date: string;
  end_date: string; // allow 'today'
  use_rth?: boolean;
  what_to_show?: 'TRADES' | 'MIDPOINT' | 'BID' | 'ASK' | string;
  chunk?: string; // e.g., '20 D'
  save?: boolean; // default true
}

export interface StartIbDownloadResponse {
  success: boolean;
  download_id: string;
}

export interface IbDownloadProgress {
  success: boolean;
  download_id: string;
  status: 'pending' | 'running' | 'done' | 'error' | string;
  progress: number; // 0..100
  message: string;
  rows: number;
  result_key?: string | null;
  error?: string | null;
}

export async function startIbDownload(req: StartIbDownloadRequest): Promise<StartIbDownloadResponse> {
  const response = await fetch(`${API_BASE_URL}/data/ib/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol: req.symbol,
      interval: req.interval,
      start_date: req.start_date,
      end_date: req.end_date,
      use_rth: req.use_rth ?? true,
      what_to_show: req.what_to_show ?? 'TRADES',
      chunk: req.chunk,
      save: req.save ?? true,
    })
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Start download failed: ${response.status} ${text}`);
  }
  return response.json();
}

export async function getIbDownloadProgress(download_id: string): Promise<IbDownloadProgress> {
  const response = await fetch(`${API_BASE_URL}/data/ib/progress/${encodeURIComponent(download_id)}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Progress fetch failed: ${response.status} ${text}`);
  }
  return response.json();
}

export async function getIbDownloadResult(download_id: string): Promise<IbDownloadProgress> {
  const response = await fetch(`${API_BASE_URL}/data/ib/result/${encodeURIComponent(download_id)}`);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Result fetch failed: ${response.status} ${text}`);
  }
  return response.json();
}
