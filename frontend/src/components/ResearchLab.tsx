import React, { useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { FlaskConical, Play, Download } from 'lucide-react';
import { runBacktest, getBacktestResult, getBacktestTrades, startIngestOHLCV, getIngestProgress, getStrategies as fetchStrategies, type Interval, type BacktestPoint, type BacktestTradeRow, type IngestResponse, type StrategiesResponse } from '@/lib/api';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart';
import { Line, LineChart, XAxis, YAxis, CartesianGrid } from 'recharts';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Progress } from '@/components/ui/progress';

const ResearchLab: React.FC = () => {
  const [symbol, setSymbol] = useState('TQQQ');
  const [strategyFile, setStrategyFile] = useState('tqqq_strategy.py');
  const [interval, setInterval] = useState<Interval>('minute');
  const [startDate, setStartDate] = useState<string>(() => new Date(Date.now() - 3 * 24 * 3600 * 1000).toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(false);
  const [ingestInfo, setIngestInfo] = useState<IngestResponse['data'] | null>(null);
  const [runInfo, setRunInfo] = useState<any | null>(null);
  const [equityPoints, setEquityPoints] = useState<BacktestPoint[]>([]);
  const [trades, setTrades] = useState<BacktestTradeRow[]>([]);
  const [tradesSummary, setTradesSummary] = useState<any | null>(null);
  const [ingestId, setIngestId] = useState<string | null>(null);
  const [ingestPct, setIngestPct] = useState<number>(0);
  const [ingestMsg, setIngestMsg] = useState<string>('');
  const [ingestStatus, setIngestStatus] = useState<string>('idle');
  const [ingestTimer, setIngestTimer] = useState<number | null>(null);
  // toggles removed; rely on date pickers only
  const [discovered, setDiscovered] = useState<string[]>([]);
  const [strategiesMeta, setStrategiesMeta] = useState<StrategiesResponse['strategies']>([]);
  const [errorMsg, setErrorMsg] = useState<string>('');

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetchStrategies(false);
        setDiscovered(res.discovered_strategies || []);
        setStrategiesMeta(res.strategies || []);
        // If current strategyFile is empty, pick the first discovered
        if ((!strategyFile || strategyFile.trim().length === 0) && res.discovered_strategies?.length) {
          setStrategyFile(res.discovered_strategies[0]);
        }
      } catch (e) {
        console.error(e);
      }
    };
    load();
  }, []);

  const canRun = useMemo(() => {
    return symbol.trim() && strategyFile.trim() && startDate && endDate;
  }, [symbol, strategyFile, startDate, endDate]);

  const onIngest = async () => {
    try {
      setLoading(true);
      setIngestStatus('starting');
      setIngestPct(0);
      setIngestMsg('');
      const { ingest_id } = await startIngestOHLCV({ symbol, start_date: startDate, end_date: endDate, interval });
      setIngestId(ingest_id);
      setIngestStatus('running');
      // Start polling
      const timer = window.setInterval(async () => {
        try {
          const p = await getIngestProgress(ingest_id);
          setIngestPct(p.progress || 0);
          setIngestMsg(p.message || '');
          setIngestStatus(p.status || 'running');
          if (p.status === 'done') {
            setIngestInfo(p.data || null);
            window.clearInterval(timer);
            setIngestTimer(null);
          } else if (p.status === 'error') {
            window.clearInterval(timer);
            setIngestTimer(null);
          }
        } catch (e) {
          // stop polling on error
          window.clearInterval(timer);
          setIngestTimer(null);
          setIngestStatus('error');
        }
      }, 1000);
      setIngestTimer(timer);
    } catch (e) {
      console.error(e);
      setIngestStatus('error');
    } finally {
      setLoading(false);
    }
  };

  const onRun = async () => {
    try {
      setLoading(true);
      setErrorMsg('');
      const res = await runBacktest({
        strategy_filename: strategyFile,
        symbol,
        start_date: startDate,
        end_date: endDate,
        interval,
      });
      setRunInfo(res.results);
      // Fetch curve for chart
      const curve = await getBacktestResult(res.results.backtest_id);
      setEquityPoints(curve.points || []);
      // Fetch trades and summary
      try {
        const t = await getBacktestTrades(res.results.backtest_id);
        setTrades(t.trades || []);
        setTradesSummary(t.summary || null);
      } catch (e) {
        setTrades([]);
        setTradesSummary(null);
      }
    } catch (e: any) {
      console.error(e);
      const msg = typeof e?.message === 'string' ? e.message : 'Backtest failed';
      setErrorMsg(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5" />
            <CardTitle>Research Lab</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-5">
            <div className="grid gap-2">
              <Label htmlFor="strategyFile">Strategy File</Label>
              {discovered && discovered.length > 0 ? (
                <Select value={strategyFile} onValueChange={(v) => setStrategyFile(v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a strategy file" />
                  </SelectTrigger>
                  <SelectContent>
                    {discovered.map((f) => (
                      <SelectItem key={f} value={f}>{f}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input id="strategyFile" value={strategyFile} onChange={e => setStrategyFile(e.target.value)} placeholder="tqqq_strategy.py" />
              )}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="symbol">Symbol</Label>
              <Input id="symbol" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} placeholder="TQQQ" />
            </div>
            <div className="grid gap-2">
              <Label>Interval</Label>
              <Select value={interval} onValueChange={(v) => setInterval(v as Interval)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="minute">Minute</SelectItem>
                  <SelectItem value="hourly">Hourly</SelectItem>
                  <SelectItem value="daily">Daily</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="start">Start</Label>
              <Input id="start" type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="end">End</Label>
              <Input id="end" type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
            </div>
          </div>

          <div className="flex gap-2 mt-4">
            <Button onClick={onIngest} disabled={loading || !symbol} variant="outline">
              <Download className="h-4 w-4 mr-2" /> Ingest OHLCV
            </Button>
            <Button onClick={onRun} disabled={loading || !canRun}>
              <Play className="h-4 w-4 mr-2" /> Run Backtest
            </Button>
          </div>

          {errorMsg && (
            <div className="mt-2 text-sm text-red-600">
              {errorMsg}
            </div>
          )}

          {/* Ingest info */}
          {ingestInfo && (
            <div className="mt-4 text-sm text-muted-foreground">
              <div>Ingested/Available: <b>{ingestInfo.symbol_key}</b> ({ingestInfo.rows} rows)</div>
              <div>Range: {ingestInfo.start} → {ingestInfo.end}</div>
            </div>
          )}

          {/* Ingest progress */}
          {ingestStatus !== 'idle' && ingestStatus !== 'starting' && (
            <div className="mt-4">
              <Label>Ingest Progress</Label>
              <div className="flex items-center gap-4 mt-2">
                <Progress value={ingestPct} className="w-[300px]" />
                <div className="text-sm text-muted-foreground">{ingestMsg}</div>
              </div>
            </div>
          )}

          {/* Backtest summary */}
          {runInfo && (
            <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card>
                <CardHeader><CardTitle className="text-sm">Return</CardTitle></CardHeader>
                <CardContent>
                  <div className={`text-xl font-semibold ${runInfo.total_return >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {(runInfo.total_return * 100).toFixed(2)}%
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-sm">Sharpe</CardTitle></CardHeader>
                <CardContent>
                  <div className="text-xl font-semibold">{runInfo.sharpe_ratio.toFixed(2)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-sm">Final Equity</CardTitle></CardHeader>
                <CardContent>
                  <div className="text-xl font-semibold">${runInfo.final_equity.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Equity curve */}
          {equityPoints.length > 0 && (
            <div className="mt-6">
              <ChartContainer config={{ equity: { label: 'Equity', color: '#0ea5e9' } }}>
                <LineChart data={equityPoints} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" tick={{ fontSize: 10 }} minTickGap={24} />
                  <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Line type="monotone" dataKey="equity" stroke="var(--color-equity)" dot={false} strokeWidth={1.5} />
                </LineChart>
              </ChartContainer>
            </div>
          )}

          {/* Trades summary + table */}
          {tradesSummary && (
            <div className="mt-6 grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card>
                <CardHeader><CardTitle className="text-sm">Total Trades</CardTitle></CardHeader>
                <CardContent><div className="text-xl font-semibold">{tradesSummary.total_trades}</div></CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-sm">Wins / Losses</CardTitle></CardHeader>
                <CardContent><div className="text-xl font-semibold">{tradesSummary.wins} / {tradesSummary.losses}</div></CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-sm">Profit Factor</CardTitle></CardHeader>
                <CardContent><div className="text-xl font-semibold">{Number(tradesSummary.profit_factor).toFixed(2)}</div></CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-sm">Avg Win / Loss Return</CardTitle></CardHeader>
                <CardContent>
                  <div className="text-xl font-semibold">{(Number(tradesSummary.avg_win_return_pct)*100).toFixed(2)}% / {(Number(tradesSummary.avg_loss_return_pct)*100).toFixed(2)}%</div>
                </CardContent>
              </Card>
            </div>
          )}

          {trades && trades.length > 0 && (
            <div className="mt-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time In</TableHead>
                    <TableHead>Side</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Entry</TableHead>
                    <TableHead className="text-right">Exit</TableHead>
                    <TableHead className="text-right">PnL</TableHead>
                    <TableHead className="text-right">Return</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {trades.map((tr) => (
                    <TableRow key={tr.trade_id}>
                      <TableCell>{tr.entry_time}</TableCell>
                      <TableCell className={tr.won ? 'text-profit' : 'text-loss'}>{tr.side}</TableCell>
                      <TableCell className="text-right">{tr.qty}</TableCell>
                      <TableCell className="text-right">{tr.entry_price.toFixed(2)}</TableCell>
                      <TableCell className="text-right">{tr.exit_price.toFixed(2)}</TableCell>
                      <TableCell className={`text-right ${tr.pnl >= 0 ? 'text-profit' : 'text-loss'}`}>{tr.pnl.toFixed(2)}</TableCell>
                      <TableCell className={`text-right ${tr.won ? 'text-profit' : 'text-loss'}`}>{(tr.return_pct*100).toFixed(2)}%</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {/* Placeholder for future: strategy parameters */}
          <div className="mt-6 text-xs text-muted-foreground">
            Strategy parameters loading/saving will be added here (ArcticDB-backed). For now, defaults are used.
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ResearchLab;
