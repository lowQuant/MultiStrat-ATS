import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { 
  TrendingUp, 
  TrendingDown, 
  Target,
  AlertTriangle,
  Calendar,
  BarChart3
} from 'lucide-react';

const PerformanceAnalytics = () => {
  const [timeframe, setTimeframe] = useState('1D');
  
  // Mock performance data - replace with API calls
  const performanceMetrics = {
    totalReturn: 5.67,
    sharpeRatio: 1.43,
    maxDrawdown: -2.85,
    winRate: 68.5,
    profitFactor: 1.85,
    avgWin: 127.50,
    avgLoss: -89.25,
    totalTrades: 234,
    winningTrades: 160,
    losingTrades: 74
  };

  const strategyPerformance = [
    {
      name: 'Mean Reversion SPY',
      return: 8.24,
      sharpe: 1.67,
      maxDD: -1.95,
      trades: 89
    },
    {
      name: 'Momentum QQQ',
      return: 3.12,
      sharpe: 1.23,
      maxDD: -3.45,
      trades: 67
    },
    {
      name: 'Pairs Trade Tech',
      return: 4.89,
      sharpe: 1.38,
      maxDD: -2.12,
      trades: 78
    }
  ];

  const riskMetrics = {
    var95: -1250.00,
    var99: -2150.00,
    expectedShortfall: -2750.00,
    beta: 0.85,
    correlation: 0.72
  };

  const recentTrades = [
    { symbol: 'SPY', pnl: 125.50, return: 0.29, date: '2024-01-20' },
    { symbol: 'QQQ', pnl: -45.25, return: -0.13, date: '2024-01-20' },
    { symbol: 'AAPL', pnl: 78.90, return: 0.45, date: '2024-01-19' },
    { symbol: 'MSFT', pnl: 92.15, return: 0.27, date: '2024-01-19' },
    { symbol: 'SPY', pnl: -23.60, return: -0.06, date: '2024-01-18' }
  ];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Performance Analytics</h2>
        <Select value={timeframe} onValueChange={setTimeframe}>
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1D">1 Day</SelectItem>
            <SelectItem value="1W">1 Week</SelectItem>
            <SelectItem value="1M">1 Month</SelectItem>
            <SelectItem value="3M">3 Months</SelectItem>
            <SelectItem value="1Y">1 Year</SelectItem>
            <SelectItem value="ALL">All Time</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Key Performance Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Return</CardTitle>
            <TrendingUp className="h-4 w-4 text-profit" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-profit">
              {performanceMetrics.totalReturn.toFixed(2)}%
            </div>
            <p className="text-xs text-muted-foreground">Since inception</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Sharpe Ratio</CardTitle>
            <Target className="h-4 w-4 text-info" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{performanceMetrics.sharpeRatio}</div>
            <p className="text-xs text-muted-foreground">Risk-adjusted return</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Max Drawdown</CardTitle>
            <TrendingDown className="h-4 w-4 text-loss" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-loss">
              {performanceMetrics.maxDrawdown.toFixed(2)}%
            </div>
            <p className="text-xs text-muted-foreground">Worst peak-to-trough</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Win Rate</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{performanceMetrics.winRate.toFixed(1)}%</div>
            <p className="text-xs text-muted-foreground">
              {performanceMetrics.winningTrades}/{performanceMetrics.totalTrades} trades
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Strategy Performance Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle>Strategy Performance</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-2">Strategy</th>
                  <th className="text-right p-2">Return (%)</th>
                  <th className="text-right p-2">Sharpe Ratio</th>
                  <th className="text-right p-2">Max DD (%)</th>
                  <th className="text-right p-2">Trades</th>
                </tr>
              </thead>
              <tbody>
                {strategyPerformance.map((strategy, index) => (
                  <tr key={index} className="border-b hover:bg-muted/50">
                    <td className="p-2 font-medium">{strategy.name}</td>
                    <td className={`text-right p-2 ${strategy.return >= 0 ? 'text-profit' : 'text-loss'}`}>
                      {strategy.return.toFixed(2)}%
                    </td>
                    <td className="text-right p-2">{strategy.sharpe.toFixed(2)}</td>
                    <td className="text-right p-2 text-loss">{strategy.maxDD.toFixed(2)}%</td>
                    <td className="text-right p-2">{strategy.trades}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Risk Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Risk Metrics
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between">
              <span>Value at Risk (95%)</span>
              <span className="font-mono text-loss">${riskMetrics.var95.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span>Value at Risk (99%)</span>
              <span className="font-mono text-loss">${riskMetrics.var99.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span>Expected Shortfall</span>
              <span className="font-mono text-loss">${riskMetrics.expectedShortfall.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span>Market Beta</span>
              <span className="font-mono">{riskMetrics.beta}</span>
            </div>
            <div className="flex justify-between">
              <span>Market Correlation</span>
              <span className="font-mono">{riskMetrics.correlation}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5" />
              Recent Trades P&L
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {recentTrades.map((trade, index) => (
              <div key={index} className="flex justify-between items-center p-2 hover:bg-muted/50 rounded">
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{trade.symbol}</Badge>
                  <span className="text-sm text-muted-foreground">{trade.date}</span>
                </div>
                <div className="text-right">
                  <div className={`font-mono ${trade.pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                    ${trade.pnl.toFixed(2)}
                  </div>
                  <div className={`text-xs ${trade.return >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {trade.return.toFixed(2)}%
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Additional Performance Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Profit Factor</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{performanceMetrics.profitFactor}</div>
            <p className="text-xs text-muted-foreground">Gross profit / Gross loss</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Average Win</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-profit">
              ${performanceMetrics.avgWin.toFixed(2)}
            </div>
            <p className="text-xs text-muted-foreground">Per winning trade</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Average Loss</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-loss">
              ${performanceMetrics.avgLoss.toFixed(2)}
            </div>
            <p className="text-xs text-muted-foreground">Per losing trade</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default PerformanceAnalytics;