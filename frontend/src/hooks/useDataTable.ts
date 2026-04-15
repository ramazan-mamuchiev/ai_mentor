import { useCallback, useMemo, useRef, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getGroupedRowModel,
  getExpandedRowModel,
  type ColumnDef,
  type SortingState,
  type ColumnOrderState,
  type ColumnFiltersState,
  type GroupingState,
  type ExpandedState,
  type VisibilityState,
  type RowData,
  type FilterFn,
} from '@tanstack/react-table'

export interface TableSettings {
  sorting?: SortingState
  grouping?: GroupingState
  columnOrder?: ColumnOrderState
  columnVisibility?: VisibilityState
}

function loadSettings(key: string): TableSettings {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function saveSettings(key: string, settings: TableSettings) {
  try {
    localStorage.setItem(key, JSON.stringify(settings))
  } catch { /* quota exceeded */ }
}

export interface UseDataTableOptions<TData extends RowData> {
  data: TData[]
  columns: ColumnDef<TData, unknown>[]
  storageKey: string
  defaultColumnOrder: string[]
  defaultSorting?: SortingState
  defaultGrouping?: GroupingState
  getRowId: (row: TData) => string
  columnFilters?: ColumnFiltersState
  globalFilter?: string
  onGlobalFilterChange?: (value: string) => void
  globalFilterFn?: FilterFn<TData>
}

export function useDataTable<TData extends RowData>({
  data,
  columns,
  storageKey,
  defaultColumnOrder,
  getRowId,
  columnFilters = [],
  globalFilter = '',
  onGlobalFilterChange,
  globalFilterFn,
  defaultSorting = [],
  defaultGrouping = [],
}: UseDataTableOptions<TData>) {
  const saved = useMemo(() => loadSettings(storageKey), [storageKey])

  const [sorting, setSorting] = useState<SortingState>(saved.sorting ?? defaultSorting)
  const [grouping, setGrouping] = useState<GroupingState>('grouping' in saved ? saved.grouping! : defaultGrouping)
  const [expanded, setExpanded] = useState<ExpandedState>(true)
  const [columnOrder, setColumnOrder] = useState<ColumnOrderState>(saved.columnOrder ?? defaultColumnOrder)
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(saved.columnVisibility ?? {})

  const persistRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const persist = useCallback((partial: Partial<TableSettings>) => {
    if (persistRef.current) clearTimeout(persistRef.current)
    persistRef.current = setTimeout(() => {
      const current = loadSettings(storageKey)
      saveSettings(storageKey, { ...current, ...partial })
    }, 300)
  }, [storageKey])

  const handleSortingChange = useCallback((updater: SortingState | ((old: SortingState) => SortingState)) => {
    setSorting(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      persist({ sorting: next })
      return next
    })
  }, [persist])

  const handleGroupingChange = useCallback((updater: GroupingState | ((old: GroupingState) => GroupingState)) => {
    setGrouping(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      persist({ grouping: next })
      return next
    })
  }, [persist])

  const handleColumnOrderChange = useCallback((updater: ColumnOrderState | ((old: ColumnOrderState) => ColumnOrderState)) => {
    setColumnOrder(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      persist({ columnOrder: next })
      return next
    })
  }, [persist])

  const handleColumnVisibilityChange = useCallback((updater: VisibilityState | ((old: VisibilityState) => VisibilityState)) => {
    setColumnVisibility(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      persist({ columnVisibility: next })
      return next
    })
  }, [persist])

  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter, columnFilters, columnOrder, grouping, expanded, columnVisibility },
    onSortingChange: handleSortingChange,
    onGlobalFilterChange,
    onColumnOrderChange: handleColumnOrderChange,
    onGroupingChange: handleGroupingChange,
    onExpandedChange: setExpanded,
    onColumnVisibilityChange: handleColumnVisibilityChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getGroupedRowModel: getGroupedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    enableMultiSort: true,
    getRowId,
    ...(globalFilterFn ? { globalFilterFn } : {}),
  })

  const removeGrouping = useCallback((columnId: string) => {
    handleGroupingChange(prev => prev.filter(g => g !== columnId))
  }, [handleGroupingChange])

  const toggleGrouping = useCallback((columnId: string) => {
    handleGroupingChange(prev =>
      prev.includes(columnId)
        ? prev.filter(g => g !== columnId)
        : [...prev, columnId]
    )
  }, [handleGroupingChange])

  const resetSettings = useCallback(() => {
    setSorting(defaultSorting)
    setGrouping(defaultGrouping)
    setColumnOrder(defaultColumnOrder)
    setColumnVisibility({})
    setExpanded(true)
    localStorage.removeItem(storageKey)
  }, [defaultSorting, defaultGrouping, defaultColumnOrder, storageKey])

  return {
    table,
    sorting,
    grouping,
    expanded,
    columnOrder,
    columnVisibility,
    handleColumnOrderChange,
    removeGrouping,
    toggleGrouping,
    resetSettings,
  }
}
