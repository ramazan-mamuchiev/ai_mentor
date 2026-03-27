import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Save } from 'lucide-react'
import { getRole, patchRole, type RoleDetail } from '../../api/admin'

const FEATURE_GROUPS: Record<string, string[]> = {
  Chat: ['chat', 'chat.feedback'],
  Documents: ['documents.upload', 'documents.delete', 'documents.view'],
  Products: ['products.view', 'products.edit', 'products.delete'],
  Other: ['share', 'reindex', 'analytics', 'settings', 'mcp'],
  Admin: [
    'admin', 'admin.tenants', 'admin.documents', 'admin.chats',
    'admin.logs', 'admin.stats', 'admin.roles', 'admin.prompts',
  ],
}

const LIMIT_KEYS = [
  { key: 'max_documents', label: 'Max Documents' },
  { key: 'max_tokens_per_day', label: 'Max Tokens/Day' },
  { key: 'max_file_size_mb', label: 'Max File Size (MB)' },
  { key: 'max_sessions', label: 'Max Sessions' },
  { key: 'max_api_keys', label: 'Max API Keys' },
]

const ALL_QUERY_TYPES = ['overview', 'technical', 'code', 'comparison', 'troubleshooting', 'chitchat']

export function RoleDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [role, setRole] = useState<RoleDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState(0)
  const [features, setFeatures] = useState<Record<string, boolean>>({})
  const [limits, setLimits] = useState<Record<string, string>>({})
  const [queryTypes, setQueryTypes] = useState<string[]>([])
  const [suggestionRole, setSuggestionRole] = useState('default')

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const r = await getRole(Number(id))
      setRole(r)
      setName(r.name)
      setDescription(r.description)
      setPriority(r.priority)

      const perms = r.permissions as any || {}
      setFeatures(perms.features || {})
      const lim = perms.limits || {}
      const limStrings: Record<string, string> = {}
      for (const { key } of LIMIT_KEYS) {
        limStrings[key] = lim[key] != null ? String(lim[key]) : ''
      }
      setLimits(limStrings)

      const ctx = perms.chat_context || {}
      setQueryTypes(ctx.allowed_query_types || ALL_QUERY_TYPES)
      setSuggestionRole(ctx.suggestion_template_role || 'default')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const handleSave = async () => {
    if (!id) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const parsedLimits: Record<string, number | null> = {}
      for (const { key } of LIMIT_KEYS) {
        const val = limits[key]
        parsedLimits[key] = val === '' ? null : Number(val)
      }

      const permissions = {
        features,
        limits: Object.fromEntries(
          Object.entries(parsedLimits).filter(([, v]) => v !== null)
        ),
        chat_context: {
          allowed_query_types: queryTypes,
          suggestion_template_role: suggestionRole,
        },
      }

      const updated = await patchRole(Number(id), { name, description, priority, permissions })
      setRole(updated)
      setSuccess('Saved')
      setTimeout(() => setSuccess(''), 2000)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const toggleFeature = (key: string) => {
    setFeatures(prev => ({ ...prev, [key]: !prev[key] }))
  }

  const toggleQueryType = (qt: string) => {
    setQueryTypes(prev =>
      prev.includes(qt) ? prev.filter(t => t !== qt) : [...prev, qt]
    )
  }

  if (loading) return <div className="admin-loading">Loading...</div>
  if (!role) return <div className="admin-error">Role not found</div>

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <button className="btn" onClick={() => navigate('/app/admin/roles')}>
          <ArrowLeft size={14} /> Back
        </button>
        <h1>
          {role.is_system ? '🔒 ' : ''}
          {role.slug}
        </h1>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          <Save size={14} /> {saving ? 'Saving...' : 'Save'}
        </button>
      </div>

      {error && <div className="admin-error">{error}</div>}
      {success && <div className="admin-success">{success}</div>}

      <div className="admin-card">
        <h3>Basic Info</h3>
        <div className="admin-form-row">
          <label>Name</label>
          <input value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div className="admin-form-row">
          <label>Description</label>
          <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2} />
        </div>
        <div className="admin-form-row">
          <label>Priority</label>
          <input type="number" value={priority} onChange={e => setPriority(Number(e.target.value))} />
          <small>Higher priority wins for prompt overrides when user has multiple roles</small>
        </div>
      </div>

      <div className="admin-card">
        <h3>Feature Permissions</h3>
        {Object.entries(FEATURE_GROUPS).map(([group, keys]) => (
          <div key={group} style={{ marginBottom: 12 }}>
            <strong>{group}</strong>
            <div className="admin-checkbox-grid">
              {keys.map(key => (
                <label key={key} className="admin-checkbox-label">
                  <input
                    type="checkbox"
                    checked={!!features[key]}
                    onChange={() => toggleFeature(key)}
                  />
                  {key}
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="admin-card">
        <h3>Limits</h3>
        <small>Leave empty for unlimited</small>
        {LIMIT_KEYS.map(({ key, label }) => (
          <div className="admin-form-row" key={key}>
            <label>{label}</label>
            <input
              type="number"
              value={limits[key] || ''}
              onChange={e => setLimits(prev => ({ ...prev, [key]: e.target.value }))}
              placeholder="unlimited"
            />
          </div>
        ))}
      </div>

      <div className="admin-card">
        <h3>Chat Context</h3>
        <div className="admin-form-row">
          <label>Allowed Query Types</label>
          <div className="admin-checkbox-grid">
            {ALL_QUERY_TYPES.map(qt => (
              <label key={qt} className="admin-checkbox-label">
                <input
                  type="checkbox"
                  checked={queryTypes.includes(qt)}
                  onChange={() => toggleQueryType(qt)}
                />
                {qt}
              </label>
            ))}
          </div>
        </div>
        <div className="admin-form-row">
          <label>Suggestion Template Role</label>
          <input value={suggestionRole} onChange={e => setSuggestionRole(e.target.value)} />
        </div>
      </div>

      <div className="admin-card">
        <h3>Permissions JSON</h3>
        <pre className="admin-json-preview">
          {JSON.stringify(role.permissions, null, 2)}
        </pre>
      </div>
    </div>
  )
}
