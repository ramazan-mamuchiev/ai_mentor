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
    if (!confirm('Delete this language and all its translations?')) return
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

  return (
    <div className="logs-page">
      <div className="admin-page-header">
        <h1><Globe size={20} /> {t('admin.nav.languages')}</h1>
      </div>

      {/* Toolbar — logs-style */}
      <div className="logs-toolbar">
        <div className="logs-toolbar__row">
          <input
            placeholder="Code (e.g. de)"
            value={newCode}
            onChange={e => setNewCode(e.target.value)}
            className="logs-search"
            style={{ width: 100, minWidth: 80 }}
          />
          <input
            placeholder="Native name (e.g. Deutsch)"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            className="logs-search"
            style={{ width: 200, minWidth: 140 }}
          />
          <button
            onClick={handleCreate}
            className="logs-live-btn logs-live-btn--active"
            disabled={!newCode.trim() || !newName.trim()}
          >
            <Plus size={13} />
            {t('admin.common.create')}
          </button>

          <span className="logs-count">{languages.length} {t('admin.nav.languages').toLowerCase()}</span>
        </div>
      </div>

      {loading && <div className="admin-loading">{t('admin.common.loading')}</div>}

      {!loading && languages.length === 0 && (
        <div className="admin-empty">{t('admin.common.loading')}</div>
      )}

      {!loading && languages.length > 0 && (
        <table className="admin-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Name</th>
              <th>Default</th>
              <th>Active</th>
              <th>System</th>
              <th>Keys</th>
              <th>Auto-translate</th>
              <th>{t('admin.common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {languages.map(lang => {
              const progress = translating[lang.id]
              const isTranslating = progress && progress.status === 'running'
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
                    ) : (
                      <button onClick={() => handleTranslate(lang.id)} className="logs-icon-btn" title="Auto-translate missing keys">
                        <Play size={14} />
                      </button>
                    )}
                    {progress && progress.status === 'complete' && <span style={{ fontSize: 12, color: 'var(--success)' }}> Done</span>}
                    {progress && progress.status === 'partial' && <span style={{ fontSize: 12, color: 'var(--warning)' }}> Partial ({progress.errors} errors)</span>}
                  </td>
                  <td>
                    <button
                      className="logs-icon-btn"
                      onClick={() => handleDelete(lang.id, lang.is_system)}
                      disabled={lang.is_system}
                      title={lang.is_system ? 'System language' : t('admin.common.delete')}
                    >
                      <Trash2 size={14} />
                    </button>
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
