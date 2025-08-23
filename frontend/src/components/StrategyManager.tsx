import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { 
  Play, 
  Square, 
  Plus, 
  Edit, 
  Trash2,
  TrendingUp,
  TrendingDown,
  Activity,
  RefreshCw
} from 'lucide-react';

interface Strategy {
  symbol: string;            // e.g., AAPL
  filename: string;          // e.g., aapl_strategy.py
  running: boolean;          // from backend status
  type: string;              // derived placeholder from filename
  pnl: number;               // placeholder until wired
  todayPnl: number;          // placeholder until wired
  positions: number;         // placeholder until wired
  lastUpdate: string;        // placeholder
  active?: boolean;          // local activation toggle (frontend-only for now)
}

const StrategyManager = () => {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(false);

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [newStrategy, setNewStrategy] = useState({
    name: '',
    type: '',
    symbol: '',
    capital: '',
    riskLimit: ''
  });

  const backendBase = 'http://127.0.0.1:8000';

  const fetchStrategies = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${backendBase}/api/strategies?active_only=false`);
      if (!res.ok) return;
      const data = await res.json();
      const discovered: string[] = data.discovered_strategies || [];
      const running: Record<string, any> = (data.strategy_status && data.strategy_status.strategies) || {};

      // Normalize: derive symbol from filename and merge running status
      const normalized: Strategy[] = discovered.map((filename) => {
        const symbol = filename.replace('_strategy.py', '').toUpperCase();
        const run = !!running[symbol];
        return {
          symbol,
          filename,
          running: run,
          type: filename.replace('_strategy.py', ''),
          pnl: 0,
          todayPnl: 0,
          positions: 0,
          lastUpdate: run ? 'just now' : '-',
          active: true, // default active locally for now
        };
      });
      setStrategies((prev) => {
        // Preserve local active toggles by symbol if present
        const activeMap = new Map(prev.map((s) => [s.symbol, s.active]));
        return normalized.map((s) => ({ ...s, active: activeMap.get(s.symbol) ?? s.active }));
      });
    } catch (e) {
      console.error('Failed to fetch strategies', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStrategies();
  }, []);

  const handleStrategyAction = async (symbol: string, action: 'start' | 'stop') => {
    try {
      const response = await fetch(`${backendBase}/api/strategies/${symbol}/${action}`, { method: 'POST' });
      if (response.ok) {
        await fetchStrategies();
      }
    } catch (error) {
      console.error(`Failed to ${action} strategy:`, error);
    }
  };

  const handleCreateStrategy = async () => {
    try {
      const response = await fetch('/api/strategies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newStrategy)
      });
      
      if (response.ok) {
        const createdStrategy = await response.json();
        setStrategies(prev => [...prev, createdStrategy]);
        setNewStrategy({ name: '', type: '', symbol: '', capital: '', riskLimit: '' });
        setIsCreateDialogOpen(false);
      }
    } catch (error) {
      console.error('Failed to create strategy:', error);
    }
  };

  // Frontend-only activation state toggle (to be persisted in backend later)
  const toggleActive = (symbol: string, value: boolean) => {
    setStrategies((prev) => prev.map((s) => (s.symbol === symbol ? { ...s, active: value } : s)));
  };

  const getStatusIcon = (running: boolean) => {
    return running ? <Play className="h-4 w-4 text-profit" /> : <Square className="h-4 w-4 text-muted-foreground" />;
  };

  const getStatusBadge = (running: boolean) => {
    return <Badge variant={running ? ('default' as any) : ('outline' as any)}>{running ? 'running' : 'stopped'}</Badge>;
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Strategy Management</h2>
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              New Strategy
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[425px]">
            <DialogHeader>
              <DialogTitle>Create New Strategy</DialogTitle>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="name">Strategy Name</Label>
                <Input
                  id="name"
                  value={newStrategy.name}
                  onChange={(e) => setNewStrategy(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="e.g. Mean Reversion SPY"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="type">Strategy Type</Label>
                <Select value={newStrategy.type} onValueChange={(value) => setNewStrategy(prev => ({ ...prev, type: value }))}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select strategy type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="mean_reversion">Mean Reversion</SelectItem>
                    <SelectItem value="momentum">Momentum</SelectItem>
                    <SelectItem value="pairs_trading">Pairs Trading</SelectItem>
                    <SelectItem value="arbitrage">Arbitrage</SelectItem>
                    <SelectItem value="market_making">Market Making</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="symbol">Primary Symbol</Label>
                <Input
                  id="symbol"
                  value={newStrategy.symbol}
                  onChange={(e) => setNewStrategy(prev => ({ ...prev, symbol: e.target.value }))}
                  placeholder="e.g. SPY"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="capital">Capital Allocation</Label>
                <Input
                  id="capital"
                  type="number"
                  value={newStrategy.capital}
                  onChange={(e) => setNewStrategy(prev => ({ ...prev, capital: e.target.value }))}
                  placeholder="e.g. 50000"
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="riskLimit">Risk Limit (%)</Label>
                <Input
                  id="riskLimit"
                  type="number"
                  value={newStrategy.riskLimit}
                  onChange={(e) => setNewStrategy(prev => ({ ...prev, riskLimit: e.target.value }))}
                  placeholder="e.g. 2"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreateStrategy}>Create Strategy</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Toolbar */}
      <div className="flex gap-2">
        <Button variant="default" onClick={() => fetch(`${backendBase}/api/strategies/start-all`, { method: 'POST' }).then(fetchStrategies)} disabled={loading || strategies.length === 0}>
          <Play className="h-4 w-4 mr-2" />
          Start All
        </Button>
        <Button variant="outline" onClick={() => fetch(`${backendBase}/api/strategies/stop-all`, { method: 'POST' }).then(fetchStrategies)} disabled={loading}>
          <Square className="h-4 w-4 mr-2" />
          Stop All
        </Button>
        <Button variant="ghost" onClick={fetchStrategies} disabled={loading}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      <div className="grid gap-4">
        {strategies.map((strategy) => (
          <Card key={strategy.symbol}>
            <CardHeader>
              <div className="flex justify-between items-start">
                <div className="space-y-1">
                  <CardTitle className="flex items-center gap-2">
                    {getStatusIcon(strategy.running)}
                    {strategy.symbol}
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    {getStatusBadge(strategy.running)}
                    <Badge variant="outline">{strategy.type.replace('_', ' ')}</Badge>
                  </div>
                </div>
                <div className="flex gap-2">
                  <div className="flex items-center gap-2 mr-2">
                    <Switch checked={!!strategy.active} onCheckedChange={(v) => toggleActive(strategy.symbol, v)} />
                    <span className="text-sm text-muted-foreground">Active</span>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleStrategyAction(strategy.symbol, strategy.running ? 'stop' : 'start')}
                  >
                    {strategy.running ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleStrategyAction(strategy.symbol, 'stop')}
                  >
                    <Square className="h-4 w-4" />
                  </Button>
                  <Button variant="outline" size="sm">
                    <Edit className="h-4 w-4" />
                  </Button>
                  <Button variant="outline" size="sm">
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Total P&L</p>
                  <p className={`text-lg font-semibold ${strategy.pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                    ${strategy.pnl.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Today P&L</p>
                  <p className={`text-lg font-semibold ${strategy.todayPnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                    ${strategy.todayPnl.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Positions</p>
                  <p className="text-lg font-semibold">{strategy.positions}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Last Update</p>
                  <p className="text-lg font-semibold">{strategy.lastUpdate}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default StrategyManager;