import { useEffect, useState, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, Save, ChevronLeft, ChevronRight, Languages, X } from 'lucide-react'
import {
  adminListLanguages, adminListTranslations, adminUpsertTranslation,
  type AdminLanguage, type TranslationItem,
} from '../../api/admin-i18n'

export default function TranslationsPage() {
  const { t } = useTranslation()
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
      const res = await adminListTranslations(selectedLangId, namespace, page, pageSize, debouncedSearch || undefined)
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [selectedLangId, namespace, page, pageSize, debouncedSearch])

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

  return (
    <div className="logs-page">
      <div className="admin-page-header">
        <h1><Languages size={20} /> {t('admin.nav.translations')}</h1>
      </div>

      {/* Toolbar — logs-style */}
      <div className="logs-toolbar">
        <div className="logs-toolbar__row">
          {/* Language select */}
          <select
            className="logs-select"
            value={selectedLangId ?? ''}
            onChange={e => { setSelectedLangId(Number(e.target.value)); setPage(1) }}
          >
            {languages.map(l => (
              <option key={l.id} value={l.id}>{l.code} — {l.name_native}</option>
            ))}
          </select>

          {/* Namespace chips */}
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

          {/* Search */}
          <div className="logs-search-wrap">
            <Search size={14} className="logs-search-wrap__icon" />
            <input
              className="logs-search"
              placeholder={t('admin.logs.searchPlaceholder', { defaultValue: 'Search keys or values...' })}
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
            />
            {search && (
              <button className="logs-search-wrap__clear" onClick={() => setSearch('')}>
                <X size={14} />
              </button>
            )}
          </div>

          {/* Count */}
          <span className="logs-count">{total} {t('admin.translations.keys', { defaultValue: 'keys' })}</span>
        </div>
      </div>

      {loading && <div className="admin-loading">{t('admin.common.loading')}</div>}

      {!loading && items.length === 0 && (
        <div className="admin-empty">{t('admin.translations.empty', { defaultValue: 'No translations found' })}</div>
      )}

      {!loading && items.length > 0 && (
        <>
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: '35%' }}>Key</th>
                <th>Value</th>
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr key={item.id}>
                  <td><code style={{ fontSize: 12 }}>{item.key}</code></td>
                  <td>
                    {editingId === item.id ? (
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
                    ) : (
                      <span
                        onClick={() => { setEditingId(item.id); setEditValue(item.value) }}
                        style={{ cursor: 'pointer' }}
                        title={t('admin.translations.clickToEdit', { defaultValue: 'Click to edit' })}
                      >
                        {item.value || <em style={{ opacity: 0.4 }}>—</em>}
                      </span>
                    )}
                  </td>
                  <td>
                    {editingId === item.id && (
                      <button onClick={() => handleSave(item)} className="logs-icon-btn" title={t('admin.common.save')}>
                        <Save size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination — logs style */}
          {totalPages > 1 && (
            <div className="logs-toolbar__row" style={{ justifyContent: 'center', marginTop: 12, gap: 8 }}>
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="logs-icon-btn">
                <ChevronLeft size={16} />
              </button>
              <span className="logs-count">{page} / {totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="logs-icon-btn">
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
