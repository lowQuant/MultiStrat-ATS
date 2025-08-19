import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { 
  TrendingUp, 
  TrendingDown, 
  Clock, 
  CheckCircle, 
  XCircle,
  AlertCircle
} from 'lucide-react';

interface Trade {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  orderType: string;
  price?: number;
  status: 'pending' | 'filled' | 'cancelled' | 'partial';
  timestamp: string;
  strategy: string;
  fillPrice?: number;
  filledQuantity?: number;
}

const TradeExecution = () => {
  const [trades, setTrades] = useState<Trade[]>([
    {
      id: '1',
      symbol: 'SPY',
      side: 'buy',
      quantity: 100,
      orderType: 'market',
      status: 'filled',
      timestamp: '10:15:32',
      strategy: 'Mean Reversion SPY',
      fillPrice: 425.20,
      filledQuantity: 100
    },
    {
      id: '2',
      symbol: 'QQQ',
      side: 'sell',
      quantity: 50,
      orderType: 'limit',
      price: 349.00,
      status: 'pending',
      timestamp: '10:12:45',
      strategy: 'Momentum QQQ',
      filledQuantity: 0
    },
    {
      id: '3',
      symbol: 'AAPL',
      side: 'buy',
      quantity: 25,
      orderType: 'market',
      status: 'partial',
      timestamp: '10:08:12',
      strategy: 'Pairs Trade Tech',
      fillPrice: 176.45,
      filledQuantity: 15
    }
  ]);

  const [manualOrder, setManualOrder] = useState({
    symbol: '',
    side: '',
    quantity: '',
    orderType: 'market',
    price: '',
    strategy: ''
  });

  const handleManualOrder = async () => {
    try {
      const response = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(manualOrder)
      });
      
      if (response.ok) {
        const newTrade = await response.json();
        setTrades(prev => [newTrade, ...prev]);
        setManualOrder({ symbol: '', side: '', quantity: '', orderType: 'market', price: '', strategy: '' });
      }
    } catch (error) {
      console.error('Failed to place order:', error);
    }
  };

  const cancelOrder = async (tradeId: string) => {
    try {
      const response = await fetch(`/api/orders/${tradeId}/cancel`, {
        method: 'POST'
      });
      
      if (response.ok) {
        setTrades(prev => prev.map(trade => 
          trade.id === tradeId ? { ...trade, status: 'cancelled' } : trade
        ));
      }
    } catch (error) {
      console.error('Failed to cancel order:', error);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'filled': return <CheckCircle className="h-4 w-4 text-profit" />;
      case 'pending': return <Clock className="h-4 w-4 text-warning" />;
      case 'cancelled': return <XCircle className="h-4 w-4 text-loss" />;
      case 'partial': return <AlertCircle className="h-4 w-4 text-info" />;
      default: return <Clock className="h-4 w-4" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const variants = {
      filled: 'default',
      pending: 'secondary',
      cancelled: 'destructive',
      partial: 'outline'
    };
    return <Badge variant={variants[status as keyof typeof variants] as any}>{status}</Badge>;
  };

  const getSideIcon = (side: string) => {
    return side === 'buy' ? 
      <TrendingUp className="h-4 w-4 text-profit" /> : 
      <TrendingDown className="h-4 w-4 text-loss" />;
  };

  const pendingTrades = trades.filter(trade => trade.status === 'pending' || trade.status === 'partial');
  const completedTrades = trades.filter(trade => trade.status === 'filled');
  const cancelledTrades = trades.filter(trade => trade.status === 'cancelled');

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Trade Execution</h2>
        <div className="flex gap-4 text-sm">
          <span>Pending: <Badge variant="secondary">{pendingTrades.length}</Badge></span>
          <span>Filled: <Badge variant="default">{completedTrades.length}</Badge></span>
          <span>Cancelled: <Badge variant="destructive">{cancelledTrades.length}</Badge></span>
        </div>
      </div>

      {/* Manual Order Entry */}
      <Card>
        <CardHeader>
          <CardTitle>Manual Order Entry</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
            <div>
              <Label htmlFor="symbol">Symbol</Label>
              <Input
                id="symbol"
                value={manualOrder.symbol}
                onChange={(e) => setManualOrder(prev => ({ ...prev, symbol: e.target.value.toUpperCase() }))}
                placeholder="SPY"
              />
            </div>
            <div>
              <Label htmlFor="side">Side</Label>
              <Select value={manualOrder.side} onValueChange={(value) => setManualOrder(prev => ({ ...prev, side: value }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Select" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="buy">Buy</SelectItem>
                  <SelectItem value="sell">Sell</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="quantity">Quantity</Label>
              <Input
                id="quantity"
                type="number"
                value={manualOrder.quantity}
                onChange={(e) => setManualOrder(prev => ({ ...prev, quantity: e.target.value }))}
                placeholder="100"
              />
            </div>
            <div>
              <Label htmlFor="orderType">Order Type</Label>
              <Select value={manualOrder.orderType} onValueChange={(value) => setManualOrder(prev => ({ ...prev, orderType: value }))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="market">Market</SelectItem>
                  <SelectItem value="limit">Limit</SelectItem>
                  <SelectItem value="stop">Stop</SelectItem>
                  <SelectItem value="stop_limit">Stop Limit</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {manualOrder.orderType !== 'market' && (
              <div>
                <Label htmlFor="price">Price</Label>
                <Input
                  id="price"
                  type="number"
                  step="0.01"
                  value={manualOrder.price}
                  onChange={(e) => setManualOrder(prev => ({ ...prev, price: e.target.value }))}
                  placeholder="425.00"
                />
              </div>
            )}
            <div>
              <Label htmlFor="strategy">Strategy</Label>
              <Select value={manualOrder.strategy} onValueChange={(value) => setManualOrder(prev => ({ ...prev, strategy: value }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Manual" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="mean_reversion">Mean Reversion</SelectItem>
                  <SelectItem value="momentum">Momentum</SelectItem>
                  <SelectItem value="pairs_trading">Pairs Trading</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button onClick={handleManualOrder} className="w-full">
            Place Order
          </Button>
        </CardContent>
      </Card>

      {/* Recent Trades */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Trades</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-2">Time</th>
                  <th className="text-left p-2">Symbol</th>
                  <th className="text-left p-2">Side</th>
                  <th className="text-right p-2">Quantity</th>
                  <th className="text-left p-2">Type</th>
                  <th className="text-right p-2">Price</th>
                  <th className="text-left p-2">Status</th>
                  <th className="text-left p-2">Strategy</th>
                  <th className="text-left p-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => (
                  <tr key={trade.id} className="border-b hover:bg-muted/50">
                    <td className="p-2">{trade.timestamp}</td>
                    <td className="p-2 font-medium">{trade.symbol}</td>
                    <td className="p-2">
                      <div className="flex items-center gap-1">
                        {getSideIcon(trade.side)}
                        <span className={trade.side === 'buy' ? 'text-profit' : 'text-loss'}>
                          {trade.side.toUpperCase()}
                        </span>
                      </div>
                    </td>
                    <td className="text-right p-2">
                      {trade.status === 'partial' ? 
                        `${trade.filledQuantity}/${trade.quantity}` : 
                        trade.quantity
                      }
                    </td>
                    <td className="p-2">{trade.orderType.toUpperCase()}</td>
                    <td className="text-right p-2">
                      {trade.fillPrice ? 
                        `$${trade.fillPrice.toFixed(2)}` : 
                        trade.price ? `$${trade.price.toFixed(2)}` : 'Market'
                      }
                    </td>
                    <td className="p-2">
                      <div className="flex items-center gap-1">
                        {getStatusIcon(trade.status)}
                        {getStatusBadge(trade.status)}
                      </div>
                    </td>
                    <td className="p-2">
                      <Badge variant="outline" className="text-xs">
                        {trade.strategy}
                      </Badge>
                    </td>
                    <td className="p-2">
                      {(trade.status === 'pending' || trade.status === 'partial') && (
                        <Button 
                          variant="outline" 
                          size="sm"
                          onClick={() => cancelOrder(trade.id)}
                        >
                          Cancel
                        </Button>
                      )}
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

export default TradeExecution;