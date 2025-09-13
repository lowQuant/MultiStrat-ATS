import React, { useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Binoculars, RefreshCcw, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

type ScannerCode = { code: string; display_name: string };
type ScannerFilter = { code: string; display_name: string; unit?: string; data_type?: string; min?: string; max?: string };

const Screener: React.FC = () => {
  const [codes, setCodes] = useState<ScannerCode[]>([]);
  const [filters, setFilters] = useState<ScannerFilter[]>([]);
  const [instrument, setInstrument] = useState<string>('STK');
  const [locationCode, setLocationCode] = useState<string>('STK.US.MAJOR');
  const [scanCode, setScanCode] = useState<string>('');
  const [selectedFilters, setSelectedFilters] = useState<Record<string, string>>({});
  const [filterQuery, setFilterQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [results, setResults] = useState<any[]>([]);

  const loadOptions = async () => {
    try {
      setError('');
      const res = await fetch('http://127.0.0.1:8000/api/scanner/options');
      const data = await res.json();
      if (data.success) {
        // Extra client-side safety: exclude anything with 'bond'
        const cleanCodes = (data.codes || []).filter((c: ScannerCode) =>
          !/bond/i.test(c.code) && !/bond/i.test(c.display_name || '')
        );
        const cleanFilters = (data.filters || []).filter((f: ScannerFilter) =>
          !/bond/i.test(f.code) && !/bond/i.test(f.display_name || '')
        );
        setCodes(cleanCodes);
        setFilters(cleanFilters);
        if (!scanCode && cleanCodes.length) setScanCode(cleanCodes[0].code);
      } else {
        setError(data.error || 'Failed to load scanner options');
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  };

  const filtersMap: Record<string, ScannerFilter> = React.useMemo(() => {
    const m: Record<string, ScannerFilter> = {};
    filters.forEach((f) => { m[f.code] = f; });
    return m;
  }, [filters]);

  const fuzzyMatch = (text: string, query: string) => {
    if (!query) return true;
    const t = (text || '').toLowerCase();
    const q = query.toLowerCase();
    // simple includes or all tokens present
    if (t.includes(q)) return true;
    const tokens = q.split(/\s+/).filter(Boolean);
    return tokens.every(tok => t.includes(tok));
  };

  const availableFilters = React.useMemo(() => {
    const selectedSet = new Set(Object.keys(selectedFilters));
    return filters.filter((f) => !selectedSet.has(f.code) && (
      fuzzyMatch(f.display_name || '', filterQuery) ||
      fuzzyMatch(f.code, filterQuery)
    ));
  }, [filters, selectedFilters, filterQuery]);

  useEffect(() => { loadOptions(); }, []);

  const addFilter = (code: string) => {
    setSelectedFilters((prev) => ({ ...(code in prev ? prev : { ...prev, [code]: '' }) }));
  };
  const removeFilter = (code: string) => {
    setSelectedFilters((prev) => {
      const next = { ...prev } as Record<string, string>;
      delete next[code];
      return next;
    });
  };

  const onFilterValueChange = (code: string, value: string) => {
    setSelectedFilters((prev) => ({ ...prev, [code]: value }));
  };

  const runScan = async () => {
    if (!scanCode) return;
    try {
      setLoading(true);
      setError('');
      setResults([]);
      const payload = {
        instrument,
        locationCode,
        scanCode,
        filters: Object.entries(selectedFilters)
          .filter(([_, v]) => v !== undefined)
          .map(([tag, value]) => ({ tag, value })),
      };
      const res = await fetch('http://127.0.0.1:8000/api/scanner/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.success) {
        setResults(data.data || []);
      } else {
        setError(data.error || 'Scan failed');
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div className="flex items-center gap-2">
            <Binoculars className="h-5 w-5" />
            <CardTitle>Market Screener</CardTitle>
          </div>
          <Button variant="outline" size="sm" onClick={loadOptions} title="Refresh options">
            <RefreshCcw className="h-4 w-4 mr-2" /> Refresh
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Controls */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            <div>
              <Label>Instrument</Label>
              <Input value={instrument} onChange={(e) => setInstrument(e.target.value)} />
            </div>
            <div>
              <Label>Location</Label>
              <Input value={locationCode} onChange={(e) => setLocationCode(e.target.value)} />
            </div>
            <div className="md:col-span-2">
              <Label>Scan Code</Label>
              <Select value={scanCode} onValueChange={setScanCode}>
                <SelectTrigger>
                  <SelectValue placeholder="Select scan code" />
                </SelectTrigger>
                <SelectContent>
                  {codes.map((c) => (
                    <SelectItem key={c.code} value={c.code}>
                      {c.display_name || c.code}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Filters */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label>Filters</Label>
              <div className="text-xs text-muted-foreground">Search and add filters; set values below</div>
            </div>
            {/* Searchable dropdown */}
            <div className="border rounded-md bg-muted/30">
              <div className="p-2 border-b flex items-center gap-2">
                <Input
                  placeholder="Search filters (auto-correct supported by token match)"
                  value={filterQuery}
                  onChange={(e) => setFilterQuery(e.target.value)}
                />
              </div>
              <div className="max-h-56 overflow-auto">
                {availableFilters.length === 0 ? (
                  <div className="p-3 text-sm text-muted-foreground">No filters match</div>
                ) : (
                  <ul className="divide-y">
                    {availableFilters.map((f) => (
                      <li
                        key={f.code}
                        className="p-2 hover:bg-muted/50 cursor-pointer flex items-center justify-between"
                        onClick={() => addFilter(f.code)}
                        title={f.code}
                      >
                        <div>
                          <div className="text-sm font-medium">{f.display_name || f.code}</div>
                          <div className="text-xs text-muted-foreground">{f.code} {f.unit ? `(${f.unit})` : ''}</div>
                        </div>
                        <span className="text-xs text-primary">Add</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            {/* Selected filters list */}
            {Object.keys(selectedFilters).length > 0 && (
              <div className="space-y-2">
                <div className="text-sm font-medium">Selected Filters</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Object.keys(selectedFilters).map((code) => {
                    const meta = filtersMap[code];
                    return (
                      <div key={code} className="flex items-center gap-2 border rounded-md p-2 bg-background">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{meta?.display_name || code}</div>
                          <div className="text-xs text-muted-foreground truncate">{code} {meta?.unit ? `(${meta.unit})` : ''}</div>
                        </div>
                        <Input
                          placeholder="value"
                          className="w-28"
                          value={selectedFilters[code]}
                          onChange={(e) => onFilterValueChange(code, e.target.value)}
                        />
                        <Button variant="outline" size="sm" onClick={() => removeFilter(code)}>Remove</Button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex justify-end">
            <Button onClick={runScan} disabled={!scanCode || loading}>
              <Play className="h-4 w-4 mr-2" /> {loading ? 'Scanning…' : 'Scan'}
            </Button>
          </div>

          {error && <div className="text-sm text-red-600">{error}</div>}

          {/* Results */}
          {!!results.length && (
            <div className="space-y-6">
              {results.map((r: any, idx: number) => (
                <Card key={`${r.symbol}-${idx}`}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <div className="text-base font-semibold">{r.symbol}</div>
                      {typeof r.rank !== 'undefined' && (
                        <div className="text-xs text-muted-foreground">Rank {r.rank}</div>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="w-full max-w-[1100px] h-[480px] border rounded-md overflow-hidden">
                      <iframe
                        title={`tv-${r.symbol}-${idx}`}
                        src={`https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(r.symbol || '')}&interval=D&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=var(--background)&studies=[]&hideideas=1&theme=light#`}
                        width="100%"
                        height="100%"
                        frameBorder={0}
                        allowTransparency
                        scrolling="no"
                      />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Screener;
