import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { StrategyDetails } from './StrategyDetails';
import { getStrategies } from '@/lib/api';
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
  name: string;
  strategy_symbol: string;
  description?: string;
  target_weight?: number | null;
  min_weight?: number | null;
  max_weight?: number | null;
  filename: string;
  params: Record<string, any>;
  color?: string;
  running: boolean;
  active?: boolean;
  // UI-only fields
  type: string;
  pnl: number;
  todayPnl: number;
  positions: number;
  lastUpdate: string;
}

interface StrategyManagerProps {
  onDataChange?: () => void;
}

const StrategyManager: React.FC<StrategyManagerProps> = ({ onDataChange }) => {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null);

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editingStrategy, setEditingStrategy] = useState<Strategy | null>(null);
  const [weightErrors, setWeightErrors] = useState<{target?: string, min?: string, max?: string}>({});
  const [discoveredFiles, setDiscoveredFiles] = useState<string[]>([]);
  // Keys to treat as special weight fields
  const WEIGHT_KEYS = new Set(['target_weight', 'min_weight', 'max_weight']);
  const handleOpenEditDialog = (strategy: Strategy) => {
    setEditingStrategy(JSON.parse(JSON.stringify(strategy))); // Deep copy
    setWeightErrors({});
    setIsEditDialogOpen(true);
  };

  // Prevent arrow key navigation from propagating to parent components (e.g., Tabs)
  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (
      e.key === 'ArrowLeft' ||
      e.key === 'ArrowRight' ||
      e.key === 'ArrowUp' ||
      e.key === 'ArrowDown'
    ) {
      e.stopPropagation();
    }
  };

  const validateWeight = (value: string, fieldName: string): string | null => {
    if (!value || value.trim() === '') return null;
    
    // Allow both . and , as decimal separators
    const normalizedValue = value.replace(',', '.');
    
    // Check if it's a valid number
    if (!/^\d+([.,]\d+)?$/.test(value)) {
      return `${fieldName} must be a valid number`;
    }
    
    const numValue = parseFloat(normalizedValue);
    
    // Check if values > 1 have decimal separator
    if (numValue > 1 && !value.includes('.') && !value.includes(',')) {
      return `${fieldName} > 1 must include decimal separator (e.g., 1.1 or 1,1)`;
    }
    
    if (numValue < 0) {
      return `${fieldName} cannot be negative`;
    }
    
    return null;
  };

  // Normalize any weight value to number or null (accepts string with comma or dot)
  const normalizeToNumber = (v: any): number | null => {
    if (v === null || v === undefined || v === '') return null;
    if (typeof v === 'number') return isNaN(v) ? null : v;
    const s = String(v).replace(',', '.');
    const n = parseFloat(s);
    return isNaN(n) ? null : n;
  };

  // Cross-field validation rules: min <= target and min <= max
  const validateCrossWeights = (weights: { target_weight: any; min_weight: any; max_weight: any; }) => {
    const t = normalizeToNumber(weights.target_weight);
    const mn = normalizeToNumber(weights.min_weight);
    const mx = normalizeToNumber(weights.max_weight);

    const crossErrors: { target?: string; min?: string; max?: string } = {};
    if (mn !== null && t !== null && mn > t) {
      crossErrors.min = 'Min Weight cannot be greater than Target Weight';
    }
    if (mn !== null && mx !== null && mn > mx) {
      crossErrors.min = crossErrors.min
        ? crossErrors.min + ' • Min Weight cannot be greater than Max Weight'
        : 'Min Weight cannot be greater than Max Weight';
    }
    return crossErrors;
  };

  const handleWeightChange = (value: string, field: 'target_weight' | 'min_weight' | 'max_weight') => {
    const fieldNames = {
      target_weight: 'Target Weight',
      min_weight: 'Min Weight', 
      max_weight: 'Max Weight'
    };

    const fieldError = validateWeight(value, fieldNames[field]);
    const errorKey = field.replace('_weight', '') as 'target' | 'min' | 'max';

    // Store the raw string value, convert to number only when valid
    const normalizedValue = value.replace(',', '.');
    const numValue = value === '' ? null : (fieldError ? value : parseFloat(normalizedValue));

    setEditingStrategy(prev => {
      const next = prev ? { ...prev, [field]: numValue } : null;
      if (next) {
        const cross = validateCrossWeights({
          target_weight: next.target_weight,
          min_weight: next.min_weight,
          max_weight: next.max_weight,
        });
        setWeightErrors(prevErrs => ({
          ...prevErrs,
          [errorKey]: fieldError,
          ...cross,
        }));
      } else {
        setWeightErrors(prevErrs => ({ ...prevErrs, [errorKey]: fieldError }));
      }
      return next;
    });
  };

  const handleSaveStrategy = async () => {
    if (!editingStrategy) return;

    // Check for validation errors
    // Re-run cross-field validation to be safe
    const cross = validateCrossWeights({
      target_weight: editingStrategy.target_weight,
      min_weight: editingStrategy.min_weight,
      max_weight: editingStrategy.max_weight,
    });
    if (cross.target || cross.min || cross.max) {
      setWeightErrors(prev => ({ ...prev, ...cross }));
    }

    const hasErrors = Object.values({ ...weightErrors, ...cross }).some(error => error !== null && error !== undefined);
    if (hasErrors) {
      console.error('Cannot save strategy with validation errors');
      return;
    }

    try {
      // Ensure weights are properly converted to numbers with . as decimal separator
      const normalizeWeight = (weight: any) => {
        if (weight === null || weight === undefined || weight === '') return null;
        const str = String(weight).replace(',', '.');
        return parseFloat(str);
      };

      // Build payload with weights folded into params only
      const payload: any = {
        name: editingStrategy.name,
        strategy_symbol: editingStrategy.strategy_symbol,
        description: editingStrategy.description,
        filename: editingStrategy.filename,
        color: editingStrategy.color,
        active: editingStrategy.active,
        params: {
          ...editingStrategy.params,
          target_weight: normalizeWeight(editingStrategy.target_weight),
          min_weight: normalizeWeight(editingStrategy.min_weight),
          max_weight: normalizeWeight(editingStrategy.max_weight),
        },
      };


      const resp = await fetch(`${backendBase}/api/strategies/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const msg = await resp.text();
        console.error('Failed to save strategy:', msg);
        return;
      }

      await fetchStrategies();
      setIsEditDialogOpen(false);
      setEditingStrategy(null);
      onDataChange?.();
    } catch (e) {
      console.error('Error saving strategy', e);
    }
  };

  const [newStrategy, setNewStrategy] = useState({
    name: '',
    symbol: '',
    description: '',
    filename: '',
    color: '#4f46e5',
  });

  // Create-dialog params (excluding weight keys) and weights
  const [newParams, setNewParams] = useState<Record<string, any>>({});
  const [createWeights, setCreateWeights] = useState<{ target_weight: any; min_weight: any; max_weight: any }>({
    target_weight: null,
    min_weight: null,
    max_weight: null,
  });

  const backendBase = 'http://127.0.0.1:8000';

  const fetchStrategies = async () => {
    setLoading(true);
    try {
      const data = await getStrategies(false);
      const discovered: string[] = data.discovered_strategies || [];
      setDiscoveredFiles(discovered);
      const saved: any[] = data.strategies || [];

      const normalized: Strategy[] = saved.map((row) => {
        const symbol = String(row.strategy_symbol || '').toUpperCase();
        const filename = row.filename || '';
        const run = !!row.running;

        let params: Record<string, any> = {};
        if (typeof row.params === 'string' && row.params) {
          try {
            params = JSON.parse(row.params);
          } catch (e) {
            console.error('Failed to parse params for', symbol, e);
          }
        }

        // Prefer weights from params; fall back to row for backwards compat
        const pTarget = params?.target_weight ?? row.target_weight ?? null;
        const pMin = params?.min_weight ?? row.min_weight ?? null;
        const pMax = params?.max_weight ?? row.max_weight ?? null;

        return {
          name: row.name || symbol,
          strategy_symbol: symbol,
          description: row.description,
          target_weight: pTarget,
          min_weight: pMin,
          max_weight: pMax,
          filename,
          params,
          color: row.color,
          running: run,
          type: filename ? filename.replace('_strategy.py', '') : (row.name || symbol),
          pnl: 0,
          todayPnl: 0,
          positions: 0,
          lastUpdate: run ? 'just now' : '-',
          active: !!row.active,
        };
      });

      // Sort active strategies first
      normalized.sort((a, b) => {
        if (a.active === b.active) return 0;
        return a.active ? -1 : 1;
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

  const handleStrategyAction = async (strategy_symbol: string, action: 'start' | 'stop') => {
    try {
      const response = await fetch(`${backendBase}/api/strategies/${strategy_symbol}/${action}`, { method: 'POST' });
      if (response.ok) {
        await fetchStrategies();
        onDataChange?.();
      }
    } catch (error) {
      console.error(`Failed to ${action} strategy:`, error);
    }
  };

  const handleDeleteStrategy = async (strategy_symbol: string) => {
    try {
      const resp = await fetch(`${backendBase}/api/strategies/${strategy_symbol}/delete`, { method: 'POST' });
      if (!resp.ok) {
        const msg = await resp.text();
        console.error('Failed to delete strategy:', msg);
        return;
      }
      await fetchStrategies();
      onDataChange?.();
    } catch (e) {
      console.error('Error deleting strategy', e);
    }
  };

  const handleCreateStrategy = async () => {
    try {
      // Normalize weights to numbers or null
      const normalizeWeight = (weight: any) => {
        if (weight === null || weight === undefined || weight === '') return null;
        const str = String(weight).replace(',', '.');
        const n = parseFloat(str);
        return isNaN(n) ? null : n;
      };

      // Include weights inside params only
      const payload = {
        name: newStrategy.name,
        strategy_symbol: newStrategy.symbol.toUpperCase(),
        description: newStrategy.description,
        filename: newStrategy.filename || null,
        params: {
          ...newParams,
          target_weight: normalizeWeight(createWeights.target_weight),
          min_weight: normalizeWeight(createWeights.min_weight),
          max_weight: normalizeWeight(createWeights.max_weight),
        },
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
      onDataChange?.();
      setIsCreateDialogOpen(false);
      setNewStrategy({
        name: '',
        symbol: '',
        description: '',
        filename: '',
        color: '#4f46e5',
      });
      setNewParams({});
      setCreateWeights({ target_weight: null, min_weight: null, max_weight: null });
    } catch (e) {
      console.error('Error saving strategy metadata', e);
    }
  };

  const toggleActive = async (strategy_symbol: string, value: boolean) => {
    try {
      const endpoint = value ? 'activate' : 'deactivate';
      const resp = await fetch(`${backendBase}/api/strategies/${strategy_symbol}/${endpoint}`, { method: 'POST' });
      if (!resp.ok) {
        const msg = await resp.text();
        console.error(`Failed to ${endpoint} strategy:`, msg);
      }
      await fetchStrategies();
      onDataChange?.();
    } catch (e) {
      console.error('Error toggling strategy active state', e);
    }
  };

  const getStatusIcon = (running: boolean, color?: string) => {
    if (color) {
      return running ? <Play className="h-4 w-4" style={{ color }} /> : <Square className="h-4 w-4" style={{ color }} />;
    }
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

  if (selectedStrategy) {
    return (
      <StrategyDetails 
        strategySymbol={selectedStrategy} 
        onBack={() => setSelectedStrategy(null)} 
      />
    );
  }

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
              {/* Weights and filename/color */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="filename">Filename</Label>
                  <Select value={newStrategy.filename} onValueChange={async (value) => {
                    setNewStrategy(prev => ({ ...prev, filename: value }));
                    if (!value) return;
                    try {
                      const res = await fetch(`${backendBase}/api/strategies/params-from-file?filename=${encodeURIComponent(value)}`);
                      if (res.ok) {
                        const data = await res.json();
                        const params = (data && data.params) ? data.params : {};
                        const { target_weight = null, min_weight = null, max_weight = null, ...rest } = params || {};
                        setCreateWeights({ target_weight, min_weight, max_weight });
                        setNewParams(rest);
                      }
                    } catch (e) {
                      console.error('Failed to load params from file', e);
                    }
                  }}>
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

              {/* Create dialog weights */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="grid gap-2">
                  <Label>Target Weight</Label>
                  <Input
                    type="text"
                    inputMode="decimal"
                    value={createWeights.target_weight ?? ''}
                    onChange={(e) => setCreateWeights(prev => ({ ...prev, target_weight: e.target.value }))}
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Min Weight</Label>
                  <Input
                    type="text"
                    inputMode="decimal"
                    value={createWeights.min_weight ?? ''}
                    onChange={(e) => setCreateWeights(prev => ({ ...prev, min_weight: e.target.value }))}
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Max Weight</Label>
                  <Input
                    type="text"
                    inputMode="decimal"
                    value={createWeights.max_weight ?? ''}
                    onChange={(e) => setCreateWeights(prev => ({ ...prev, max_weight: e.target.value }))}
                  />
                </div>
              </div>

              {/* Parameters loaded from file (excluding weight keys) */}
              {Object.keys(newParams).length > 0 && (
                <>
                  <h3 className="font-semibold text-lg mt-2 border-b pb-2">Parameters</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {Object.entries(newParams).map(([key, value]) => (
                      <div className="grid gap-2" key={key}>
                        <Label htmlFor={`create-param-${key}`}>{key.replace(/_/g, ' ')}</Label>
                        <Input
                          id={`create-param-${key}`}
                          type={typeof value === 'number' ? 'number' : 'text'}
                          step={typeof value === 'number' ? 'any' : undefined}
                          value={value ?? ''}
                          onChange={(e) => {
                            const rawValue = e.target.value.replace(',', '.');
                            const newValue = (typeof value === 'number') ? (rawValue === '' ? null : parseFloat(rawValue)) : rawValue;
                            setNewParams(prev => ({ ...prev, [key]: newValue }));
                          }}
                        />
                      </div>
                    ))}
                  </div>
                </>
              )}
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

      {/* Edit Strategy Dialog */}
      {editingStrategy && (
        <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
          <DialogContent className="sm:max-w-[700px] max-h-[85vh]">
            <DialogHeader>
              <DialogTitle>Edit Strategy: {editingStrategy.name}</DialogTitle>
            </DialogHeader>
            <div className="grid gap-4 py-4 max-h-[60vh] overflow-y-auto pr-6">
              {/* Metadata fields */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label>Strategy Name</Label>
                  <Input 
                    value={editingStrategy.name}
                    onChange={(e) => setEditingStrategy(s => s ? {...s, name: e.target.value} : null)}
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Strategy Symbol</Label>
                  <Input value={editingStrategy.strategy_symbol} disabled />
                </div>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="edit-description">Description</Label>
                <textarea
                  id="edit-description"
                  className="min-h-[96px] rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  value={editingStrategy.description || ''}
                  onChange={(e) => setEditingStrategy(s => s ? {...s, description: e.target.value} : null)}
                  placeholder="Describe the strategy..."
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
                <div className="grid gap-2">
                  <Label>Target Weight</Label>
                  <Input 
                    type="text"
                    inputMode="decimal"
                    value={editingStrategy.target_weight ?? ''}
                    onChange={(e) => handleWeightChange(e.target.value, 'target_weight')}
                    onKeyDown={handleInputKeyDown}
                    className={weightErrors.target ? 'border-red-500' : ''}
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Min Weight</Label>
                  <Input 
                    type="text"
                    inputMode="decimal"
                    value={editingStrategy.min_weight ?? ''}
                    onChange={(e) => handleWeightChange(e.target.value, 'min_weight')}
                    onKeyDown={handleInputKeyDown}
                    className={weightErrors.min ? 'border-red-500' : ''}
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Max Weight</Label>
                  <Input 
                    type="text"
                    inputMode="decimal"
                    value={editingStrategy.max_weight ?? ''}
                    onChange={(e) => handleWeightChange(e.target.value, 'max_weight')}
                    onKeyDown={handleInputKeyDown}
                    className={weightErrors.max ? 'border-red-500' : ''}
                  />
                </div>
              </div>
              <div className="grid gap-2 mt-4">
                  <Label>Color</Label>
                  <Input 
                    type="color"
                    value={editingStrategy.color || '#000000'}
                    onChange={(e) => setEditingStrategy(s => s ? {...s, color: e.target.value} : null)}
                    className="h-9 w-16 p-1"
                  />
              </div>

              {/* Parameter fields (exclude weights; they are edited above) */}
              <h3 className="font-semibold text-lg mt-4 border-b pb-2">Parameters</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {Object.entries(editingStrategy.params).filter(([key]) => !WEIGHT_KEYS.has(key)).map(([key, value]) => {
                  const isNumber = typeof value === 'number';
                  return (
                    <div className="grid gap-2" key={key}>
                      <Label htmlFor={`param-${key}`}>{key.replace(/_/g, ' ')}</Label>
                      <Input
                        id={`param-${key}`}
                        type={isNumber ? 'number' : 'text'}
                        step={isNumber ? 'any' : undefined}
                        value={value ?? ''}
                        onChange={(e) => {
                          const rawValue = e.target.value.replace(',', '.');
                          const newValue = isNumber ? (rawValue === '' ? null : parseFloat(rawValue)) : rawValue;
                          setEditingStrategy(s => s ? { 
                            ...s, 
                            params: { ...s.params, [key]: newValue }
                          } : null);
                        }}
                      />
                    </div>
                  )
                })}
              </div>
            </div>
            
            {/* Validation Messages Section */}
            <div className="min-h-[60px] px-4 py-2 bg-gray-50 border-t">
              {(weightErrors.target || weightErrors.min || weightErrors.max) && (
                <div className="space-y-1">
                  <p className="text-sm font-medium text-gray-700">Validation Errors:</p>
                  {weightErrors.target && (
                    <p className="text-sm text-red-500">• Target Weight: {weightErrors.target}</p>
                  )}
                  {weightErrors.min && (
                    <p className="text-sm text-red-500">• Min Weight: {weightErrors.min}</p>
                  )}
                  {weightErrors.max && (
                    <p className="text-sm text-red-500">• Max Weight: {weightErrors.max}</p>
                  )}
                </div>
              )}
            </div>
            
            <div className="flex justify-end gap-2 px-4 pb-4">
              <Button variant="outline" onClick={() => setIsEditDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleSaveStrategy}>Save Changes</Button>
            </div>
          </DialogContent>
        </Dialog>
      )}

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
          <Card 
            key={strategy.strategy_symbol}
            className="overflow-hidden cursor-pointer hover:border-primary transition-colors"
            style={strategy.color ? { borderLeft: `4px solid ${strategy.color}` } : undefined}
            onClick={() => setSelectedStrategy(strategy.strategy_symbol)}
          >
            <CardHeader>
              <div className="flex justify-between items-start">
                <div className="space-y-1">
                  <CardTitle className="flex items-center gap-2">
                    {getStatusIcon(strategy.running, strategy.color)}
                    {strategy.name}
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    {getActiveBadge(strategy.active)}
                    {getRunningBadge(strategy.running)}
                    <Badge variant="outline" style={{ borderColor: strategy.color, color: strategy.color }}>{strategy.strategy_symbol}</Badge>
                  </div>
                </div>
                <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                  <div className="flex items-center gap-2 mr-2">
                    <Switch checked={!!strategy.active} onCheckedChange={(v) => toggleActive(strategy.strategy_symbol, v)} />
                    <span className="text-sm text-muted-foreground">Active</span>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleStrategyAction(strategy.strategy_symbol, strategy.running ? 'stop' : 'start')}
                  >
                    {strategy.running ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleStrategyAction(strategy.strategy_symbol, 'stop')}
                  >
                    <Square className="h-4 w-4" />
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => handleOpenEditDialog(strategy)}>
                    <Edit className="h-4 w-4" />
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => handleDeleteStrategy(strategy.strategy_symbol)}>
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