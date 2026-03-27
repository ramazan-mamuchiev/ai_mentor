import { useCallback, useEffect, useState } from 'react'
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
        <h1><MessageSquareCode size={20} /> Prompt Templates</h1>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <Plus size={14} /> New Override
        </button>
      </div>

      {error && <div className="admin-error">{error}</div>}

      {showCreate && (
        <div className="admin-card" style={{ marginBottom: 16 }}>
          <h3>Create Prompt Override</h3>
          <div className="admin-form-row">
            <label>Query Type</label>
            <select value={newQueryType} onChange={e => setNewQueryType(e.target.value)}>
              <option value="">— select —</option>
              {baseQueryTypes.map(qt => (
                <option key={qt} value={qt}>{qt}</option>
              ))}
              <option value="__custom">Custom type...</option>
            </select>
            {newQueryType === '__custom' && (
              <input
                style={{ marginTop: 4 }}
                placeholder="custom_type"
                onChange={e => setNewQueryType(e.target.value)}
              />
            )}
          </div>
          <div className="admin-form-row">
            <label>Role (empty = base prompt)</label>
            <select value={newRoleId} onChange={e => setNewRoleId(e.target.value === '' ? '' : Number(e.target.value))}>
              <option value="">— base (no role) —</option>
              {roles.filter(r => !r.is_system || r.slug !== 'admin').map(r => (
                <option key={r.id} value={r.id}>{r.name} ({r.slug})</option>
              ))}
            </select>
          </div>
          <div className="admin-form-actions">
            <button className="btn btn-primary" onClick={handleCreate} disabled={!newQueryType || newQueryType === '__custom'}>
              Create
            </button>
            <button className="btn" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="admin-loading">Loading...</div>
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
                    {' '}Base prompt
                    {g.base.is_customized && <span className="admin-badge admin-badge--warning"> edited</span>}
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
                      Role: <strong>{ovr.role_slug}</strong>
                    </span>
                    <Pencil size={14} />
                  </div>
                ))
              ) : (
                <div className="admin-prompt-row admin-prompt-row--empty">
                  No role overrides
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
