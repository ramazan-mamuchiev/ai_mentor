import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Plus, MessageSquareCode, Lock, Pencil } from 'lucide-react'
import {
  listPrompts, listRoles, createPrompt,
  type PromptTemplateItem, type RoleListItem,
} from '../../api/admin'

interface GroupedPrompt {
  query_type: string
  base: PromptTemplateItem | null
  overrides: PromptTemplateItem[]
}

export function PromptsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [prompts, setPrompts] = useState<PromptTemplateItem[]>([])
  const [roles, setRoles] = useState<RoleListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [showCreate, setShowCreate] = useState(false)
  const [newQueryType, setNewQueryType] = useState('')
  const [newRoleId, setNewRoleId] = useState<number | ''>('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [p, r] = await Promise.all([listPrompts(), listRoles()])
      setPrompts(p)
      setRoles(r)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const grouped: GroupedPrompt[] = (() => {
    const map = new Map<string, GroupedPrompt>()
    for (const p of prompts) {
      if (!map.has(p.query_type)) {
        map.set(p.query_type, { query_type: p.query_type, base: null, overrides: [] })
      }
      const g = map.get(p.query_type)!
      if (p.role_id === null) {
        g.base = p
      } else {
        g.overrides.push(p)
      }
    }
    return Array.from(map.values()).sort((a, b) => a.query_type.localeCompare(b.query_type))
  })()

  const baseQueryTypes = grouped.map(g => g.query_type)

  const handleCreate = async () => {
    try {
      const pt = await createPrompt({
        query_type: newQueryType,
        role_id: newRoleId === '' ? null : newRoleId,
      })
      setShowCreate(false)
      setNewQueryType('')
      setNewRoleId('')
      navigate(`/app/admin/prompts/${pt.id}`)
    } catch (e: any) {
      setError(e.message)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h1><MessageSquareCode size={20} /> {t('admin.prompts.title')}</h1>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <Plus size={14} /> {t('admin.prompts.newOverride')}
        </button>
      </div>

      {error && <div className="admin-error">{error}</div>}

      {showCreate && (
        <div className="admin-card" style={{ marginBottom: 16 }}>
          <h3>{t('admin.prompts.createOverride')}</h3>
          <div className="admin-form-row">
            <label>{t('admin.prompts.queryType')}</label>
            <select value={newQueryType} onChange={e => setNewQueryType(e.target.value)}>
              <option value="">{t('admin.prompts.selectType')}</option>
              {baseQueryTypes.map(qt => (
                <option key={qt} value={qt}>{qt}</option>
              ))}
              <option value="__custom">{t('admin.prompts.customType')}</option>
            </select>
            {newQueryType === '__custom' && (
              <input
                style={{ marginTop: 4 }}
                placeholder={t('admin.prompts.customTypePlaceholder')}
                onChange={e => setNewQueryType(e.target.value)}
              />
            )}
          </div>
          <div className="admin-form-row">
            <label>{t('admin.prompts.role')}</label>
            <select value={newRoleId} onChange={e => setNewRoleId(e.target.value === '' ? '' : Number(e.target.value))}>
              <option value="">{t('admin.prompts.baseNoRole')}</option>
              {roles.filter(r => !r.is_system || r.slug !== 'admin').map(r => (
                <option key={r.id} value={r.id}>{r.name} ({r.slug})</option>
              ))}
            </select>
          </div>
          <div className="admin-form-actions">
            <button className="btn btn-primary" onClick={handleCreate} disabled={!newQueryType || newQueryType === '__custom'}>
              {t('admin.common.create')}
            </button>
            <button className="btn" onClick={() => setShowCreate(false)}>{t('admin.common.cancel')}</button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="admin-loading">{t('admin.common.loading')}</div>
      ) : (
        <div className="admin-prompts-grid">
          {grouped.map(g => (
            <div key={g.query_type} className="admin-card">
              <div className="admin-card-header">
                <h3><code>{g.query_type}</code></h3>
              </div>

              {g.base && (
                <div
                  className="admin-prompt-row admin-prompt-row--base"
                  onClick={() => navigate(`/app/admin/prompts/${g.base!.id}`)}
                >
                  <span>
                    {g.base.is_system ? <Lock size={12} /> : null}
                    {' '}{t('admin.prompts.basePrompt')}
                    {g.base.is_customized && <span className="admin-badge admin-badge--warning">{t('admin.prompts.edited')}</span>}
                  </span>
                  <Pencil size={14} />
                </div>
              )}

              {g.overrides.length > 0 ? (
                g.overrides.map(ovr => (
                  <div
                    key={ovr.id}
                    className="admin-prompt-row"
                    onClick={() => navigate(`/app/admin/prompts/${ovr.id}`)}
                  >
                    <span>
                      {t('admin.prompts.roleLabel')} <strong>{ovr.role_slug}</strong>
                    </span>
                    <Pencil size={14} />
                  </div>
                ))
              ) : (
                <div className="admin-prompt-row admin-prompt-row--empty">
                  {t('admin.prompts.noOverrides')}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
