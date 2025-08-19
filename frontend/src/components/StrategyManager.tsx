import { useState } from 'react';
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
  Pause, 
  Square, 
  Plus, 
  Edit, 
  Trash2,
  TrendingUp,
  TrendingDown,
  Activity
} from 'lucide-react';

interface Strategy {
  id: string;
  name: string;
  type: string;
  status: 'running' | 'paused' | 'stopped';
  pnl: number;
  todayPnl: number;
  positions: number;
  lastUpdate: string;
}

const StrategyManager = () => {
  const [strategies, setStrategies] = useState<Strategy[]>([
    {
      id: '1',
      name: 'Mean Reversion SPY',
      type: 'mean_reversion',
      status: 'running',
      pnl: 3250.75,
      todayPnl: 125.50,
      positions: 3,
      lastUpdate: '2 min ago'
    },
    {
      id: '2',
      name: 'Momentum QQQ',
      type: 'momentum',
      status: 'running',
      pnl: -850.25,
      todayPnl: 75.20,
      positions: 2,
      lastUpdate: '1 min ago'
    },
    {
      id: '3',
      name: 'Pairs Trade Tech',
      type: 'pairs_trading',
      status: 'paused',
      pnl: 1250.00,
      todayPnl: 0.00,
      positions: 0,
      lastUpdate: '15 min ago'
    }
  ]);

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [newStrategy, setNewStrategy] = useState({
    name: '',
    type: '',
    symbol: '',
    capital: '',
    riskLimit: ''
  });

  const handleStrategyAction = async (strategyId: string, action: 'start' | 'pause' | 'stop') => {
    // API call to FastAPI backend
    try {
      const response = await fetch(`/api/strategies/${strategyId}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      if (response.ok) {
        setStrategies(prev => prev.map(strategy => 
          strategy.id === strategyId 
            ? { ...strategy, status: action === 'start' ? 'running' : action as any }
            : strategy
        ));
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

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running': return <Play className="h-4 w-4 text-profit" />;
      case 'paused': return <Pause className="h-4 w-4 text-warning" />;
      case 'stopped': return <Square className="h-4 w-4 text-muted-foreground" />;
      default: return <Activity className="h-4 w-4" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const variants = {
      running: 'default',
      paused: 'secondary',
      stopped: 'outline'
    };
    return <Badge variant={variants[status as keyof typeof variants] as any}>{status}</Badge>;
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

      <div className="grid gap-4">
        {strategies.map((strategy) => (
          <Card key={strategy.id}>
            <CardHeader>
              <div className="flex justify-between items-start">
                <div className="space-y-1">
                  <CardTitle className="flex items-center gap-2">
                    {getStatusIcon(strategy.status)}
                    {strategy.name}
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    {getStatusBadge(strategy.status)}
                    <Badge variant="outline">{strategy.type.replace('_', ' ')}</Badge>
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleStrategyAction(strategy.id, strategy.status === 'running' ? 'pause' : 'start')}
                  >
                    {strategy.status === 'running' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleStrategyAction(strategy.id, 'stop')}
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