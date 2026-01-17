import React, { useEffect, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, CardContent } from '@/components/ui/card';
import { Loader2 } from 'lucide-react';

interface FutureChartProps {
  symbol: string;
  assetClass: string;
  currency?: string;
  exchange?: string;
  conId?: number;
}

interface ChartDataPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

const FutureChart: React.FC<FutureChartProps> = ({ symbol, assetClass, currency = 'USD', exchange = 'SMART', conId }) => {
  const [data, setData] = useState<ChartDataPoint[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Build query params
        const params = new URLSearchParams({
          symbol,
          asset_class: assetClass,
          currency,
          exchange
        });
        
        if (conId) {
          params.append('conId', conId.toString());
        }

        const res = await fetch(`http://127.0.0.1:8000/api/scanner/history?${params.toString()}`);
        const json = await res.json();

        if (json.success && json.data) {
          const { dates, open, high, low, close } = json.data;
          
          // Transform to array of objects for Recharts
          const chartData = dates.map((date: string, i: number) => ({
            date: new Date(date).toLocaleDateString(),
            open: open[i],
            high: high[i],
            low: low[i],
            close: close[i],
          })).filter((d: any) => d.close !== null); // Filter out missing data

          setData(chartData);
        } else {
          setError(json.error || 'Failed to load historical data');
        }
      } catch (err: any) {
        setError(err.message || 'Failed to fetch data');
      } finally {
        setLoading(false);
      }
    };

    if (symbol) {
      fetchData();
    }
  }, [symbol, assetClass, currency, exchange]);

  if (loading) {
    return (
      <div className="w-full h-[500px] flex items-center justify-center border rounded-md bg-card">
        <div className="flex flex-col items-center gap-2 text-muted-foreground">
          <Loader2 className="h-8 w-8 animate-spin" />
          <p>Loading chart data from IB...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full h-[500px] flex items-center justify-center border rounded-md bg-card">
        <div className="text-destructive text-center">
          <p className="font-medium">Unable to load chart</p>
          <p className="text-sm opacity-80">{error}</p>
        </div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="w-full h-[500px] flex items-center justify-center border rounded-md bg-card">
        <p className="text-muted-foreground">No historical data available</p>
      </div>
    );
  }

  // Calculate min/max for Y-axis scaling
  const prices = data.map(d => d.close);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const padding = (maxPrice - minPrice) * 0.1;

  return (
    <Card>
      <CardContent className="p-0">
        <div className="w-full h-[500px] border rounded-md bg-background p-4">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <defs>
                <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
              <XAxis 
                dataKey="date" 
                tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                tickLine={false}
                axisLine={false}
                minTickGap={30}
              />
              <YAxis 
                domain={[minPrice - padding, maxPrice + padding]} 
                tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => value.toFixed(2)}
                width={60}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: 'hsl(var(--popover))', 
                  borderColor: 'hsl(var(--border))',
                  color: 'hsl(var(--popover-foreground))',
                  borderRadius: 'var(--radius)'
                }}
                itemStyle={{ color: 'hsl(var(--primary))' }}
                formatter={(value: number) => [value.toFixed(2), 'Price']}
                labelStyle={{ color: 'hsl(var(--muted-foreground))', marginBottom: '0.5rem' }}
              />
              <Area 
                type="monotone" 
                dataKey="close" 
                stroke="hsl(var(--primary))" 
                fillOpacity={1} 
                fill="url(#colorPrice)" 
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
};

export default FutureChart;
