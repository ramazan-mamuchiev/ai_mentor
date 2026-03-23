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
} from '@tanstack/react-table'
import { listProducts, deleteProduct } from '../api/products'
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
  const [debugExpandedIds, setDebugExpandedIds] = useState<Set<number>>(new Set())
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

  const toggleDebug = useCallback((id: number) => {
    setDebugExpandedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

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
    },
    {
      id: 'status',
      accessorFn: row => getProductStatus(row),
      header: () => t('products.table.status'),
      cell: ({ row }) => <ProductStatusBadge product={row.original} />,
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
    state: { sorting, globalFilter },
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
