import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  Box,
  Upload,
  Download,
  RefreshCw,
  Trash2,
  Clock,
  Loader2,
  CheckCircle,
  AlertCircle,
  Search,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  X,
  Bug,
  Pencil,
} from 'lucide-react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
} from '@tanstack/react-table'
import { listProducts, deleteProduct, reingestProduct } from '../api/products'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { ProductDebugPanel } from '../components/ProductDebugPanel'
import { ProductEditDialog } from '../components/ProductEditDialog'
import type { ProductListItem, DocumentStatusValue } from '../types'

const POLL_INTERVAL = 5000

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${sizes[i]}`
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const date = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  return `${date}\n${time}`
}

function getProductStatus(p: ProductListItem): DocumentStatusValue {
  if (p.error_documents > 0) return 'error'
  if (p.processing_documents > 0) return 'processing'
  if (p.pending_documents > 0) return 'pending'
  return 'ready'
}

function ProductStatusBadge({ product }: { product: ProductListItem }) {
  const { t } = useTranslation()
  const status = getProductStatus(product)

  const icons: Record<DocumentStatusValue, React.ReactNode> = {
    pending: <Clock size={14} />,
    processing: <Loader2 size={14} className="spin-icon" />,
    ready: <CheckCircle size={14} />,
    error: <AlertCircle size={14} />,
  }

  const pct = status === 'processing' || status === 'pending'
    ? Math.max(0, Math.min(100, product.progress_percent))
    : 0

  return (
    <div className="docs-status-wrap">
      <span className={`docs-status docs-status--${status}`}>
        {icons[status]}
        {t(`docs.status.${status}`)}
      </span>
      {(status === 'processing' || status === 'pending') && (
        <>
          <div className="docs-progress-bar">
            <div
              className={`docs-progress-fill docs-progress-fill--${status}`}
              style={pct > 0 ? { width: `${pct}%`, animation: 'none' } : undefined}
            />
          </div>
          {product.progress_detail && (
            <div className="docs-progress-info">
              {pct > 0 && <span className="docs-progress-pct">{pct}%</span>}
              <span className="docs-progress-stage">{product.progress_detail}</span>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function SortIcon({ direction }: { direction: false | 'asc' | 'desc' }) {
  if (direction === 'asc') return <ArrowUp size={14} className="docs-sort-icon docs-sort-icon--active" />
  if (direction === 'desc') return <ArrowDown size={14} className="docs-sort-icon docs-sort-icon--active" />
  return <ArrowUpDown size={14} className="docs-sort-icon" />
}

interface Props {
  onUploadClick?: () => void
}

export function ProductsPage({ onUploadClick }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [products, setProducts] = useState<ProductListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [globalFilter, setGlobalFilter] = useState('')
  const [sorting, setSorting] = useState<SortingState>([])
  const [deleteTarget, setDeleteTarget] = useState<ProductListItem | null>(null)
  const [editTarget, setEditTarget] = useState<ProductListItem | null>(null)
  const [reingestTarget, setReingestTarget] = useState<ProductListItem | null>(null)
  const [debugExpandedIds, setDebugExpandedIds] = useState<Set<number>>(new Set())
  const [formatFilter, setFormatFilter] = useState<Set<string>>(new Set())
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set())
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const fetchProducts = useCallback(async () => {
    try {
      const data = await listProducts()
      setProducts(data)
    } catch { /* keep previous */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchProducts() }, [fetchProducts])

  useEffect(() => {
    const hasPending = products.some(p => p.pending_documents > 0 || p.processing_documents > 0)
    if (hasPending) {
      pollRef.current = setInterval(fetchProducts, POLL_INTERVAL)
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [products, fetchProducts])

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return
    try {
      await deleteProduct(deleteTarget.id)
      setProducts(prev => prev.filter(p => p.id !== deleteTarget.id))
    } catch { /* ignore */ }
    finally { setDeleteTarget(null) }
  }, [deleteTarget])

  const handleReingestConfirm = useCallback(async () => {
    if (!reingestTarget) return
    try {
      await reingestProduct(reingestTarget.id)
      fetchProducts()
    } catch { /* ignore */ }
    finally { setReingestTarget(null) }
  }, [reingestTarget, fetchProducts])

  const toggleDebug = useCallback((id: number) => {
    setDebugExpandedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const formatCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const p of products) {
      for (const f of p.formats) {
        map.set(f.format, (map.get(f.format) ?? 0) + 1)
      }
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1])
  }, [products])

  const statusCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const p of products) {
      map.set(getProductStatus(p), (map.get(getProductStatus(p)) ?? 0) + 1)
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1])
  }, [products])

  const toggleFilter = useCallback((setter: React.Dispatch<React.SetStateAction<Set<string>>>, value: string) => {
    setter(prev => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }, [])

  const clearFilters = useCallback(() => {
    setFormatFilter(new Set())
    setStatusFilter(new Set())
  }, [])

  const hasActiveFilters = formatFilter.size > 0 || statusFilter.size > 0

  const columnFilters = useMemo<ColumnFiltersState>(() => {
    const filters: ColumnFiltersState = []
    if (formatFilter.size > 0) filters.push({ id: 'format', value: formatFilter })
    if (statusFilter.size > 0) filters.push({ id: 'status', value: statusFilter })
    return filters
  }, [formatFilter, statusFilter])

  const columns = useMemo<ColumnDef<ProductListItem, unknown>[]>(() => [
    {
      id: 'name',
      accessorFn: row => row.name,
      header: () => t('products.table.name'),
      cell: ({ row }) => (
        <div
          className="docs-name-cell"
          style={{ cursor: 'pointer' }}
          onClick={() => navigate(`/app/products/${row.original.id}`)}
        >
          <span className="docs-name">{row.original.name}</span>
          {row.original.manufacturer && (
            <span className="docs-filename">{row.original.manufacturer}</span>
          )}
        </div>
      ),
    },
    {
      id: 'documents',
      accessorKey: 'total_documents',
      header: () => t('products.table.documents'),
      cell: ({ getValue }) => <span className="docs-chunks">{Number(getValue()) || '—'}</span>,
    },
    {
      id: 'format',
      accessorFn: row => row.formats.map(f => f.format).join(', '),
      header: () => t('products.table.format'),
      cell: ({ row }) => (
        <div className="docs-format-badges">
          {row.original.formats.map(f => (
            <span key={f.format} className="docs-format-badge">
              {f.format.toUpperCase()} {f.count > 1 && <span className="docs-format-count">{f.count}</span>}
            </span>
          ))}
        </div>
      ),
      filterFn: (row, _columnId, filterValue: Set<string>) =>
        filterValue.size === 0 || row.original.formats.some(f => filterValue.has(f.format)),
    },
    {
      id: 'status',
      accessorFn: row => getProductStatus(row),
      header: () => t('products.table.status'),
      cell: ({ row }) => <ProductStatusBadge product={row.original} />,
      filterFn: (row, _columnId, filterValue: Set<string>) =>
        filterValue.size === 0 || filterValue.has(getProductStatus(row.original)),
    },
    {
      id: 'size',
      accessorKey: 'total_file_size_bytes',
      header: () => t('products.table.size'),
      cell: ({ getValue }) => <span className="docs-size">{formatBytes(Number(getValue()))}</span>,
      sortingFn: 'basic',
    },
    {
      id: 'chunks',
      accessorKey: 'total_chunks',
      header: () => t('products.table.chunks'),
      cell: ({ getValue }) => <span className="docs-chunks">{Number(getValue()) || '—'}</span>,
    },
    {
      id: 'uploaded',
      accessorFn: row => row.uploaded_at,
      header: () => t('products.table.uploaded'),
      cell: ({ getValue }) => <span className="docs-date docs-date--twoline">{formatDateTime(getValue() as string | null)}</span>,
      sortingFn: 'datetime',
    },
    {
      id: 'indexed',
      accessorFn: row => row.indexed_at,
      header: () => t('products.table.indexed'),
      cell: ({ getValue }) => <span className="docs-date docs-date--twoline">{formatDateTime(getValue() as string | null)}</span>,
      sortingFn: 'datetime',
    },
    {
      id: 'actions',
      header: () => t('products.table.actions'),
      enableSorting: false,
      cell: ({ row }) => {
        const p = row.original
        const isDebugOpen = debugExpandedIds.has(p.id)
        return (
          <div className="docs-actions">
            <button
              className={`docs-action-btn docs-debug-toggle${isDebugOpen ? ' docs-debug-toggle--active' : ''}`}
              onClick={() => toggleDebug(p.id)}
              title={t('products.actions.debug')}
            >
              <Bug size={16} />
            </button>
            <button
              className="docs-action-btn"
              onClick={() => setReingestTarget(p)}
              title={t('products.actions.reindex')}
            >
              <RefreshCw size={16} />
            </button>
            <button
              className="docs-action-btn"
              onClick={() => setEditTarget(p)}
              title={t('products.actions.edit')}
            >
              <Pencil size={16} />
            </button>
            <button
              className="docs-action-btn docs-action-btn--danger"
              onClick={() => setDeleteTarget(p)}
              title={t('products.actions.delete')}
            >
              <Trash2 size={16} />
            </button>
          </div>
        )
      },
    },
  ], [t, navigate, debugExpandedIds, toggleDebug])

  const table = useReactTable({
    data: products,
    columns,
    state: { sorting, globalFilter, columnFilters },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getRowId: row => String(row.id),
  })

  if (loading) {
    return (
      <div className="docs-page">
        <div className="docs-empty">
          <Loader2 size={32} className="spin-icon docs-empty-icon" />
        </div>
      </div>
    )
  }

  if (products.length === 0) {
    return (
      <div className="docs-page">
        <div className="docs-empty">
          <Box size={48} className="docs-empty-icon" />
          <h2>{t('products.empty.title')}</h2>
          <p>{t('products.empty.description')}</p>
          {onUploadClick && (
            <button className="docs-upload-btn" onClick={onUploadClick}>
              <Upload size={16} />
              <span>{t('products.empty.cta')}</span>
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="docs-page">
      <div className="docs-header">
        <h1 className="docs-page-title">
          <Box size={20} />
          {t('products.title')}
        </h1>
        <div className="docs-header-actions">
          <div className="docs-search">
            <Search size={16} />
            <input
              ref={searchRef}
              type="text"
              value={globalFilter}
              onChange={e => setGlobalFilter(e.target.value)}
              placeholder={t('products.search.placeholder')}
              className="docs-search-input"
            />
            {globalFilter && (
              <button className="docs-search-clear" onClick={() => { setGlobalFilter(''); searchRef.current?.focus() }}>
                <X size={14} />
              </button>
            )}
          </div>
          {onUploadClick && (
            <button className="docs-upload-btn" onClick={onUploadClick}>
              <Upload size={16} />
              <span>{t('docs.upload')}</span>
            </button>
          )}
        </div>
      </div>

      {(formatCounts.length > 1 || statusCounts.length > 1) && (
        <div className="docs-filter-bar">
          {formatCounts.length > 1 && (
            <div className="docs-filter-group">
              <span className="docs-filter-label">{t('docs.filter.format')}:</span>
              <div className="docs-filter-chips">
                {formatCounts.map(([fmt, count]) => (
                  <button
                    key={fmt}
                    className={`docs-filter-chip${formatFilter.has(fmt) ? ' docs-filter-chip--active' : ''}`}
                    onClick={() => toggleFilter(setFormatFilter, fmt)}
                  >
                    {fmt.toUpperCase()}
                    <span className="docs-filter-chip-count">{count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {statusCounts.length > 1 && (
            <div className="docs-filter-group">
              <span className="docs-filter-label">{t('docs.filter.status')}:</span>
              <div className="docs-filter-chips">
                {statusCounts.map(([st, count]) => (
                  <button
                    key={st}
                    className={`docs-filter-chip docs-filter-chip--status-${st}${statusFilter.has(st) ? ' docs-filter-chip--active' : ''}`}
                    onClick={() => toggleFilter(setStatusFilter, st)}
                  >
                    {t(`docs.status.${st}`)}
                    <span className="docs-filter-chip-count">{count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {hasActiveFilters && (
            <button className="docs-filter-clear" onClick={clearFilters}>
              <X size={12} />
              {t('docs.filter.clear')}
            </button>
          )}
        </div>
      )}

      <div className="docs-table-wrap">
        <table className="docs-table">
          <thead>
            {table.getHeaderGroups().map(headerGroup => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map(header => (
                  <th key={header.id} className="docs-th">
                    <div className="docs-th-inner">
                      <span
                        className={header.column.getCanSort() ? 'docs-th-label docs-th-label--sortable' : 'docs-th-label'}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getCanSort() && <SortIcon direction={header.column.getIsSorted()} />}
                      </span>
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map(row => {
              const showDebug = debugExpandedIds.has(row.original.id)
              return (
                <Fragment key={row.id}>
                  <tr>
                    {row.getVisibleCells().map(cell => (
                      <td key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                  {showDebug && (
                    <tr className="docs-debug-expand-row">
                      <td colSpan={row.getVisibleCells().length}>
                        <ProductDebugPanel productId={row.original.id} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      {deleteTarget && (
        <ConfirmDialog
          title={t('products.delete.title')}
          message={t('products.delete.message')}
          details={`${deleteTarget.name} (${deleteTarget.total_documents} documents, ${formatBytes(deleteTarget.total_file_size_bytes)})`}
          confirmLabel={t('products.delete.confirm')}
          cancelLabel={t('products.delete.cancel')}
          variant="danger"
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {reingestTarget && (
        <ConfirmDialog
          title={t('products.reingest.title')}
          message={t('products.reingest.message')}
          details={`${reingestTarget.name} (${reingestTarget.total_documents} documents)`}
          confirmLabel={t('products.reingest.confirm')}
          cancelLabel={t('products.delete.cancel')}
          variant="default"
          onConfirm={handleReingestConfirm}
          onCancel={() => setReingestTarget(null)}
        />
      )}

      {editTarget && (
        <ProductEditDialog
          product={editTarget}
          onSave={() => { setEditTarget(null); fetchProducts() }}
          onCancel={() => setEditTarget(null)}
        />
      )}
    </div>
  )
}
