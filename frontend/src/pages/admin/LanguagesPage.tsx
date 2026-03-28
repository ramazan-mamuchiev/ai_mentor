import { useEffect, useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, Globe, Play } from 'lucide-react'
import {
  adminListLanguages, adminCreateLanguage, adminDeleteLanguage,
  adminTriggerTranslate, adminGetTranslateProgress,
  type AdminLanguage,
} from '../../api/admin-i18n'

export function LanguagesPage() {
  const { t } = useTranslation()
  const [languages, setLanguages] = useState<AdminLanguage[]>([])
  const [loading, setLoading] = useState(true)
  const [newCode, setNewCode] = useState('')
  const [newName, setNewName] = useState('')
  const [translating, setTranslating] = useState<Record<number, { total: number; done: number; status: string; errors: number }>>({})
  const pollTimers = useRef<Record<number, ReturnType<typeof setInterval>>>({})

  const loadLanguages = async () => {
    setLoading(true)
    try {
      setLanguages(await adminListLanguages())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLanguages()
    return () => {
      Object.values(pollTimers.current).forEach(clearInterval)
    }
  }, [])

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

          <span className="logs-count">{languages.length} {t('admin.languages.count')}</span>
        </div>
      </div>

      {loading && <div className="admin-loading">{t('admin.common.loading')}</div>}

      {!loading && languages.length === 0 && (
        <div className="admin-empty">{t('admin.languages.empty')}</div>
      )}

      {!loading && languages.length > 0 && (
        <table className="admin-table">
          <thead>
            <tr>
              <th>{t('admin.languages.colCode')}</th>
              <th>{t('admin.languages.colName')}</th>
              <th>{t('admin.languages.colDefault')}</th>
              <th>{t('admin.languages.colActive')}</th>
              <th>{t('admin.languages.colSystem')}</th>
              <th>{t('admin.languages.colKeys')}</th>
              <th>{t('admin.languages.colAutoTranslate')}</th>
              <th>{t('admin.common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {languages.map(lang => {
              const progress = translating[lang.id]
              const isTranslating = progress && progress.status === 'running'
              const isSourceLang = lang.id === defaultLangId
              return (
                <tr key={lang.id}>
                  <td><code>{lang.code}</code></td>
                  <td>{lang.name_native}</td>
                  <td>{lang.is_default ? '✓' : ''}</td>
                  <td>{lang.is_active ? '✓' : '—'}</td>
                  <td>{lang.is_system ? '✓' : ''}</td>
                  <td>{lang.total_keys}</td>
                  <td>
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
                      <button onClick={() => handleTranslate(lang.id)} className="logs-icon-btn" title={t('admin.languages.translateTitle')}>
                        <Play size={14} />
                      </button>
                    )}
                    {progress && progress.status === 'complete' && <span style={{ fontSize: 12, color: 'var(--success)' }}> {t('admin.languages.translateDone')}</span>}
                    {progress && progress.status === 'partial' && <span style={{ fontSize: 12, color: 'var(--warning)' }}> {t('admin.languages.translatePartial', { errors: progress.errors })}</span>}
                  </td>
                  <td>
                    {!lang.is_system && (
                      <button
                        className="logs-icon-btn"
                        onClick={() => handleDelete(lang.id, lang.is_system)}
                        title={t('admin.common.delete')}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
