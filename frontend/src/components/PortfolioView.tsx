import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { 
  TrendingUp, 
  TrendingDown, 
  DollarSign,
  BarChart3,
  RefreshCw,
  AlertCircle
} from 'lucide-react';
import { fetchPortfolioPositions, fetchPortfolioSummary, refreshPortfolioPositions, PortfolioPosition } from '@/lib/api';

interface Position {
  symbol: string;
  assetClass: string;
  quantity: number;
  avgPrice: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnL: number;
  strategy: string;
  side: 'long' | 'short';
  navPercentage: number;
  currency: string;
  pnlPercentage: number;
}

const PortfolioView = () => {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalEquity, setTotalEquity] = useState(0);
  const [baseCurrency, setBaseCurrency] = useState('USD');
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [groupBy, setGroupBy] = useState<'symbol' | 'side' | 'nav'>('symbol');

  // Convert backend position data to frontend format
  const convertBackendPosition = (backendPos: PortfolioPosition): Position => {
    const quantity = backendPos.position; // keep sign; negative for shorts
    const marketValue = Math.abs(quantity * backendPos.marketPrice);
    const unrealizedPnL = (backendPos.marketPrice - backendPos.averageCost) * Math.abs(quantity);
    
    return {
      symbol: backendPos.symbol,
      assetClass: backendPos['asset_class'],
      quantity: quantity,
      avgPrice: backendPos.averageCost,
      currentPrice: backendPos.marketPrice,
      marketValue: marketValue,
      unrealizedPnL: unrealizedPnL,
      strategy: backendPos.strategy || 'Unassigned',
      side: quantity >= 0 ? 'long' : 'short',
      navPercentage: backendPos['% of nav'],
      currency: backendPos.currency,
      pnlPercentage: backendPos['pnl %']
    };
  };

  // Load portfolio data from backend
  const loadPortfolioData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetchPortfolioPositions();
      
      if (response.success && response.data.positions) {
        const convertedPositions = response.data.positions.map(convertBackendPosition);
        setPositions(convertedPositions);
        setTotalEquity(response.data.total_equity);
        setBaseCurrency(response.data.base_currency);
        setLastUpdate(new Date());
      } else {
        setError(response.message || 'Failed to load positions');
      }
    } catch (error) {
      console.error('Failed to load portfolio data:', error);
      setError(error instanceof Error ? error.message : 'Failed to load portfolio data');
    } finally {
      setLoading(false);
    }
  };

  const refreshPositions = async () => {
    try {
      setLoading(true);
      await refreshPortfolioPositions();
      await loadPortfolioData();
    } catch (error) {
      console.error('Failed to refresh positions:', error);
      setError(error instanceof Error ? error.message : 'Failed to refresh positions');
    }
  };

  // Load data on component mount
  useEffect(() => {
    loadPortfolioData();
  }, []);

  const totalMarketValue = positions.reduce((sum, pos) => sum + pos.marketValue, 0);
  const totalUnrealizedPnL = positions.reduce((sum, pos) => sum + pos.unrealizedPnL, 0);
  const longPositions = positions.filter(pos => pos.side === 'long');
  const shortPositions = positions.filter(pos => pos.side === 'short');

  // Sorting/grouping helpers
  const sortedBySymbol = [...positions].sort((a, b) => a.symbol.localeCompare(b.symbol));
  const sortedByNav = [...positions].sort((a, b) => b.navPercentage - a.navPercentage);
  const sideGrouped = {
    longs: [...longPositions].sort((a, b) => a.symbol.localeCompare(b.symbol)),
    shorts: [...shortPositions].sort((a, b) => a.symbol.localeCompare(b.symbol)),
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Portfolio Overview</h2>
        <div />
      </div>

      {/* Portfolio Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Market Value</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{baseCurrency} {totalEquity.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">{positions.length} positions</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Unrealized P&L</CardTitle>
            {totalUnrealizedPnL >= 0 ? 
              <TrendingUp className="h-4 w-4 text-profit" /> : 
              <TrendingDown className="h-4 w-4 text-loss" />
            }
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${totalUnrealizedPnL >= 0 ? 'text-profit' : 'text-loss'}`}>
              {baseCurrency} {totalUnrealizedPnL.toFixed(2)}
            </div>
            <p className="text-xs text-muted-foreground">Current session</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Position Balance</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{longPositions.length}L / {shortPositions.length}S</div>
            <p className="text-xs text-muted-foreground">Long / Short positions</p>
          </CardContent>
        </Card>
      </div>

      {/* Error Display */}
      {error && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-4 w-4" />
              <span>{error}</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Loading State */}
      {loading && positions.length === 0 && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-center gap-2 text-muted-foreground">
              <RefreshCw className="h-4 w-4 animate-spin" />
              <span>Loading portfolio data...</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Current Positions Header (outside of containers) */}
      {!loading && (
        <div className="flex justify-between items-center">
          <h3 className="text-xl font-semibold">Current Positions</h3>
          <div className="flex items-center gap-4">
            <p className="text-sm text-muted-foreground">
              Last updated: {lastUpdate.toLocaleTimeString()}
            </p>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Group by:</span>
              <div className="inline-flex rounded-md border overflow-hidden">
                <button
                  className={`px-3 py-1 ${groupBy === 'symbol' ? 'bg-muted font-medium' : ''}`}
                  onClick={() => setGroupBy('symbol')}
                >
                  Symbol
                </button>
                <button
                  className={`px-3 py-1 border-l ${groupBy === 'side' ? 'bg-muted font-medium' : ''}`}
                  onClick={() => setGroupBy('side')}
                >
                  Side
                </button>
                <button
                  className={`px-3 py-1 border-l ${groupBy === 'nav' ? 'bg-muted font-medium' : ''}`}
                  onClick={() => setGroupBy('nav')}
                >
                  % NAV
                </button>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={refreshPositions} disabled={loading}>
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </div>
      )}

      {/* Positions Table(s) */}
      {!loading && positions.length > 0 && groupBy !== 'side' && (
        <Card>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-2">Symbol</th>
                    <th className="text-left p-2">Asset Class</th>
                    <th className="text-right p-2">Quantity</th>
                    <th className="text-right p-2">Avg Price</th>
                    <th className="text-right p-2">Current Price</th>
                    <th className="text-right p-2">Market Value</th>
                    <th className="text-right p-2">% of NAV</th>
                    <th className="text-right p-2">P&L %</th>
                    <th className="text-left p-2">Strategy</th>
                  </tr>
                </thead>
                <tbody>
                  {(groupBy === 'symbol' ? sortedBySymbol : sortedByNav).map((position, index) => (
                    <tr key={`${position.symbol}-${index}`} className="border-b hover:bg-muted/50">
                      <td className="p-2 font-medium">{position.symbol}</td>
                      <td className="p-2 text-sm text-muted-foreground">{position.assetClass}</td>
                      <td className="text-right p-2">{position.quantity.toLocaleString()}</td>
                      <td className="text-right p-2">{position.currency} {position.avgPrice.toFixed(2)}</td>
                      <td className="text-right p-2">{position.currency} {position.currentPrice.toFixed(2)}</td>
                      <td className="text-right p-2">{position.currency} {position.marketValue.toLocaleString()}</td>
                      <td className="text-right p-2">{position.navPercentage.toFixed(2)}%</td>
                      <td className={`text-right p-2 ${position.pnlPercentage >= 0 ? 'text-profit' : 'text-loss'}`}>{position.pnlPercentage.toFixed(2)}%</td>
                      <td className="p-2">
                        <Badge variant="outline" className="text-xs">{position.strategy}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Side Grouped: Two separate containers stacked vertically */}
      {!loading && positions.length > 0 && groupBy === 'side' && (
        <div className="grid grid-cols-1 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Longs</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-2">Symbol</th>
                      <th className="text-left p-2">Asset Class</th>
                      <th className="text-right p-2">Quantity</th>
                      <th className="text-right p-2">Avg Price</th>
                      <th className="text-right p-2">Current Price</th>
                      <th className="text-right p-2">Market Value</th>
                      <th className="text-right p-2">% of NAV</th>
                      <th className="text-right p-2">P&L %</th>
                      <th className="text-left p-2">Strategy</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sideGrouped.longs.map((position, index) => (
                      <tr key={`long-${position.symbol}-${index}`} className="border-b hover:bg-muted/50">
                        <td className="p-2 font-medium">{position.symbol}</td>
                        <td className="p-2 text-sm text-muted-foreground">{position.assetClass}</td>
                        <td className="text-right p-2">{position.quantity.toLocaleString()}</td>
                        <td className="text-right p-2">{position.currency} {position.avgPrice.toFixed(2)}</td>
                        <td className="text-right p-2">{position.currency} {position.currentPrice.toFixed(2)}</td>
                        <td className="text-right p-2">{position.currency} {position.marketValue.toLocaleString()}</td>
                        <td className="text-right p-2">{position.navPercentage.toFixed(2)}%</td>
                        <td className={`text-right p-2 ${position.pnlPercentage >= 0 ? 'text-profit' : 'text-loss'}`}>{position.pnlPercentage.toFixed(2)}%</td>
                        <td className="p-2">
                          <Badge variant="outline" className="text-xs">{position.strategy}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Shorts</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left p-2">Symbol</th>
                      <th className="text-left p-2">Asset Class</th>
                      <th className="text-right p-2">Quantity</th>
                      <th className="text-right p-2">Avg Price</th>
                      <th className="text-right p-2">Current Price</th>
                      <th className="text-right p-2">Market Value</th>
                      <th className="text-right p-2">% of NAV</th>
                      <th className="text-right p-2">P&L %</th>
                      <th className="text-left p-2">Strategy</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sideGrouped.shorts.map((position, index) => (
                      <tr key={`short-${position.symbol}-${index}`} className="border-b hover:bg-muted/50">
                        <td className="p-2 font-medium">{position.symbol}</td>
                        <td className="p-2 text-sm text-muted-foreground">{position.assetClass}</td>
                        <td className="text-right p-2">{position.quantity.toLocaleString()}</td>
                        <td className="text-right p-2">{position.currency} {position.avgPrice.toFixed(2)}</td>
                        <td className="text-right p-2">{position.currency} {position.currentPrice.toFixed(2)}</td>
                        <td className="text-right p-2">{position.currency} {position.marketValue.toLocaleString()}</td>
                        <td className="text-right p-2">{position.navPercentage.toFixed(2)}%</td>
                        <td className={`text-right p-2 ${position.pnlPercentage >= 0 ? 'text-profit' : 'text-loss'}`}>{position.pnlPercentage.toFixed(2)}%</td>
                        <td className="p-2">
                          <Badge variant="outline" className="text-xs">{position.strategy}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* No Positions State */}
      {!loading && positions.length === 0 && !error && (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-muted-foreground">
              <BarChart3 className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No positions found</p>
              <p className="text-sm">Connect to IB and start trading to see your portfolio</p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default PortfolioView;