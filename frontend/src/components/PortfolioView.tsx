import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { 
  TrendingUp, 
  TrendingDown, 
  DollarSign,
  BarChart3,
  RefreshCw,
  AlertCircle,
  MoreHorizontal,
  Trash2,
  ArrowLeft
} from 'lucide-react';
import { 
  fetchPortfolioPositions,
  refreshPortfolioPositions,
  getStrategies as fetchStrategies,
  assignPortfolioStrategy,
  deletePortfolioPosition,
  PortfolioPosition,
  StrategiesResponse
} from '@/lib/api';
import FutureChart from './FutureChart';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useToast } from '@/components/ui/use-toast';

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
  exchange?: string;
  contract?: string;
  conId?: number;
}

const PortfolioView = () => {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalEquity, setTotalEquity] = useState(0);
  const [baseCurrency, setBaseCurrency] = useState('USD');
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [groupBy, setGroupBy] = useState<'symbol' | 'side' | 'nav'>('symbol');
  const [strategies, setStrategies] = useState<string[]>([]);
  const [assigningKey, setAssigningKey] = useState<string | null>(null);
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);
  const { toast } = useToast();

  const getAssignKey = (position: Position) => `${position.symbol}-${position.assetClass}-${position.strategy}`;

  // Convert backend position data to frontend format
  const convertBackendPosition = (backendPos: PortfolioPosition): Position => {
    const quantity = backendPos.position; // keep sign; negative for shorts
    const marketValue = Math.abs(quantity * backendPos.marketPrice);
    const unrealizedPnL = (backendPos.marketPrice - backendPos.averageCost) * quantity;
    
    return {
      symbol: backendPos.symbol,
      assetClass: backendPos['asset_class'],
      quantity: quantity,
      avgPrice: backendPos.averageCost,
      currentPrice: backendPos.marketPrice,
      marketValue: marketValue,
      unrealizedPnL: unrealizedPnL,
      strategy: backendPos.strategy || 'Discretionary',
      side: quantity >= 0 ? 'long' : 'short',
      navPercentage: backendPos['% of nav'],
      currency: backendPos.currency,
      pnlPercentage: backendPos['pnl %'],
      exchange: backendPos.exchange,
      contract: backendPos.contract,
      conId: backendPos.conId
    };
  };

  // Load portfolio data from backend
  const loadPortfolioData = useCallback(async () => {
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
  }, []);

  const loadStrategies = useCallback(async () => {
    try {
      const response: StrategiesResponse = await fetchStrategies(false);
      const strategySymbols = response.strategies
        .map((item) => item.strategy_symbol)
        .filter((sym): sym is string => Boolean(sym))
        .sort();
      setStrategies(strategySymbols);
    } catch (err) {
      console.error('Failed to load strategies', err);
    }
  }, []);

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

  const handleStrategyAssignment = async (position: Position, nextStrategy: string) => {
    if (nextStrategy === position.strategy) {
      return;
    }

    const key = getAssignKey(position);
    setAssigningKey(key);
    try {
      await assignPortfolioStrategy({
        symbol: position.symbol,
        asset_class: position.assetClass,
        target_strategy: nextStrategy,
        current_strategy: position.strategy === 'Discretionary' ? null : position.strategy,
      });

      toast({
        title: 'Strategy updated',
        description: `${position.symbol} assigned to ${nextStrategy}`,
      });

      await loadPortfolioData();
    } catch (err) {
      console.error('Failed to assign strategy', err);
      const message = err instanceof Error ? err.message : 'Failed to assign strategy';
      setError(message);
      toast({
        title: 'Assignment failed',
        description: message,
        variant: 'destructive',
      });
    } finally {
      setAssigningKey(null);
    }
  };

  const handleDeletePosition = async (position: Position) => {
    if (!confirm(`Are you sure you want to delete position: ${position.symbol} (${position.strategy})?`)) {
      return;
    }

    try {
      setLoading(true);
      await deletePortfolioPosition(
        position.symbol,
        position.assetClass,
        position.strategy
      );

      toast({
        title: 'Position deleted',
        description: `${position.symbol} (${position.strategy}) removed from portfolio`,
      });

      await loadPortfolioData();
    } catch (err) {
      console.error('Failed to delete position', err);
      toast({
        title: 'Delete failed',
        description: err instanceof Error ? err.message : 'Failed to delete position',
        variant: 'destructive',
      });
      setLoading(false);
    }
  };

  const getTradingViewSymbol = (position: Position) => {
    const { symbol, assetClass, currency } = position;
    
    // Handle Futures
    // IBKR sends 'FUT', but helper might send 'Future' if changed later. checking both just in case, 
    // though currently it is 'FUT'
    if (assetClass === 'FUT' || assetClass === 'Future') {
      // Append 1! for continuous contract (TradingView convention)
      // This distinguishes cases like MBT (stock) vs MBT1! (future)
      return `${symbol}1!`;
    }
    
    // Handle Forex
    if (assetClass === 'CASH' || assetClass === 'Forex') {
      // Construct pair: e.g. EUR + USD -> EURUSD
      if (currency && currency !== symbol) {
        return `${symbol}${currency}`;
      }
    }
    
    // Handle Crypto
    if (assetClass === 'CRYPTO' || assetClass === 'Crypto') {
       if (currency && currency !== symbol) {
         // e.g. BTC + USD -> BTCUSD
         return `${symbol}${currency}`;
       }
    }

    // Default (Stocks 'STK', etc)
    return symbol;
  };

  const renderDetailView = () => {
    if (!selectedPosition) return null;

    const tvSymbol = getTradingViewSymbol(selectedPosition);
    const isFuture = selectedPosition.assetClass === 'FUT' || selectedPosition.assetClass === 'Future';

    return (
      <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => setSelectedPosition(null)} className="gap-2 pl-0 hover:pl-2 transition-all">
            <ArrowLeft className="h-4 w-4" />
            Back to Portfolio
          </Button>
          <h2 className="text-2xl font-bold">{selectedPosition.symbol} Details</h2>
        </div>

        <Card>
          <CardContent className="p-6">
            <div className="w-full h-[500px] border rounded-md overflow-hidden">
              {isFuture ? (
                <FutureChart 
                  symbol={selectedPosition.symbol}
                  assetClass={selectedPosition.assetClass}
                  currency={selectedPosition.currency}
                  exchange={selectedPosition.exchange}
                  conId={selectedPosition.conId}
                />
              ) : (
                <iframe
                  title={`tv-${selectedPosition.symbol}`}
                  src={`https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(tvSymbol)}&interval=D&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=var(--background)&studies=[]&hideideas=1&theme=light#`}
                  width="100%"
                  height="100%"
                  frameBorder="0"
                  allowTransparency={true}
                  scrolling="no"
                />
              )}
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Position Details</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <dt className="text-muted-foreground">Asset Class</dt>
                  <dd className="font-medium">{selectedPosition.assetClass}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Strategy</dt>
                  <dd className="font-medium">{selectedPosition.strategy}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Quantity</dt>
                  <dd className="font-medium">{selectedPosition.quantity.toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Side</dt>
                  <dd className={`font-medium ${selectedPosition.side === 'long' ? 'text-profit' : 'text-loss'}`}>
                    {selectedPosition.side.toUpperCase()}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Avg Price</dt>
                  <dd className="font-medium">{selectedPosition.currency} {selectedPosition.avgPrice.toFixed(2)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Current Price</dt>
                  <dd className="font-medium">{selectedPosition.currency} {selectedPosition.currentPrice.toFixed(2)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Market Value</dt>
                  <dd className="font-medium">{selectedPosition.currency} {selectedPosition.marketValue.toLocaleString()}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Unrealized P&L</dt>
                  <dd className={`font-medium ${selectedPosition.unrealizedPnL >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {selectedPosition.currency} {selectedPosition.unrealizedPnL.toFixed(2)} ({selectedPosition.pnlPercentage.toFixed(2)}%)
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Transaction History</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center text-muted-foreground py-8 flex flex-col items-center justify-center h-full">
                <p className="font-medium">Transaction history coming soon...</p>
                <p className="text-xs mt-2">Initial purchase, top-ups, and reductions will be listed here.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  };

  const renderStrategySelector = (position: Position) => {
    const key = getAssignKey(position);
    const value = position.strategy || 'Discretionary';
    const hasCurrentInOptions = value === 'Discretionary' || strategies.includes(value);

    return (
      <div className="min-w-[180px]">
        <Select
          value={value}
          onValueChange={(next) => handleStrategyAssignment(position, next)}
          disabled={assigningKey === key}
        >
          <SelectTrigger className="h-8">
            {value === 'Discretionary' ? <span className="opacity-50"></span> : <SelectValue placeholder="Assign strategy" />}
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="Discretionary">Discretionary</SelectItem>
            {!hasCurrentInOptions && (
              <SelectItem value={value}>{value}</SelectItem>
            )}
            {strategies.map((strategy) => (
              <SelectItem key={strategy} value={strategy}>
                {strategy}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  };

  const renderActions = (position: Position) => {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="h-8 w-8 p-0">
            <span className="sr-only">Open menu</span>
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onClick={() => handleDeletePosition(position)}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete Position
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  };

  // Load data on component mount
  useEffect(() => {
    loadPortfolioData();
    loadStrategies();
  }, [loadPortfolioData, loadStrategies]);

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

  if (selectedPosition) {
    return renderDetailView();
  }

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
                    <th className="w-[50px]"></th>
                  </tr>
                </thead>
                <tbody>
                  {(groupBy === 'symbol' ? sortedBySymbol : sortedByNav).map((position, index) => (
                    <tr key={`${position.symbol}-${index}`} className="border-b hover:bg-muted/50">
                      <td className="p-2 font-medium">
                        <button 
                          onClick={() => setSelectedPosition(position)}
                          className="hover:underline focus:outline-none font-medium text-left"
                        >
                          {position.symbol}
                        </button>
                      </td>
                      <td className="p-2 text-sm text-muted-foreground">{position.assetClass}</td>
                      <td className="text-right p-2">{position.quantity.toLocaleString()}</td>
                      <td className="text-right p-2">{position.currency} {position.avgPrice.toFixed(2)}</td>
                      <td className="text-right p-2">{position.currency} {position.currentPrice.toFixed(2)}</td>
                      <td className="text-right p-2">{position.currency} {position.marketValue.toLocaleString()}</td>
                      <td className="text-right p-2">{position.navPercentage.toFixed(2)}%</td>
                      <td className={`text-right p-2 ${position.pnlPercentage >= 0 ? 'text-profit' : 'text-loss'}`}>{position.pnlPercentage.toFixed(2)}%</td>
                      <td className="p-2">{renderStrategySelector(position)}</td>
                      <td className="p-2">{renderActions(position)}</td>
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
                      <th className="w-[50px]"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sideGrouped.longs.map((position, index) => (
                      <tr key={`long-${position.symbol}-${index}`} className="border-b hover:bg-muted/50">
                        <td className="p-2 font-medium">
                          <button 
                            onClick={() => setSelectedPosition(position)}
                            className="hover:underline focus:outline-none font-medium text-left"
                          >
                            {position.symbol}
                          </button>
                        </td>
                        <td className="p-2 text-sm text-muted-foreground">{position.assetClass}</td>
                        <td className="text-right p-2">{position.quantity.toLocaleString()}</td>
                        <td className="text-right p-2">{position.currency} {position.avgPrice.toFixed(2)}</td>
                        <td className="text-right p-2">{position.currency} {position.currentPrice.toFixed(2)}</td>
                        <td className="text-right p-2">{position.currency} {position.marketValue.toLocaleString()}</td>
                        <td className="text-right p-2">{position.navPercentage.toFixed(2)}%</td>
                        <td className={`text-right p-2 ${position.pnlPercentage >= 0 ? 'text-profit' : 'text-loss'}`}>{position.pnlPercentage.toFixed(2)}%</td>
                        <td className="p-2">{renderStrategySelector(position)}</td>
                        <td className="p-2">{renderActions(position)}</td>
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
                      <th className="w-[50px]"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sideGrouped.shorts.map((position, index) => (
                      <tr key={`short-${position.symbol}-${index}`} className="border-b hover:bg-muted/50">
                        <td className="p-2 font-medium">
                          <button 
                            onClick={() => setSelectedPosition(position)}
                            className="hover:underline focus:outline-none font-medium text-left"
                          >
                            {position.symbol}
                          </button>
                        </td>
                        <td className="p-2 text-sm text-muted-foreground">{position.assetClass}</td>
                        <td className="text-right p-2">{position.quantity.toLocaleString()}</td>
                        <td className="text-right p-2">{position.currency} {position.avgPrice.toFixed(2)}</td>
                        <td className="text-right p-2">{position.currency} {position.currentPrice.toFixed(2)}</td>
                        <td className="text-right p-2">{position.currency} {position.marketValue.toLocaleString()}</td>
                        <td className="text-right p-2">{position.navPercentage.toFixed(2)}%</td>
                        <td className={`text-right p-2 ${position.pnlPercentage >= 0 ? 'text-profit' : 'text-loss'}`}>{position.pnlPercentage.toFixed(2)}%</td>
                        <td className="p-2">{renderStrategySelector(position)}</td>
                        <td className="p-2">{renderActions(position)}</td>
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