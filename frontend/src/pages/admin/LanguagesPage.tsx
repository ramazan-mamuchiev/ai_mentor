import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, Globe, Play } from 'lucide-react'
import type { ColumnDef } from '@tanstack/react-table'
import {
  adminListLanguages, adminCreateLanguage, adminDeleteLanguage,
  adminTriggerTranslate, adminGetTranslateProgress,
  type AdminLanguage,
} from '../../api/admin-i18n'
import { TenantFilterCombo } from '../../components/TenantFilterCombo'
import { DataTable } from '../../components/DataTable'
import { useDataTable } from '../../hooks/useDataTable'
import type { TenantSearchResult } from '../../api/admin'

const STORAGE_KEY = 'lexiro-admin-languages'
const DEFAULT_COLUMN_ORDER = ['code', 'name', 'default', 'active', 'system', 'keys', 'autoTranslate', 'modifiedBy', 'modifiedAt', 'actions']

export function LanguagesPage() {
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
  const [loading, setLoading] = useState(true)
  const [newCode, setNewCode] = useState('')
  const [newName, setNewName] = useState('')
  const [tenantFilter, setTenantFilter] = useState<TenantSearchResult | null>(null)
  const [translating, setTranslating] = useState<Record<number, { total: number; done: number; status: string; errors: number }>>({})
  const pollTimers = useRef<Record<number, ReturnType<typeof setInterval>>>({})

  const loadLanguages = useCallback(async () => {
    setLoading(true)
    try {
      setLanguages(await adminListLanguages(tenantFilter?.id))
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [tenantFilter])

  useEffect(() => {
    loadLanguages()
    return () => {
      Object.values(pollTimers.current).forEach(clearInterval)
    }
  }, [loadLanguages])

  const handleCreate = async () => {
    if (!newCode.trim() || !newName.trim()) return
    try {
      await adminCreateLanguage({ code: newCode.trim(), name_native: newName.trim() })
      setNewCode('')
      setNewName('')
      await loadLanguages()
    } catch (e) {
      console.error(e)
    }
  }

  const handleDelete = async (id: number, isSystem: boolean) => {
    if (isSystem) return
    if (!confirm(t('admin.languages.confirmDelete'))) return
    try {
      await adminDeleteLanguage(id)
      await loadLanguages()
    } catch (e) {
      console.error(e)
    }
  }

  const handleTranslate = async (id: number) => {
    try {
      await adminTriggerTranslate(id)
      setTranslating(prev => ({ ...prev, [id]: { total: 0, done: 0, status: 'running', errors: 0 } }))
      startPolling(id)
    } catch (e) {
      console.error(e)
    }
  }

  const startPolling = (id: number) => {
    if (pollTimers.current[id]) clearInterval(pollTimers.current[id])
    pollTimers.current[id] = setInterval(async () => {
      try {
        const progress = await adminGetTranslateProgress(id)
        setTranslating(prev => ({ ...prev, [id]: progress }))
        if (progress.status === 'complete' || progress.status === 'partial' || progress.status === 'timeout' || progress.status === 'idle') {
          clearInterval(pollTimers.current[id])
          delete pollTimers.current[id]
          await loadLanguages()
        }
      } catch {
        clearInterval(pollTimers.current[id])
        delete pollTimers.current[id]
      }
    }, 3000)
  }

  const defaultLangId = languages.find(l => l.is_default)?.id

  const columns = useMemo<ColumnDef<AdminLanguage, unknown>[]>(() => [
    {
      id: 'code',
      accessorKey: 'code',
      header: () => t('admin.languages.colCode'),
      cell: ({ getValue }) => <code>{String(getValue())}</code>,
      enableGrouping: false,
    },
    {
      id: 'name',
      accessorKey: 'name_native',
      header: () => t('admin.languages.colName'),
      enableGrouping: false,
    },
    {
      id: 'default',
      accessorKey: 'is_default',
      header: () => t('admin.languages.colDefault'),
      cell: ({ getValue }) => getValue() ? '✓' : '',
      enableGrouping: false,
    },
    {
      id: 'active',
      accessorKey: 'is_active',
      header: () => t('admin.languages.colActive'),
      cell: ({ getValue }) => getValue() ? '✓' : '—',
      enableGrouping: false,
    },
    {
      id: 'system',
      accessorKey: 'is_system',
      header: () => t('admin.languages.colSystem'),
      cell: ({ getValue }) => getValue() ? '✓' : '',
      enableGrouping: true,
    },
    {
      id: 'keys',
      accessorKey: 'total_keys',
      header: () => t('admin.languages.colKeys'),
      cell: ({ getValue }) => <span className="docs-chunks">{Number(getValue())}</span>,
      enableGrouping: false,
    },
    {
      id: 'autoTranslate',
      header: () => t('admin.languages.colAutoTranslate'),
      enableSorting: false,
      enableGrouping: false,
      cell: ({ row }) => {
        const lang = row.original
        const progress = translating[lang.id]
        const isTranslating = progress && progress.status === 'running'
        const isSourceLang = lang.id === defaultLangId
        return (
          <>
            {isTranslating ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ flex: 1, height: 6, background: 'var(--bg-tertiary)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    width: `${progress.total > 0 ? (progress.done / progress.total) * 100 : 0}%`,
                    height: '100%',
                    background: 'var(--accent)',
                    borderRadius: 3,
                    transition: 'width 0.3s',
                  }} />
                </div>
                <span style={{ fontSize: 12 }}>{progress.done}/{progress.total}</span>
              </div>
            ) : isSourceLang ? (
              <span style={{ fontSize: 12, opacity: 0.4 }}>—</span>
            ) : (
              <button onClick={() => handleTranslate(lang.id)} className="docs-action-btn">
                <Play size={14} />
              </button>
            )}
            {progress && progress.status === 'complete' && <span style={{ fontSize: 12, color: 'var(--success)' }}> {t('admin.languages.translateDone')}</span>}
            {progress && progress.status === 'partial' && <span style={{ fontSize: 12, color: 'var(--warning)' }}> {t('admin.languages.translatePartial', { errors: progress.errors })}</span>}
          </>
        )
      },
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
      header: () => t('admin.common.actions'),
      enableSorting: false,
      enableGrouping: false,
      cell: ({ row }) => {
        const lang = row.original
        if (lang.is_system) return null
        return (
          <div className="docs-actions">
            <button
              className="docs-action-btn"
              onClick={() => handleDelete(lang.id, lang.is_system)}
            >
              <Trash2 size={14} />
            </button>
          </div>
        )
      },
    },
  ], [t, translating, defaultLangId, relativeTime])

  const {
    table,
    columnOrder,
    grouping,
    handleColumnOrderChange,
    removeGrouping,
    toggleGrouping,
    resetSettings,
  } = useDataTable({
    data: languages,
    columns,
    storageKey: STORAGE_KEY,
    defaultColumnOrder: DEFAULT_COLUMN_ORDER,
    defaultSorting: [{ id: 'code', desc: false }],
    getRowId: row => String(row.id),
  })

  return (
    <div className="logs-page">
      <div className="admin-page-header">
        <h1><Globe size={20} /> {t('admin.nav.languages')}</h1>
      </div>

      <div className="logs-toolbar">
        <div className="logs-toolbar__row">
          <input
            placeholder={t('admin.languages.codePlaceholder')}
            value={newCode}
            onChange={e => setNewCode(e.target.value)}
            className="logs-search"
            style={{ width: 130, minWidth: 100 }}
          />
          <input
            placeholder={t('admin.languages.namePlaceholder')}
            value={newName}
            onChange={e => setNewName(e.target.value)}
            className="logs-search"
            style={{ width: 220, minWidth: 160 }}
          />
          <button
            onClick={handleCreate}
            className="admin-btn admin-btn--primary"
            disabled={!newCode.trim() || !newName.trim()}
          >
            <Plus size={14} />
            {t('admin.common.create')}
          </button>

          <TenantFilterCombo value={tenantFilter} onChange={setTenantFilter} />

          <span className="logs-count">{languages.length} {t('admin.languages.count')}</span>
        </div>
      </div>

      {loading && <div className="admin-loading">{t('admin.common.loading')}</div>}

      {!loading && languages.length === 0 && (
        <div className="admin-empty">{t('admin.languages.empty')}</div>
      )}

      {!loading && languages.length > 0 && (
        <DataTable
          table={table}
          columnOrder={columnOrder}
          grouping={grouping}
          onColumnOrderChange={handleColumnOrderChange}
          removeGrouping={removeGrouping}
          toggleGrouping={toggleGrouping}
          resetSettings={resetSettings}
        />
      )}
    </div>
  )
}
