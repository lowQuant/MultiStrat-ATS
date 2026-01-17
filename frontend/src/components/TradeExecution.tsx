import { useEffect, useState, useCallback } from 'react';
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
  AlertCircle,
  RefreshCw
} from 'lucide-react';

interface Trade {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  orderType: string;
  price?: number;
  status: string;
  timestamp: string;
  strategy: string;
  fillPrice?: number;
  filledQuantity?: number;
}

const TradeExecution = () => {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const [manualOrder, setManualOrder] = useState({
    symbol: '',
    side: '',
    quantity: '',
    orderType: 'market',
    price: '',
    strategy: 'Discretionary'
  });

  const [strategyOptions, setStrategyOptions] = useState<string[]>(['Discretionary']);

  const fetchOrders = useCallback(async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/trade/orders');
      if (!res.ok) return;
      const data = await res.json();
      
      // Map backend orders to frontend Trade interface
      const mappedTrades: Trade[] = data.map((order: any) => ({
        id: String(order.permId || order.orderId),
        symbol: order.symbol,
        side: order.action.toLowerCase(),
        quantity: order.totalQuantity,
        orderType: order.orderType.toLowerCase(),
        price: order.lmtPrice || undefined,
        status: order.status.toLowerCase(),
        timestamp: new Date().toLocaleTimeString(), // Placeholder as API doesn't send time yet
        strategy: order.orderRef || 'Discretionary',
        fillPrice: order.avgFillPrice > 0 ? order.avgFillPrice : undefined,
        filledQuantity: order.filled > 0 ? order.filled : undefined
      }));
      
      setTrades(mappedTrades);
    } catch (error) {
      console.error("Failed to fetch orders", error);
    }
  }, []);

  useEffect(() => {
    // Initial fetch
    fetchOrders();
    
    // Poll every 3 seconds
    const interval = setInterval(fetchOrders, 3000);
    return () => clearInterval(interval);
  }, [fetchOrders]);

  useEffect(() => {
    // Fetch saved strategies to populate the dropdown
    const fetchStrategies = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/strategies');
        const data = (await res.json()) as { strategies?: Array<{ strategy_symbol?: string }> };
        const list: Array<{ strategy_symbol?: string }> = Array.isArray(data?.strategies) ? data.strategies! : [];
        const symbols = list
          .map((s) => String(s.strategy_symbol || '').toUpperCase())
          .filter((s: string) => !!s);
        const unique = Array.from(new Set(symbols));
        setStrategyOptions(['Discretionary', ...unique]);
      } catch (e) {
        console.error('Failed to fetch strategies for dropdown', e);
        setStrategyOptions(['Discretionary']);
      }
    };
    fetchStrategies();
  }, []);

  const handleManualOrder = async () => {
    try {
      setIsLoading(true);
      // Map UI state to backend payload (flat format supported by backend)
      const order_type = manualOrder.orderType === 'limit' ? 'LMT' : 'MKT';
      const quantityNum = Number(manualOrder.quantity);
      const priceNum = manualOrder.orderType === 'limit' ? Number(manualOrder.price) : undefined;

      const payload: any = {
        symbol: manualOrder.symbol.trim().toUpperCase(),
        secType: 'STK',
        exchange: 'SMART',
        currency: 'USD',
        side: manualOrder.side as 'buy' | 'sell',
        quantity: quantityNum,
        order_type,
        price: priceNum,
        algo: true,
        urgency: 'Patient',
        orderRef: (manualOrder.strategy || 'Discretionary').toUpperCase(),
        useRth: false,
      };

      const response = await fetch('http://127.0.0.1:8000/api/trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (response.ok) {
        setManualOrder({ symbol: '', side: '', quantity: '', orderType: 'market', price: '', strategy: 'Discretionary' });
        // Refresh list immediately
        fetchOrders();
      }
    } catch (error) {
      console.error('Failed to place order:', error);
    } finally {
        setIsLoading(false);
    }
  };

  const cancelOrder = async (tradeId: string) => {
    try {
      // Use correct backend route
      const response = await fetch(`http://127.0.0.1:8000/api/trade/orders/${tradeId}/cancel`, {
        method: 'POST'
      });
      
      if (response.ok) {
        // Optimistic update or wait for refresh
        fetchOrders();
      }
    } catch (error) {
      console.error('Failed to cancel order:', error);
    }
  };

  const getStatusIcon = (status: string) => {
    // Normalize status
    const s = status.toLowerCase();
    if (s === 'filled') return <CheckCircle className="h-4 w-4 text-profit" />;
    if (['cancelled', 'inactive'].includes(s)) return <XCircle className="h-4 w-4 text-loss" />;
    if (['pending', 'submitted', 'presubmitted'].includes(s)) return <Clock className="h-4 w-4 text-warning" />;
    return <AlertCircle className="h-4 w-4 text-info" />;
  };

  const getStatusBadge = (status: string) => {
    const s = status.toLowerCase();
    let variant: "default" | "secondary" | "destructive" | "outline" = "outline";
    
    if (s === 'filled') variant = 'default';
    else if (['pending', 'submitted', 'presubmitted'].includes(s)) variant = 'secondary';
    else if (['cancelled', 'inactive'].includes(s)) variant = 'destructive';
    
    return <Badge variant={variant}>{status}</Badge>;
  };

  const getSideIcon = (side: string) => {
    return side.toLowerCase() === 'buy' ? 
      <TrendingUp className="h-4 w-4 text-profit" /> : 
      <TrendingDown className="h-4 w-4 text-loss" />;
  };

  const pendingTrades = trades.filter(trade => ['pending', 'submitted', 'presubmitted'].includes(trade.status.toLowerCase()));
  const completedTrades = trades.filter(trade => trade.status.toLowerCase() === 'filled');
  const cancelledTrades = trades.filter(trade => ['cancelled', 'inactive'].includes(trade.status.toLowerCase()));

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Trade Execution</h2>
        <div className="flex gap-4 text-sm items-center">
          <Button variant="ghost" size="sm" onClick={fetchOrders}>
            <RefreshCw className="h-4 w-4 mr-2" /> Refresh
          </Button>
          <span>Open: <Badge variant="secondary">{pendingTrades.length}</Badge></span>
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
                  {strategyOptions.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button onClick={handleManualOrder} className="w-full" disabled={isLoading}>
            {isLoading ? 'Placing Order...' : 'Place Order'}
          </Button>
        </CardContent>
      </Card>

      {/* Live Orders Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Active Orders & Executions</CardTitle>
          <div className="flex gap-4 text-sm">
            <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-profit"></div>
                <span className="text-muted-foreground">Buy: {trades.filter(t => t.side === 'buy').length}</span>
            </div>
            <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-loss"></div>
                <span className="text-muted-foreground">Sell: {trades.filter(t => t.side === 'sell').length}</span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="max-h-[600px] overflow-y-auto custom-scrollbar">
            <OrdersTable 
                orders={trades} 
                onCancel={cancelOrder} 
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// Internal Component for Order Table
const OrdersTable = ({ orders, onCancel }: { orders: Trade[], onCancel: (id: string) => void }) => {
  if (orders.length === 0) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        No active orders
      </div>
    );
  }

  return (
    <table className="w-full text-sm table-fixed">
      <thead className="bg-muted/50 sticky top-0 z-10 backdrop-blur-sm">
        <tr className="border-b text-xs uppercase text-muted-foreground">
          <th className="text-left p-3 font-medium w-[20%]">Symbol / Strategy</th>
          <th className="text-left p-3 font-medium w-[10%]">Side</th>
          <th className="text-left p-3 font-medium w-[15%]">Type / Limit</th>
          <th className="text-right p-3 font-medium w-[15%]">Filled / Qty</th>
          <th className="text-right p-3 font-medium w-[15%]">Avg Price</th>
          <th className="text-center p-3 font-medium w-[15%]">Status</th>
          <th className="text-right p-3 font-medium w-[10%]">Action</th>
        </tr>
      </thead>
      <tbody>
        {orders.map((trade) => {
           const isFilled = trade.status === 'filled';
           const fillProgress = trade.filledQuantity || 0;
           const totalQty = trade.quantity;
           const typeLabel = trade.orderType.toUpperCase();
           const priceLabel = trade.price ? `$${trade.price.toFixed(2)}` : '';
           const isBuy = trade.side === 'buy';
           
           return (
            <tr key={trade.id} className="border-b hover:bg-muted/50 transition-colors group">
              <td className="p-3 align-middle">
                <div className="flex flex-col gap-0.5">
                  <span className="font-bold text-base">{trade.symbol}</span>
                  <span className="text-xs text-muted-foreground font-medium truncate" title={trade.strategy}>
                    {trade.strategy}
                  </span>
                </div>
              </td>

              <td className="p-3 align-middle">
                 <Badge variant="outline" className={`${isBuy ? 'text-profit border-profit/20 bg-profit/5' : 'text-loss border-loss/20 bg-loss/5'} font-semibold`}>
                    {trade.side.toUpperCase()}
                 </Badge>
              </td>
              
              <td className="p-3 align-middle">
                <div className="flex flex-col">
                   <span className="font-semibold">{typeLabel}</span>
                   {trade.price && <span className="text-xs text-muted-foreground">@ {priceLabel}</span>}
                </div>
              </td>

              <td className="text-right p-3 align-middle font-mono text-sm">
                <span className={fillProgress > 0 ? 'text-foreground font-medium' : 'text-muted-foreground'}>
                  {fillProgress}
                </span>
                <span className="text-muted-foreground mx-1">/</span>
                <span>{totalQty}</span>
              </td>

              <td className="text-right p-3 align-middle font-mono">
                {trade.fillPrice && trade.fillPrice > 0 ? (
                   <span className={isBuy ? 'text-profit font-medium' : 'text-loss font-medium'}>
                     ${trade.fillPrice.toFixed(2)}
                   </span>
                ) : (
                   <span className="text-muted-foreground">-</span>
                )}
              </td>

              <td className="p-3 align-middle text-center">
                <Badge 
                  variant={
                      ['filled'].includes(trade.status) ? 'default' :
                      ['cancelled', 'inactive'].includes(trade.status) ? 'destructive' : 'secondary'
                  } 
                  className="text-[10px] h-5 px-2 min-w-[70px] justify-center"
                >
                  {trade.status.toUpperCase()}
                </Badge>
              </td>

              <td className="text-right p-3 align-middle">
                <div className="flex justify-end gap-1 opacity-100">
                   {/* Edit Button (Placeholder) */}
                   <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground" disabled title="Edit Order">
                     <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>
                   </Button>
                   {/* Cancel Button */}
                   {['pending', 'submitted', 'presubmitted'].includes(trade.status) && (
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      className="h-8 w-8 text-destructive hover:bg-destructive/10"
                      onClick={() => onCancel(trade.id)}
                      title="Cancel Order"
                    >
                      <XCircle className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
};

export default TradeExecution;