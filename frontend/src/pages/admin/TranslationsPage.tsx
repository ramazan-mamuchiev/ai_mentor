import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, Save, ChevronLeft, ChevronRight, Languages, X } from 'lucide-react'
import type { ColumnDef } from '@tanstack/react-table'
import {
  adminListLanguages, adminListTranslations, adminUpsertTranslation,
  type AdminLanguage, type TranslationItem,
} from '../../api/admin-i18n'
import { TenantFilterCombo } from '../../components/TenantFilterCombo'
import { DataTable } from '../../components/DataTable'
import { useDataTable } from '../../hooks/useDataTable'
import type { TenantSearchResult } from '../../api/admin'

const STORAGE_KEY = 'lexiro-admin-translations'
const DEFAULT_COLUMN_ORDER = ['key', 'value', 'modifiedBy', 'modifiedAt', 'actions']

export default function TranslationsPage() {
  const { t } = useTranslation()

  const relativeTime = useCallback((iso: string | null): string => {
    if (!iso) return ''
    const diff = Date.now() - new Date(iso).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return t('admin.common.justNow')
    if (mins < 60) return t('admin.common.minutesAgo', { count: mins })
    const hours = Math.floor(mins / 60)
    if (hours < 24) return t('admin.common.hoursAgo', { count: hours })
    const days = Math.floor(hours / 24)
    return t('admin.common.daysAgo', { count: days })
  }, [t])

  const [languages, setLanguages] = useState<AdminLanguage[]>([])
  const [selectedLangId, setSelectedLangId] = useState<number | null>(null)
  const [namespace, setNamespace] = useState('ui')
  const [items, setItems] = useState<TranslationItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')
  const [tenantFilter, setTenantFilter] = useState<TenantSearchResult | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    adminListLanguages().then(langs => {
      setLanguages(langs)
      if (langs.length > 0) setSelectedLangId(langs[0].id)
    })
  }, [])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 400)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [search])

  const loadTranslations = useCallback(async () => {
    if (!selectedLangId) return
    setLoading(true)
    try {
      const res = await adminListTranslations(selectedLangId, namespace, page, pageSize, debouncedSearch || undefined, tenantFilter?.id)
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [selectedLangId, namespace, page, pageSize, debouncedSearch, tenantFilter])

  useEffect(() => { loadTranslations() }, [loadTranslations])

  const handleSave = async (item: TranslationItem) => {
    if (!selectedLangId) return
    try {
      await adminUpsertTranslation(selectedLangId, { namespace, key: item.key, value: editValue })
      setEditingId(null)
      await loadTranslations()
    } catch (e) {
      console.error(e)
    }
  }

  const totalPages = Math.ceil(total / pageSize)

  const columns = useMemo<ColumnDef<TranslationItem, unknown>[]>(() => [
    {
      id: 'key',
      accessorKey: 'key',
      header: () => t('admin.translations.colKey'),
      cell: ({ getValue }) => <code style={{ fontSize: 12 }}>{String(getValue())}</code>,
      enableGrouping: false,
    },
    {
      id: 'value',
      accessorKey: 'value',
      header: () => t('admin.translations.colValue'),
      cell: ({ row }) => {
        const item = row.original
        if (editingId === item.id) {
          return (
            <input
              value={editValue}
              onChange={e => setEditValue(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleSave(item)
                if (e.key === 'Escape') setEditingId(null)
              }}
              onBlur={() => handleSave(item)}
              className="logs-search"
              style={{ width: '100%' }}
              autoFocus
            />
          )
        }
        return (
          <span
            className="translation-value-cell"
            onClick={() => { setEditingId(item.id); setEditValue(item.value) }}
          >
            {item.value || <em className="translation-value-cell__empty">empty</em>}
          </span>
        )
      },
      enableGrouping: false,
    },
    {
      id: 'modifiedBy',
      accessorFn: row => row.modified_by_name || row.modified_by_email || '',
      header: () => t('admin.common.modifiedBy'),
      cell: ({ getValue }) => <span className="audit-cell">{String(getValue())}</span>,
      enableGrouping: false,
    },
    {
      id: 'modifiedAt',
      accessorKey: 'modified_at',
      header: () => t('admin.common.modifiedAt'),
      cell: ({ getValue }) => <span className="audit-cell">{relativeTime(getValue() as string | null)}</span>,
      enableGrouping: false,
      sortingFn: 'datetime',
    },
    {
      id: 'actions',
      header: () => '',
      enableSorting: false,
      enableGrouping: false,
      cell: ({ row }) => {
        const item = row.original
        if (editingId !== item.id) return null
        return (
          <button onClick={() => handleSave(item)} className="docs-action-btn">
            <Save size={14} />
          </button>
        )
      },
    },
  ], [t, editingId, editValue, relativeTime])

  const {
    table,
    columnOrder,
    grouping,
    handleColumnOrderChange,
    removeGrouping,
    toggleGrouping,
    resetSettings,
  } = useDataTable({
    data: items,
    columns,
    storageKey: STORAGE_KEY,
    defaultColumnOrder: DEFAULT_COLUMN_ORDER,
    defaultSorting: [],
    getRowId: row => String(row.id),
  })

  return (
    <div className="logs-page">
      <div className="admin-page-header">
        <h1><Languages size={20} /> {t('admin.nav.translations')}</h1>
      </div>

      <div className="logs-toolbar">
        <div className="logs-toolbar__row">
          <select
            className="logs-select"
            value={selectedLangId ?? ''}
            onChange={e => { setSelectedLangId(Number(e.target.value)); setPage(1) }}
          >
            {languages.map(l => (
              <option key={l.id} value={l.id}>{l.code} — {l.name_native}</option>
            ))}
          </select>

          <div className="logs-chips" role="group" aria-label="Namespace">
            {(['ui', 'taxonomy'] as const).map(ns => (
              <button
                key={ns}
                className={`logs-chip${namespace === ns ? ' logs-chip--active' : ''}`}
                onClick={() => { setNamespace(ns); setPage(1) }}
              >
                {ns.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="logs-search-wrap">
            <Search size={14} className="logs-search-wrap__icon" />
            <input
              className="logs-search"
              placeholder={t('admin.translations.searchPlaceholder')}
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
            />
            {search && (
              <button className="logs-search-wrap__clear" onClick={() => setSearch('')}>
                <X size={14} />
              </button>
            )}
          </div>

          <TenantFilterCombo value={tenantFilter} onChange={setTenantFilter} />

          <span className="logs-count">{total} {t('admin.translations.keys')}</span>
        </div>
      </div>

      {loading && <div className="admin-loading">{t('admin.common.loading')}</div>}

      {!loading && items.length === 0 && (
        <div className="admin-empty">{t('admin.translations.empty')}</div>
      )}

      {!loading && items.length > 0 && (
        <>
          <DataTable
            table={table}
            columnOrder={columnOrder}
            grouping={grouping}
            onColumnOrderChange={handleColumnOrderChange}
            removeGrouping={removeGrouping}
            toggleGrouping={toggleGrouping}
            resetSettings={resetSettings}
          />

          {totalPages > 1 && (
            <div className="logs-toolbar__row" style={{ justifyContent: 'center', marginTop: 12, gap: 8 }}>
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="docs-action-btn">
                <ChevronLeft size={16} />
              </button>
              <span className="logs-count">{page} / {totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="docs-action-btn">
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
