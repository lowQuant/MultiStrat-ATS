import React, { useEffect, useState } from 'react';
import { ArrowLeft, Play, Square, RefreshCw, Activity, Settings, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  getStrategyDetails,
  triggerStrategySignals,
  triggerStrategyRebalance,
  StrategyDetailsResponse
} from '@/lib/api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { toast } from 'sonner';

interface StrategyDetailsProps {
  strategySymbol: string;
  onBack: () => void;
}

export const StrategyDetails: React.FC<StrategyDetailsProps> = ({ strategySymbol, onBack }) => {
  const [data, setData] = useState<StrategyDetailsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await getStrategyDetails(strategySymbol);
      setData(res);
    } catch (e) {
      console.error('Failed to fetch details', e);
      toast.error("Failed to load strategy details");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [strategySymbol]);

  const handleSignals = async () => {
    try {
      const res = await triggerStrategySignals(strategySymbol);
      if (res.success) toast.success(res.message);
      else toast.error(res.message);
    } catch (e) {
      toast.error("Failed to trigger signals");
    }
  };

  const handleRebalance = async () => {
    try {
      const res = await triggerStrategyRebalance(strategySymbol);
      if (res.success) toast.success(res.message);
      else toast.error(res.message);
    } catch (e) {
      toast.error("Failed to trigger rebalance");
    }
  };

  if (loading) return <div className="p-8 text-center">Loading strategy details...</div>;
  if (!data) return <div className="p-8 text-center">Strategy not found</div>;

  const { metadata, positions, stats, performance } = data;

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h2 className="text-2xl font-bold flex items-center gap-2">
              {metadata.name}
              <Badge variant={metadata.active ? 'default' : 'secondary'}>
                {metadata.active ? 'Active' : 'Inactive'}
              </Badge>
              {metadata.running && <Badge variant="outline" className="text-green-600 border-green-600">Running</Badge>}
            </h2>
            <p className="text-muted-foreground">{metadata.description || "No description provided"}</p>
          </div>
        </div>
        <div className="flex gap-2">
           <Button variant="outline" onClick={handleSignals}>
             <Activity className="h-4 w-4 mr-2" />
             Get Signals
           </Button>
           <Button variant="outline" onClick={handleRebalance}>
             <Zap className="h-4 w-4 mr-2" />
             Rebalance
           </Button>
           <Button variant="outline" onClick={fetchData}>
             <RefreshCw className="h-4 w-4" />
           </Button>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total Equity</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${stats.total_equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Cash Balance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${stats.cash_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
          </CardContent>
        </Card>
        <Card>
           <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Positions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.position_count}</div>
          </CardContent>
        </Card>
      </div>

      {/* Charts & Positions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Chart Section - Takes up 2 columns */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Performance</CardTitle>
            <CardDescription>Equity curve over time</CardDescription>
          </CardHeader>
          <CardContent className="h-[300px]">
            {performance.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={performance}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis 
                    dataKey="timestamp" 
                    tickFormatter={(str) => new Date(str).toLocaleDateString()}
                    stroke="#888888"
                    fontSize={12}
                  />
                  <YAxis 
                    stroke="#888888"
                    fontSize={12}
                    tickFormatter={(val) => `$${val}`}
                    domain={['auto', 'auto']}
                  />
                  <Tooltip 
                    formatter={(value: number) => [`$${value.toFixed(2)}`, 'Equity']}
                    labelFormatter={(label) => new Date(label).toLocaleString()}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="equity" 
                    stroke={metadata.color || "#2563eb"} 
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                No performance data available
              </div>
            )}
          </CardContent>
        </Card>

        {/* Positions List - Takes up 1 column */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Current Positions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4 max-h-[300px] overflow-y-auto pr-2">
              {positions.length === 0 && <div className="text-sm text-muted-foreground">No positions</div>}
              {positions.map((pos, i) => (
                <div key={i} className="flex justify-between items-center border-b last:border-0 pb-2 last:pb-0">
                  <div>
                    <div className="font-medium">{pos.symbol}</div>
                    <div className="text-xs text-muted-foreground">{pos.asset_class} • {pos.quantity} units</div>
                  </div>
                  <div className="text-right">
                    <div className="font-medium">${pos.market_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
                    <div className="text-xs text-muted-foreground">@{pos.avg_cost.toFixed(2)}</div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
      
      {/* Parameters Section */}
      <Card>
        <CardHeader>
            <CardTitle>Configuration Parameters</CardTitle>
        </CardHeader>
        <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {Object.entries(metadata.params).map(([key, value]) => (
                    <div key={key} className="flex flex-col space-y-1">
                        <span className="text-xs font-medium text-muted-foreground uppercase">{key.replace(/_/g, ' ')}</span>
                        <span className="text-sm bg-secondary/50 p-2 rounded-md break-all">
                            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                        </span>
                    </div>
                ))}
            </div>
        </CardContent>
      </Card>
    </div>
  );
};
