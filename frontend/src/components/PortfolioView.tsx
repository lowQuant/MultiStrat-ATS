import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { 
  TrendingUp, 
  TrendingDown, 
  DollarSign,
  BarChart3,
  RefreshCw
} from 'lucide-react';

interface Position {
  id: string;
  symbol: string;
  quantity: number;
  avgPrice: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnL: number;
  strategy: string;
  side: 'long' | 'short';
}

const PortfolioView = () => {
  const [positions, setPositions] = useState<Position[]>([
    {
      id: '1',
      symbol: 'SPY',
      quantity: 100,
      avgPrice: 420.50,
      currentPrice: 425.20,
      marketValue: 42520,
      unrealizedPnL: 470,
      strategy: 'Mean Reversion SPY',
      side: 'long'
    },
    {
      id: '2',
      symbol: 'QQQ',
      quantity: -50,
      avgPrice: 350.75,
      currentPrice: 348.90,
      marketValue: -17445,
      unrealizedPnL: 92.50,
      strategy: 'Momentum QQQ',
      side: 'short'
    },
    {
      id: '3',
      symbol: 'AAPL',
      quantity: 25,
      avgPrice: 175.80,
      currentPrice: 176.45,
      marketValue: 4411.25,
      unrealizedPnL: 16.25,
      strategy: 'Pairs Trade Tech',
      side: 'long'
    },
    {
      id: '4',
      symbol: 'MSFT',
      quantity: -10,
      avgPrice: 340.20,
      currentPrice: 338.50,
      marketValue: -3385,
      unrealizedPnL: 17,
      strategy: 'Pairs Trade Tech',
      side: 'short'
    }
  ]);

  const [lastUpdate, setLastUpdate] = useState(new Date());

  const refreshPositions = async () => {
    try {
      const response = await fetch('/api/positions');
      if (response.ok) {
        const updatedPositions = await response.json();
        setPositions(updatedPositions);
        setLastUpdate(new Date());
      }
    } catch (error) {
      console.error('Failed to refresh positions:', error);
    }
  };

  const totalMarketValue = positions.reduce((sum, pos) => sum + pos.marketValue, 0);
  const totalUnrealizedPnL = positions.reduce((sum, pos) => sum + pos.unrealizedPnL, 0);
  const longPositions = positions.filter(pos => pos.side === 'long');
  const shortPositions = positions.filter(pos => pos.side === 'short');

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Portfolio Overview</h2>
        <div className="flex items-center gap-4">
          <p className="text-sm text-muted-foreground">
            Last updated: {lastUpdate.toLocaleTimeString()}
          </p>
          <Button variant="outline" size="sm" onClick={refreshPositions}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Portfolio Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Market Value</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${totalMarketValue.toLocaleString()}</div>
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
              ${totalUnrealizedPnL.toFixed(2)}
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

      {/* Positions Table */}
      <Card>
        <CardHeader>
          <CardTitle>Current Positions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-2">Symbol</th>
                  <th className="text-left p-2">Side</th>
                  <th className="text-right p-2">Quantity</th>
                  <th className="text-right p-2">Avg Price</th>
                  <th className="text-right p-2">Current Price</th>
                  <th className="text-right p-2">Market Value</th>
                  <th className="text-right p-2">Unrealized P&L</th>
                  <th className="text-left p-2">Strategy</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position) => (
                  <tr key={position.id} className="border-b hover:bg-muted/50">
                    <td className="p-2 font-medium">{position.symbol}</td>
                    <td className="p-2">
                      <Badge variant={position.side === 'long' ? 'default' : 'secondary'}>
                        {position.side.toUpperCase()}
                      </Badge>
                    </td>
                    <td className="text-right p-2">{Math.abs(position.quantity)}</td>
                    <td className="text-right p-2">${position.avgPrice.toFixed(2)}</td>
                    <td className="text-right p-2">${position.currentPrice.toFixed(2)}</td>
                    <td className="text-right p-2">${Math.abs(position.marketValue).toLocaleString()}</td>
                    <td className={`text-right p-2 ${position.unrealizedPnL >= 0 ? 'text-profit' : 'text-loss'}`}>
                      ${position.unrealizedPnL.toFixed(2)}
                    </td>
                    <td className="p-2">
                      <Badge variant="outline" className="text-xs">
                        {position.strategy}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default PortfolioView;