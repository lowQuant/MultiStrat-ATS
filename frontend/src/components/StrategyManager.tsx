import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
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
  const [discoveredFiles, setDiscoveredFiles] = useState<string[]>([]);
  const [newStrategy, setNewStrategy] = useState({
    name: '',
    symbol: '',
    description: '',
    targetWeight: '',
    minWeight: '',
    maxWeight: '',
    filename: '',
    color: '#4f46e5',
  });

  const backendBase = 'http://127.0.0.1:8000';

  const fetchStrategies = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${backendBase}/api/strategies?active_only=false`);
      if (!res.ok) return;
      const data = await res.json();
      const discovered: string[] = data.discovered_strategies || [];
      setDiscoveredFiles(discovered);
      const saved: any[] = data.strategies || [];

      const normalized: Strategy[] = saved.map((row) => {
        const symbol = String(row.strategy_symbol || '').toUpperCase();
        const filename = row.filename || '';
        const run = !!row.running;
        return {
          symbol,
          filename,
          running: run,
          type: filename ? filename.replace('_strategy.py', '') : (row.name || symbol),
          pnl: 0,
          todayPnl: 0,
          positions: 0,
          lastUpdate: run ? 'just now' : '-',
          active: !!row.active,
        };
      });
      setStrategies(normalized);
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

  const handleDeleteStrategy = async (symbol: string) => {
    try {
      const resp = await fetch(`${backendBase}/api/strategies/${symbol}/delete`, { method: 'POST' });
      if (!resp.ok) {
        const msg = await resp.text();
        console.error('Failed to delete strategy:', msg);
        return;
      }
      await fetchStrategies();
    } catch (e) {
      console.error('Error deleting strategy', e);
    }
  };

  const handleCreateStrategy = async () => {
    try {
      const payload = {
        name: newStrategy.name,
        strategy_symbol: newStrategy.symbol.toUpperCase(),
        description: newStrategy.description,
        target_weight: newStrategy.targetWeight === '' ? null : parseFloat(newStrategy.targetWeight),
        min_weight: newStrategy.minWeight === '' ? null : parseFloat(newStrategy.minWeight),
        max_weight: newStrategy.maxWeight === '' ? null : parseFloat(newStrategy.maxWeight),
        filename: newStrategy.filename || null,
        params: {},
        color: newStrategy.color,
        active: false,
      };

      const resp = await fetch(`${backendBase}/api/strategies/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const msg = await resp.text();
        console.error('Failed to save strategy metadata:', msg);
        return;
      }

      // Refresh list and close dialog
      await fetchStrategies();
      setIsCreateDialogOpen(false);
      setNewStrategy({
        name: '',
        symbol: '',
        description: '',
        targetWeight: '',
        minWeight: '',
        maxWeight: '',
        filename: '',
        color: '#4f46e5',
      });
    } catch (e) {
      console.error('Error saving strategy metadata', e);
    }
  };

  const toggleActive = async (symbol: string, value: boolean) => {
    try {
      const endpoint = value ? 'activate' : 'deactivate';
      const resp = await fetch(`${backendBase}/api/strategies/${symbol}/${endpoint}`, { method: 'POST' });
      if (!resp.ok) {
        const msg = await resp.text();
        console.error(`Failed to ${endpoint} strategy:`, msg);
      }
      await fetchStrategies();
    } catch (e) {
      console.error('Error toggling strategy active state', e);
    }
  };

  const getStatusIcon = (running: boolean) => {
    return running ? <Play className="h-4 w-4 text-profit" /> : <Square className="h-4 w-4 text-muted-foreground" />;
  };

  const getRunningBadge = (running: boolean) => (
    <Badge variant={running ? ('default' as any) : ('outline' as any)}>{running ? 'running' : 'stopped'}</Badge>
  );

  const getActiveBadge = (active?: boolean) => (
    <Badge variant={active ? ('default' as any) : ('outline' as any)}>{active ? 'active' : 'inactive'}</Badge>
  );

  // Derived counts for header summary
  const totalCount = strategies.length;
  const activeCount = strategies.filter((s) => !!s.active).length;
  const runningCount = strategies.filter((s) => !!s.running).length;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Strategy Management</h2>
        {/* Dialog kept mounted; trigger moved to toolbar */}
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogContent className="sm:max-w-[560px]">
            <DialogHeader>
              <DialogTitle>Add Strategy</DialogTitle>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                  <Label htmlFor="symbol">Strategy Symbol</Label>
                  <Input
                    id="symbol"
                    value={newStrategy.symbol}
                    onChange={(e) => setNewStrategy(prev => ({ ...prev, symbol: e.target.value }))}
                    placeholder="e.g. SPY"
                  />
                </div>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="description">Description</Label>
                <textarea
                  id="description"
                  className="min-h-[96px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  value={newStrategy.description}
                  onChange={(e) => setNewStrategy(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Describe the strategy..."
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="targetWeight">Target Weight</Label>
                  <Input
                    id="targetWeight"
                    type="number"
                    value={newStrategy.targetWeight}
                    onChange={(e) => setNewStrategy(prev => ({ ...prev, targetWeight: e.target.value }))}
                    placeholder="e.g. 0.25"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="minWeight">Minimum Weight</Label>
                  <Input
                    id="minWeight"
                    type="number"
                    value={newStrategy.minWeight}
                    onChange={(e) => setNewStrategy(prev => ({ ...prev, minWeight: e.target.value }))}
                    placeholder="e.g. 0.10"
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="maxWeight">Maximum Weight</Label>
                  <Input
                    id="maxWeight"
                    type="number"
                    value={newStrategy.maxWeight}
                    onChange={(e) => setNewStrategy(prev => ({ ...prev, maxWeight: e.target.value }))}
                    placeholder="e.g. 0.40"
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="filename">Filename</Label>
                  <Select value={newStrategy.filename} onValueChange={(value) => setNewStrategy(prev => ({ ...prev, filename: value }))}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select strategy .py file" />
                    </SelectTrigger>
                    <SelectContent>
                      {discoveredFiles.length === 0 ? (
                        <SelectItem value="" disabled>No strategies discovered</SelectItem>
                      ) : (
                        discoveredFiles.map((f) => (
                          <SelectItem key={f} value={f}>{f}</SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">Save your ".py" file in your strategies folder so it appears here.</p>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="color">Color</Label>
                  <div className="flex items-center gap-3">
                    <Input
                      id="color"
                      type="color"
                      value={newStrategy.color}
                      onChange={(e) => setNewStrategy(prev => ({ ...prev, color: e.target.value }))}
                      className="h-9 w-16 p-1"
                    />
                    <span className="text-sm text-muted-foreground">Used later for UI accents and logs</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreateStrategy}>Save</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4">
        {/* Left controls */}
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

        {/* Center summary (show only on large screens to avoid crowding) */}
        <div className="hidden lg:flex items-center gap-4 text-sm text-muted-foreground">
          <span>Total: {totalCount}</span>
          <span>Active: {activeCount}</span>
          <span>Running: {runningCount}</span>
        </div>

        {/* Right: New Strategy button aligned to this row */}
        <Button onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          New Strategy
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
                    {getActiveBadge(strategy.active)}
                    {getRunningBadge(strategy.running)}
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
                  <Button variant="outline" size="sm" onClick={() => handleDeleteStrategy(strategy.symbol)}>
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