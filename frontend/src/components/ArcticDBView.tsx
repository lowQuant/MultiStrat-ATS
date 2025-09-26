import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { ChevronsUpDown, Check, Database, Filter as FilterIcon, RefreshCcw, Trash, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';
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

type FilterOperator = 'eq' | 'ne' | 'lt' | 'lte' | 'gt' | 'gte' | 'contains' | 'startswith' | 'endswith';

type TableFilter = {
  id: string;
  column: string;
  operator: FilterOperator;
  value: string;
};

const FILTER_OPERATOR_OPTIONS: { value: FilterOperator; label: string }[] = [
  { value: 'eq', label: 'Equals' },
  { value: 'ne', label: 'Not equal' },
  { value: 'gt', label: 'Greater than' },
  { value: 'gte', label: 'Greater or equal' },
  { value: 'lt', label: 'Less than' },
  { value: 'lte', label: 'Less or equal' },
  { value: 'contains', label: 'Contains' },
  { value: 'startswith', label: 'Starts with' },
  { value: 'endswith', label: 'Ends with' },
];

const createFilterId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `filter-${Math.random().toString(36).slice(2, 10)}`;
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
  const [sortBy, setSortBy] = useState<string>("__index__");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [filters, setFilters] = useState<TableFilter[]>([]);
  const [confirmDelete, setConfirmDelete] = useState<null | 'delete_symbol' | 'delete_library'>(null);
  const [libraryOpen, setLibraryOpen] = useState<boolean>(false);
  const [symbolOpen, setSymbolOpen] = useState<boolean>(false);
  const tableContainerRef = useRef<HTMLDivElement | null>(null);

  const canRead = useMemo(() => !!library && !!symbol, [library, symbol]);

  const columnOptions = useMemo(() => {
    const seen = new Set<string>();
    const normalized = columns
      .map((c) => String(c))
      .filter((c) => {
        if (seen.has(c)) return false;
        seen.add(c);
        return true;
      });
    return [{ value: '__index__', label: 'Index' }, ...normalized.map((col) => ({ value: col, label: col }))];
  }, [columns]);

  const filterPayload = useMemo(() => {
    const active = filters
      .filter((flt) => flt.column && flt.operator && flt.value !== undefined && flt.value !== null && String(flt.value).trim() !== '')
      .map((flt) => ({ column: flt.column, operator: flt.operator, value: flt.value }));
    return active.length ? JSON.stringify(active) : null;
  }, [filters]);

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
      const params = new URLSearchParams({
        library,
        symbol,
        limit: String(limit),
        offset: String(offset),
      });
      if (sortBy) params.set("sort_by", sortBy);
      if (sortOrder) params.set("sort_order", sortOrder);
      if (filterPayload) params.set("filters", filterPayload);
      const res = await fetch(`http://127.0.0.1:8000/api/arctic/read?${params.toString()}`);
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
      setSortBy("__index__");
      setSortOrder("asc");
      setFilters([]);
      setSymbolOpen(false);
    } else {
      setSymbols([]);
    }
  }, [library]);

  useEffect(() => {
    // re-fetch when symbol, offset, or limit changes
    if (symbol) fetchTable();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, offset, limit, sortBy, sortOrder, filterPayload]);

  useEffect(() => {
    setFilters((prev) => {
      if (!columns.length) {
        return prev.length ? [] : prev;
      }
      const next = prev.filter((flt) => flt.column === '__index__' || columns.includes(flt.column));
      return next.length === prev.length ? prev : next;
    });
  }, [columns]);

  const handleHeaderSort = (column: string, columnIndex: number) => {
    const targetSort = columnIndex === 0 ? "__index__" : column;
    setOffset(0);
    setSortBy((prevSort) => {
      if (prevSort === targetSort) {
        setSortOrder((prevOrder) => (prevOrder === "asc" ? "desc" : "asc"));
        return prevSort;
      }
      setSortOrder("asc");
      return targetSort;
    });
  };

  const renderSortIndicator = (column: string, columnIndex: number) => {
    const isSorted =
      (columnIndex === 0 && sortBy === "__index__") ||
      (columnIndex !== 0 && sortBy === column);
    if (!isSorted) return null;
    return <span className="ml-1 text-xs">{sortOrder === "asc" ? "▲" : "▼"}</span>;
  };

  const handleAddFilter = () => {
    if (!columnOptions.length) return;
    const defaultColumn = columnOptions[0]?.value ?? '__index__';
    const nextFilter: TableFilter = {
      id: createFilterId(),
      column: defaultColumn,
      operator: 'eq',
      value: '',
    };
    setFilters((prev) => [...prev, nextFilter]);
    setOffset(0);
  };

  const handleFilterChange = (id: string, updates: Partial<Omit<TableFilter, 'id'>>) => {
    setFilters((prev) => prev.map((flt) => (flt.id === id ? { ...flt, ...updates } : flt)));
    setOffset(0);
  };

  const handleRemoveFilter = (id: string) => {
    setFilters((prev) => prev.filter((flt) => flt.id !== id));
    setOffset(0);
  };

  const hasFilterButton = columns.length > 0;

  useEffect(() => {
    const container = tableContainerRef.current;
    if (!container) return;

    const handleWheel = (event: WheelEvent) => {
      if (!container) return;
      const primarilyHorizontal = Math.abs(event.deltaX) > Math.abs(event.deltaY);
      if (!primarilyHorizontal) return;
      event.preventDefault();
      event.stopPropagation();
      container.scrollLeft += event.deltaX;
    };

    container.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      container.removeEventListener('wheel', handleWheel);
    };
  }, [columns, symbol]);

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
              <Popover open={libraryOpen} onOpenChange={setLibraryOpen}>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={false}
                    className="w-full justify-between"
                  >
                    {library || 'Select library'}
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="p-0 w-72" align="start">
                  <Command>
                    <CommandInput placeholder="Search libraries..." />
                    <CommandEmpty>No libraries found.</CommandEmpty>
                    <CommandList>
                      <CommandGroup>
                        {libraries.map((lib) => (
                          <CommandItem
                            key={lib}
                            value={lib}
                            onSelect={() => {
                              setLibrary(lib);
                              setLibraryOpen(false);
                            }}
                          >
                            <Check className={cn('mr-2 h-4 w-4', library === lib ? 'opacity-100' : 'opacity-0')} />
                            {lib}
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            </div>
            <div>
              <Label>Symbol</Label>
              <Popover open={symbolOpen} onOpenChange={setSymbolOpen}>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={false}
                    disabled={!library || !symbols.length}
                    className="w-full justify-between"
                  >
                    {symbol || (library ? 'Select symbol' : 'Select library first')}
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="p-0 w-72" align="start">
                  <Command>
                    <CommandInput placeholder="Search symbols..." />
                    <CommandEmpty>No symbols found.</CommandEmpty>
                    <CommandList>
                      <CommandGroup>
                        {symbols.map((sym) => (
                          <CommandItem
                            key={sym}
                            value={sym}
                            onSelect={() => {
                              setSymbol(sym);
                              setSymbolOpen(false);
                            }}
                          >
                            <Check className={cn('mr-2 h-4 w-4', symbol === sym ? 'opacity-100' : 'opacity-0')} />
                            {sym}
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            </div>
            <div>
              <Label>Rows per page</Label>
              <Input className="w-24" type="number" min={1} max={10000} value={limit} onChange={(e) => setLimit(Math.max(1, Math.min(10000, Number(e.target.value) || 1)))} />
            </div>
            {/* Top controls: 4th column with paging + delete menu */}
            <div className="flex gap-2 items-end justify-end">
              <Button variant="outline" onClick={handleAddFilter} disabled={!hasFilterButton}>
                <FilterIcon className="mr-2 h-4 w-4" /> Filter
              </Button>
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

          {filters.length > 0 && (
            <div className="space-y-3 rounded-md border border-border bg-muted/20 p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Active filters</div>
              <div className="space-y-3">
                {filters.map((flt) => (
                  <div key={flt.id} className="grid gap-2 md:grid-cols-[minmax(0,180px)_minmax(0,160px)_1fr_auto] md:items-end">
                    <div className="flex flex-col gap-1">
                      <span className="text-xs font-medium text-muted-foreground">Column</span>
                      <Select value={flt.column} onValueChange={(value) => handleFilterChange(flt.id, { column: value })}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select column" />
                        </SelectTrigger>
                        <SelectContent>
                          {columnOptions.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="text-xs font-medium text-muted-foreground">Condition</span>
                      <Select value={flt.operator} onValueChange={(value: FilterOperator) => handleFilterChange(flt.id, { operator: value })}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {FILTER_OPERATOR_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="text-xs font-medium text-muted-foreground">Value</span>
                      <Input
                        value={flt.value}
                        onChange={(e) => handleFilterChange(flt.id, { value: e.target.value })}
                        placeholder="Enter value"
                      />
                    </div>
                    <div className="flex items-end justify-end">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="text-muted-foreground"
                        onClick={() => handleRemoveFilter(flt.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

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
          <div
            ref={tableContainerRef}
            tabIndex={0}
            className="overflow-x-auto border rounded-md focus:outline-none"
            onPointerDown={() => tableContainerRef.current?.focus({ preventScroll: true })}
          >
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  {columns.map((c, idx) => (
                    <th key={`${c}-${idx}`} className="text-left p-2 whitespace-nowrap">
                      <button
                        type="button"
                        className="flex items-center gap-1 font-semibold hover:underline"
                        onClick={() => handleHeaderSort(c, idx)}
                        disabled={!rows.length}
                      >
                        <span>{c}</span>
                        {renderSortIndicator(c, idx)}
                      </button>
                    </th>
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
