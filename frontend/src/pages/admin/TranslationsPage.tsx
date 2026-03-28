import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Search, Save, ChevronLeft, ChevronRight } from 'lucide-react'
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
  const [loading, setLoading] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')

  useEffect(() => {
    adminListLanguages().then(langs => {
      setLanguages(langs)
      if (langs.length > 0) setSelectedLangId(langs[0].id)
    })
  }, [])

  const loadTranslations = useCallback(async () => {
    if (!selectedLangId) return
    setLoading(true)
    try {
      const res = await adminListTranslations(selectedLangId, namespace, page, pageSize, search || undefined)
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [selectedLangId, namespace, page, pageSize, search])

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
    <div className="admin-page">
      <div className="admin-page-header">
        <h1>{t('admin.nav.translations')}</h1>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <select
          value={selectedLangId ?? ''}
          onChange={e => { setSelectedLangId(Number(e.target.value)); setPage(1) }}
          className="admin-select"
        >
          {languages.map(l => (
            <option key={l.id} value={l.id}>{l.code} — {l.name_native}</option>
          ))}
        </select>

        <select value={namespace} onChange={e => { setNamespace(e.target.value); setPage(1) }} className="admin-select">
          <option value="ui">UI</option>
          <option value="taxonomy">Taxonomy</option>
        </select>

        <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
          <Search size={14} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }} />
          <input
            placeholder="Search keys or values..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
            className="admin-input"
            style={{ paddingLeft: 28, width: '100%' }}
          />
        </div>

        <span style={{ fontSize: 13, opacity: 0.7 }}>{total} keys</span>
      </div>

      {loading && <p>{t('admin.common.loading')}</p>}

      {!loading && (
        <>
          <table className="admin-table">
            <thead>
              <tr>
                <th style={{ width: '35%' }}>Key</th>
                <th>Value</th>
                <th style={{ width: 60 }}>{t('admin.common.actions')}</th>
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
                        className="admin-input"
                        style={{ width: '100%' }}
                        autoFocus
                      />
                    ) : (
                      <span
                        onClick={() => { setEditingId(item.id); setEditValue(item.value) }}
                        style={{ cursor: 'pointer' }}
                        title="Click to edit"
                      >
                        {item.value || <em style={{ opacity: 0.4 }}>empty</em>}
                      </span>
                    )}
                  </td>
                  <td>
                    {editingId === item.id && (
                      <button onClick={() => handleSave(item)} className="admin-btn-icon" title={t('admin.common.save')}>
                        <Save size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 16, alignItems: 'center' }}>
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="admin-btn-icon">
                <ChevronLeft size={16} />
              </button>
              <span style={{ fontSize: 13 }}>{t('admin.common.page', { page, total: totalPages })}</span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="admin-btn-icon">
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
