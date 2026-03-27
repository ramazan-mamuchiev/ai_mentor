import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  Box,
  Upload,
  Globe,
  Loader2,
  CheckCircle,
  Search,
  X,
  Bug,
  RefreshCw,
  Pencil,
  Trash2,
  MoreHorizontal,
} from 'lucide-react'
import type { ColumnDef, ColumnFiltersState } from '@tanstack/react-table'
import { listProducts, deleteProduct, reingestProduct, cancelProductIngestion } from '../api/products'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { DocsRightPanel } from '../components/DocsRightPanel'
import { ProductEditDialog } from '../components/ProductEditDialog'
import { DataTable } from '../components/DataTable'
import { useDataTable } from '../hooks/useDataTable'
import type { ProductListItem, DocumentStatusValue } from '../types'

const POLL_INTERVAL = 2000
const STORAGE_KEY = 'lexiro-products-table'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${sizes[i]}`
}

function formatDateCompact(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function formatDateTimeFull(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function getProductStatus(p: ProductListItem): DocumentStatusValue {
  if (p.processing_documents > 0) return 'processing'
  if (p.pending_documents > 0) return 'pending'
  if (p.error_documents > 0) return 'error'
  if (p.cancelled_documents > 0 && p.ready_documents === 0) return 'cancelled'
  return 'ready'
}

function ProductStatusBadge({ product, onCancel }: { product: ProductListItem; onCancel?: () => void }) {
  const { t } = useTranslation()
  const status = getProductStatus(product)
  const total = product.total_documents

  const allReady = total > 0 && product.ready_documents === total

  if (allReady) {
    return (
      <span className="docs-status docs-status--ready">
        <CheckCircle size={14} />
        {t('docs.status.ready')}
      </span>
    )
  }

  if (total === 0) {
    return <span className="docs-date">—</span>
  }

  const segments = ([
    { key: 'ready' as DocumentStatusValue, count: product.ready_documents },
    { key: 'processing' as DocumentStatusValue, count: product.processing_documents },
    { key: 'pending' as DocumentStatusValue, count: product.pending_documents },
    { key: 'error' as DocumentStatusValue, count: product.error_documents },
    { key: 'cancelled' as DocumentStatusValue, count: product.cancelled_documents },
  ]).filter(s => s.count > 0)

  const tooltipParts = segments.map(s => `${s.count} ${t(`docs.status.${s.key}`).toLowerCase()}`)
  const tooltip = tooltipParts.join(', ')

  const pct = (status === 'processing' || status === 'pending')
    ? Math.max(0, Math.min(100, product.progress_percent))
    : Math.round((product.ready_documents / total) * 100)

  const canCancel = onCancel && (status === 'processing' || status === 'pending')

  return (
    <div className="product-segmented-wrap" data-tooltip={tooltip}>
      <div className="product-segmented-bar">
        {segments.map(s => (
          <div
            key={s.key}
            className={`product-segmented-segment product-segmented-segment--${s.key}`}
            style={{ width: `${(s.count / total) * 100}%` }}
          />
        ))}
      </div>
      <div className="product-segmented-text">
        {(status === 'processing' || status === 'pending') && (
          <span className="product-segmented-pct">{pct}%</span>
        )}
        <span className="product-segmented-fraction">
          {product.ready_documents} / {total}
        </span>
        {product.error_documents > 0 && (
          <span className="product-segmented-error-hint">
            ({product.error_documents} {t('docs.status.error').toLowerCase()})
          </span>
        )}
        {canCancel && (
          <button
            className="docs-status-cancel"
            onClick={e => { e.stopPropagation(); onCancel() }}
            data-tooltip={t('products.actions.cancelIngestion')}
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  )
}

function ProductActions({
  product: p,
  onEdit,
  onDelete,
  onReingest,
  onDebug,
}: {
  product: ProductListItem
  onEdit: (p: ProductListItem) => void
  onDelete: (p: ProductListItem) => void
  onReingest: (p: ProductListItem) => void
  onDebug: (p: ProductListItem) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div className="docs-actions">
      <button
        className="docs-action-btn"
        onClick={() => onEdit(p)}
        data-tooltip={t('products.actions.edit')}
      >
        <Pencil size={16} />
      </button>
      <div className="docs-actions-more" ref={ref}>
        <button
          className="docs-action-btn"
          onClick={() => setOpen(v => !v)}
          data-tooltip={t('products.table.actions')}
        >
          <MoreHorizontal size={16} />
        </button>
        {open && (
          <div className="docs-actions-dropdown">
            <button className="docs-actions-dropdown-item" onClick={() => { onDebug(p); setOpen(false) }}>
              <Bug size={15} />
              {t('products.actions.debug')}
            </button>
            <button className="docs-actions-dropdown-item" onClick={() => { onReingest(p); setOpen(false) }}>
              <RefreshCw size={15} />
              {t('products.actions.reindex')}
            </button>
            <button className="docs-actions-dropdown-item docs-actions-dropdown-item--danger" onClick={() => { onDelete(p); setOpen(false) }}>
              <Trash2 size={15} />
              {t('products.actions.delete')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

interface Props {
  onUploadClick?: () => void
  onUrlImportClick?: () => void
  refreshKey?: number
}

const DEFAULT_COLUMN_ORDER = ['name', 'documents', 'format', 'status', 'size', 'chunks', 'uploaded', 'indexed', 'actions']

export function ProductsPage({ onUploadClick, onUrlImportClick, refreshKey }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [products, setProducts] = useState<ProductListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [globalFilter, setGlobalFilter] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<ProductListItem | null>(null)
  const [editTarget, setEditTarget] = useState<ProductListItem | null>(null)
  const [reingestTarget, setReingestTarget] = useState<ProductListItem | null>(null)
  const [cancelTarget, setCancelTarget] = useState<ProductListItem | null>(null)
  const [debugPanel, setDebugPanel] = useState<ProductListItem | null>(null)
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
    if (refreshKey) fetchProducts()
  }, [refreshKey, fetchProducts])

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
      await deleteProduct(deleteTarget.manufacturer_slug, deleteTarget.slug)
      setProducts(prev => prev.filter(p =>
        !(p.manufacturer_slug === deleteTarget.manufacturer_slug && p.slug === deleteTarget.slug)
      ))
    } catch { /* ignore */ }
    finally { setDeleteTarget(null) }
  }, [deleteTarget])

  const handleReingestConfirm = useCallback(async () => {
    if (!reingestTarget) return
    try {
      await reingestProduct(reingestTarget.manufacturer_slug, reingestTarget.slug)
      fetchProducts()
    } catch { /* ignore */ }
    finally { setReingestTarget(null) }
  }, [reingestTarget, fetchProducts])

  const handleCancelConfirm = useCallback(async () => {
    if (!cancelTarget) return
    try {
      await cancelProductIngestion(cancelTarget.manufacturer_slug, cancelTarget.slug)
      fetchProducts()
    } catch { /* ignore */ }
    finally { setCancelTarget(null) }
  }, [cancelTarget, fetchProducts])

  const openDebug = useCallback((product: ProductListItem) => {
    setDebugPanel(product)
  }, [])

  const closeDebug = useCallback(() => {
    setDebugPanel(null)
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
      accessorFn: row => row.display_name || row.name,
      header: () => t('products.table.name'),
      cell: ({ row }) => (
        <div
          className="docs-name-cell"
          style={{ cursor: 'pointer' }}
          onClick={() => navigate(`/app/products/${row.original.manufacturer_slug}/${row.original.slug}`)}
        >
          <span className="docs-name">{row.original.display_name || row.original.name}</span>
          {row.original.manufacturer && (
            <span className="docs-filename">{row.original.manufacturer}</span>
          )}
        </div>
      ),
      enableGrouping: true,
    },
    {
      id: 'documents',
      accessorKey: 'total_documents',
      header: () => t('products.table.documents'),
      cell: ({ getValue }) => <span className="docs-chunks">{Number(getValue()) || '—'}</span>,
      enableGrouping: false,
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
      enableGrouping: true,
      filterFn: (row, _columnId, filterValue: Set<string>) =>
        filterValue.size === 0 || row.original.formats.some(f => filterValue.has(f.format)),
    },
    {
      id: 'status',
      accessorFn: row => getProductStatus(row),
      header: () => t('products.table.status'),
      cell: ({ row }) => <ProductStatusBadge product={row.original} onCancel={() => setCancelTarget(row.original)} />,
      enableGrouping: true,
      filterFn: (row, _columnId, filterValue: Set<string>) =>
        filterValue.size === 0 || filterValue.has(getProductStatus(row.original)),
    },
    {
      id: 'size',
      accessorKey: 'total_file_size_bytes',
      header: () => t('products.table.size'),
      cell: ({ getValue }) => <span className="docs-size">{formatBytes(Number(getValue()))}</span>,
      enableGrouping: false,
      sortingFn: 'basic',
    },
    {
      id: 'chunks',
      accessorKey: 'total_chunks',
      header: () => t('products.table.chunks'),
      cell: ({ getValue }) => <span className="docs-chunks">{Number(getValue()) || '—'}</span>,
      enableGrouping: false,
    },
    {
      id: 'uploaded',
      accessorFn: row => row.uploaded_at,
      header: () => t('products.table.uploaded'),
      cell: ({ getValue }) => {
        const v = getValue() as string | null
        return <span className="docs-date" data-tooltip={formatDateTimeFull(v)}>{formatDateCompact(v)}</span>
      },
      enableGrouping: false,
      sortingFn: 'datetime',
    },
    {
      id: 'indexed',
      accessorFn: row => row.indexed_at,
      header: () => t('products.table.indexed'),
      cell: ({ getValue }) => {
        const v = getValue() as string | null
        return <span className="docs-date" data-tooltip={formatDateTimeFull(v)}>{formatDateCompact(v)}</span>
      },
      enableGrouping: false,
      sortingFn: 'datetime',
    },
    {
      id: 'actions',
      header: () => t('products.table.actions'),
      enableSorting: false,
      enableGrouping: false,
      cell: ({ row }) => {
        const p = row.original
        return <ProductActions product={p} onEdit={setEditTarget} onDelete={setDeleteTarget} onReingest={setReingestTarget} onDebug={openDebug} />
      },
    },
  ], [t, navigate, openDebug])

  const {
    table,
    columnOrder,
    grouping,
    handleColumnOrderChange,
    removeGrouping,
    toggleGrouping,
    resetSettings,
  } = useDataTable({
    data: products,
    columns,
    storageKey: STORAGE_KEY,
    defaultColumnOrder: DEFAULT_COLUMN_ORDER,
    getRowId: row => row.firmware_version_id ? `${row.id}-${row.firmware_version_id}` : String(row.id),
    columnFilters,
    globalFilter,
    onGlobalFilterChange: setGlobalFilter,
  })

  const handleResetAll = useCallback(() => {
    resetSettings()
    setGlobalFilter('')
    setFormatFilter(new Set())
    setStatusFilter(new Set())
  }, [resetSettings])

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
          <div className="docs-empty-actions">
            {onUploadClick && (
              <button className="docs-upload-btn" onClick={onUploadClick}>
                <Upload size={16} />
                <span>{t('products.empty.cta')}</span>
              </button>
            )}
            {onUrlImportClick && (
              <button className="docs-upload-btn docs-upload-btn--secondary" onClick={onUrlImportClick}>
                <Globe size={16} />
                <span>{t('urlImport.button')}</span>
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={`docs-page${debugPanel ? ' docs-page--with-panel' : ''}`}>
      <div className="docs-page-main">
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
              <button className="docs-search-clear" onClick={() => { setGlobalFilter(''); searchRef.current?.focus() }} data-tooltip={t('products.search.clear')}>
                <X size={14} />
              </button>
            )}
          </div>
          {onUrlImportClick && (
            <button className="docs-upload-btn docs-upload-btn--secondary" onClick={onUrlImportClick}>
              <Globe size={16} />
              <span>{t('urlImport.button')}</span>
            </button>
          )}
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
              <X size={14} />
              {t('docs.filter.clear')}
            </button>
          )}
        </div>
      )}

      <DataTable
        table={table}
        columnOrder={columnOrder}
        grouping={grouping}
        onColumnOrderChange={handleColumnOrderChange}
        removeGrouping={removeGrouping}
        toggleGrouping={toggleGrouping}
        resetSettings={handleResetAll}
      />

      {/* Mobile: Cards */}
      <div className="docs-cards">
        {products
          .filter(p => {
            if (formatFilter.size > 0 && !p.formats.some(f => formatFilter.has(f.format))) return false
            if (statusFilter.size > 0 && !statusFilter.has(getProductStatus(p))) return false
            if (!globalFilter) return true
            const q = globalFilter.toLowerCase()
            return (
              p.name.toLowerCase().includes(q) ||
              (p.display_name || '').toLowerCase().includes(q) ||
              p.manufacturer.toLowerCase().includes(q) ||
              p.version.toLowerCase().includes(q)
            )
          })
          .map(p => (
            <div
              className="docs-card"
              key={p.firmware_version_id ? `${p.id}-${p.firmware_version_id}` : p.id}
              onClick={() => navigate(`/app/products/${p.manufacturer_slug}/${p.slug}`)}
              style={{ cursor: 'pointer' }}
            >
              <div className="docs-card-header">
                <div className="docs-card-title">
                  {p.display_name || p.name}
                  {p.manufacturer && <div className="docs-filename">{p.manufacturer}</div>}
                </div>
                <ProductStatusBadge product={p} onCancel={() => setCancelTarget(p)} />
              </div>
              <div className="docs-card-meta">
                <span>{t('products.table.documents')}: {p.total_documents}</span>
                <span>{formatBytes(p.total_file_size_bytes)}</span>
                {p.total_chunks > 0 && <span>{t('products.table.chunks')}: {p.total_chunks}</span>}
                {p.uploaded_at && <span>{formatDateCompact(p.uploaded_at)}</span>}
              </div>
              {p.formats.length > 0 && (
                <div className="docs-card-meta" style={{ marginTop: 4 }}>
                  {p.formats.map(f => (
                    <span key={f.format} className="docs-format-badge">
                      {f.format.toUpperCase()} {f.count > 1 && <span className="docs-format-count">{f.count}</span>}
                    </span>
                  ))}
                </div>
              )}
              <div className="docs-card-actions" onClick={e => e.stopPropagation()}>
                <button className="docs-action-btn" onClick={() => setEditTarget(p)} data-tooltip={t('products.actions.edit')}>
                  <Pencil size={16} />
                </button>
                <button className="docs-action-btn" onClick={() => openDebug(p)} data-tooltip={t('products.actions.debug')}>
                  <Bug size={16} />
                </button>
                <button className="docs-action-btn" onClick={() => setReingestTarget(p)} data-tooltip={t('products.actions.reindex')}>
                  <RefreshCw size={16} />
                </button>
                <button className="docs-action-btn docs-action-btn--danger" onClick={() => setDeleteTarget(p)} data-tooltip={t('products.actions.delete')}>
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))
        }
      </div>
      </div>

      {debugPanel && (
        <DocsRightPanel
          mode="product"
          manufacturerSlug={debugPanel.manufacturer_slug}
          productSlug={debugPanel.slug}
          productName={debugPanel.name}
          onClose={closeDebug}
        />
      )}

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

      {cancelTarget && (
        <ConfirmDialog
          title={t('products.cancelIngestion.title')}
          message={t('products.cancelIngestion.message')}
          details={`${cancelTarget.name} (${cancelTarget.pending_documents + cancelTarget.processing_documents} ${t('products.cancelIngestion.documentsLabel')})`}
          confirmLabel={t('products.cancelIngestion.confirm')}
          cancelLabel={t('products.delete.cancel')}
          variant="danger"
          onConfirm={handleCancelConfirm}
          onCancel={() => setCancelTarget(null)}
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
