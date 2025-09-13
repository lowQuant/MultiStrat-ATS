import React, { useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Database, RefreshCcw, Trash } from 'lucide-react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

type ReadResponse = {
  success: boolean;
  columns?: string[];
  rows?: any[][];
  total?: number;
  error?: string;
};

const ArcticDBView: React.FC = () => {
  const [libraries, setLibraries] = useState<string[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [library, setLibrary] = useState<string>("");
  const [symbol, setSymbol] = useState<string>("");
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<any[][]>([]);
  const [total, setTotal] = useState<number>(0);
  const [offset, setOffset] = useState<number>(0);
  const [limit, setLimit] = useState<number>(200);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [confirmDelete, setConfirmDelete] = useState<null | 'delete_symbol' | 'delete_library'>(null);

  const canRead = useMemo(() => !!library && !!symbol, [library, symbol]);

  const fetchLibraries = async () => {
    try {
      setError("");
      const res = await fetch('http://127.0.0.1:8000/api/arctic/libraries');
      const data = (await res.json()) as { success: boolean; libraries?: string[]; error?: string };
      if (data.success) {
        setLibraries(data.libraries || []);
      } else {
        setError(data.error || 'Failed to load libraries');
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  };

  const handleDeleteLibrary = async () => {
    if (!library) return;
    try {
      setLoading(true);
      setError("");
      const res = await fetch(`http://127.0.0.1:8000/api/arctic/delete_library?library=${encodeURIComponent(library)}`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (data?.success) {
        // Refresh libraries and clear selections/table
        await fetchLibraries();
        setLibrary("");
        setSymbols([]);
        setSymbol("");
        setColumns([]);
        setRows([]);
        setTotal(0);
        setOffset(0);
      } else {
        setError(data?.error || 'Failed to delete library');
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  const fetchSymbols = async (lib: string) => {
    try {
      setError("");
      const res = await fetch(`http://127.0.0.1:8000/api/arctic/symbols?library=${encodeURIComponent(lib)}`);
      const data = (await res.json()) as { success: boolean; symbols?: string[]; error?: string };
      if (data.success) {
        setSymbols(data.symbols || []);
      } else {
        setError(data.error || 'Failed to load symbols');
      }
    } catch (e: any) {
      setError(String(e?.message || e));
    }
  };

  const fetchTable = async () => {
    if (!canRead) return;
    try {
      setLoading(true);
      setError("");
      const res = await fetch(`http://127.0.0.1:8000/api/arctic/read?library=${encodeURIComponent(library)}&symbol=${encodeURIComponent(symbol)}&limit=${limit}&offset=${offset}`);
      const data = (await res.json()) as ReadResponse;
      if (data.success) {
        setColumns(data.columns || []);
        setRows(data.rows || []);
        setTotal(data.total || 0);
      } else {
        setColumns([]);
        setRows([]);
        setTotal(0);
        setError(data.error || 'Failed to load data');
      }
    } catch (e: any) {
      setColumns([]);
      setRows([]);
      setTotal(0);
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLibraries();
  }, []);

  useEffect(() => {
    if (library) {
      fetchSymbols(library);
      setSymbol("");
      setColumns([]);
      setRows([]);
      setTotal(0);
      setOffset(0);
    } else {
      setSymbols([]);
    }
  }, [library]);

  useEffect(() => {
    // re-fetch when symbol, offset, or limit changes
    if (symbol) fetchTable();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, offset, limit]);

  const nextPage = () => {
    if (offset + limit < total) setOffset(offset + limit);
  };
  const prevPage = () => {
    if (offset > 0) setOffset(Math.max(0, offset - limit));
  };

  const handleDeleteSymbol = async () => {
    if (!library || !symbol) return;
    try {
      setLoading(true);
      setError("");
      const res = await fetch(`http://127.0.0.1:8000/api/arctic/delete_symbol?library=${encodeURIComponent(library)}&symbol=${encodeURIComponent(symbol)}`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (data?.success) {
        // Refresh symbol list and clear table
        await fetchSymbols(library);
        setSymbol("");
        setColumns([]);
        setRows([]);
        setTotal(0);
        setOffset(0);
      } else {
        setError(data?.error || 'Failed to delete symbol');
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
            <Database className="h-5 w-5" />
            <CardTitle>ArcticDB</CardTitle>
          </div>
          <Button variant="outline" size="sm" onClick={fetchLibraries} title="Refresh libraries">
            <RefreshCcw className="h-4 w-4 mr-2" /> Refresh
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            <div>
              <Label>Library</Label>
              <Select value={library} onValueChange={(v) => setLibrary(v)}>
                <SelectTrigger>
                  <SelectValue placeholder="Select library" />
                </SelectTrigger>
                <SelectContent>
                  {libraries.map((lib) => (
                    <SelectItem key={lib} value={lib}>{lib}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Symbol</Label>
              <Select value={symbol} onValueChange={(v) => setSymbol(v)} disabled={!library}>
                <SelectTrigger>
                  <SelectValue placeholder={library ? 'Select symbol' : 'Select library first'} />
                </SelectTrigger>
                <SelectContent>
                  {symbols.map((sym) => (
                    <SelectItem key={sym} value={sym}>{sym}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Rows per page</Label>
              <Input className="w-24" type="number" min={1} max={10000} value={limit} onChange={(e) => setLimit(Math.max(1, Math.min(10000, Number(e.target.value) || 1)))} />
            </div>
            {/* Top controls: 4th column with paging + delete menu */}
            <div className="flex gap-2 items-end justify-end">
              <Button variant="secondary" onClick={prevPage} disabled={offset === 0 || !symbol}>Prev</Button>
              <Button variant="secondary" onClick={nextPage} disabled={offset + limit >= total || !symbol}>Next</Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="icon" title="Delete">
                    <Trash className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem disabled={!symbol || loading} onClick={() => setConfirmDelete('delete_symbol')}>
                    Delete symbol{symbol ? ` (${symbol})` : ''}
                  </DropdownMenuItem>
                  <DropdownMenuItem disabled={!library || loading} onClick={() => setConfirmDelete('delete_library')}>
                    Delete library{library ? ` (${library})` : ''}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          {/* Confirm Delete Dialog */}
          <AlertDialog open={!!confirmDelete} onOpenChange={(open) => !open && setConfirmDelete(null)}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {confirmDelete === 'delete_library' ? 'Delete Library' : 'Delete Symbol'}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {confirmDelete === 'delete_library'
                    ? `This will permanently delete the entire library${library ? ` "${library}"` : ''}. This action cannot be undone.`
                    : `This will permanently delete the symbol${symbol ? ` "${symbol}"` : ''} from library${library ? ` "${library}"` : ''}. This action cannot be undone.`}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel onClick={() => setConfirmDelete(null)}>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={async () => {
                    if (confirmDelete === 'delete_symbol') {
                      await handleDeleteSymbol();
                    } else if (confirmDelete === 'delete_library') {
                      await handleDeleteLibrary();
                    }
                    setConfirmDelete(null);
                  }}
                  className="bg-red-600 hover:bg-red-700"
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          {error && (
            <div className="text-sm text-red-600">{error}</div>
          )}

          {/* Data table */}
          <div className="overflow-x-auto border rounded-md">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  {columns.map((c) => (
                    <th key={c} className="text-left p-2 whitespace-nowrap">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, idx) => (
                  <tr key={idx} className="border-b hover:bg-muted/50">
                    {r.map((cell, i) => (
                      <td key={i} className="p-2 whitespace-nowrap">{String(cell)}</td>
                    ))}
                  </tr>
                ))}
                {!rows.length && (
                  <tr>
                    <td className="p-4 text-muted-foreground" colSpan={columns.length || 1}>
                      {symbol ? 'No rows' : 'Select a library and symbol to view data'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Table footer summary only */}
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs text-muted-foreground">
              {symbol ? (
                <span>Showing {rows.length ? `${offset + 1}-${Math.min(offset + limit, total)}` : 0} of {total}</span>
              ) : (
                <span>Select a library and symbol to view data</span>
              )}
            </div>
          </div>

        </CardContent>
      </Card>
    </div>
  );
};

export default ArcticDBView;
