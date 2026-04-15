import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Save, Lock } from 'lucide-react'
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
  const { t } = useTranslation()
  const GROUP_LABELS: Record<string, string> = {
    Chat: t('admin.roleDetail.groupChat'),
    Documents: t('admin.roleDetail.groupDocuments'),
    Products: t('admin.roleDetail.groupProducts'),
    Other: t('admin.roleDetail.groupOther'),
    Admin: t('admin.roleDetail.groupAdmin'),
  }
  const LIMIT_LABELS: Record<string, string> = {
    max_documents: t('admin.roleDetail.maxDocuments'),
    max_tokens_per_day: t('admin.roleDetail.maxTokensPerDay'),
    max_file_size_mb: t('admin.roleDetail.maxFileSizeMB'),
    max_sessions: t('admin.roleDetail.maxSessions'),
    max_api_keys: t('admin.roleDetail.maxApiKeys'),
  }

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
      setSuccess(t('admin.common.saved'))
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
      prev.includes(qt) ? prev.filter(x => x !== qt) : [...prev, qt]
    )
  }

  if (loading) return <div className="admin-loading">{t('admin.roleDetail.loading')}</div>
  if (!role) return <div className="admin-error">{t('admin.roleDetail.notFound')}</div>

  return (
    <div className="admin-page">
      <div className="admin-detail-header">
        <button className="btn" onClick={() => navigate('/app/admin/roles')}>
          <ArrowLeft size={14} /> {t('admin.common.back')}
        </button>
        <h1>
          {role.slug}
          {role.is_system && (
            <span className="admin-system-badge">
              <Lock size={10} /> system
            </span>
          )}
        </h1>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          <Save size={14} /> {saving ? t('admin.common.saving') : t('admin.common.save')}
        </button>
      </div>

      {error && <div className="admin-error">{error}</div>}
      {success && <div className="admin-success">{success}</div>}

      <div className="admin-card">
        <h3>{t('admin.roleDetail.basicInfo')}</h3>
        <div className="admin-form-row">
          <label>{t('admin.roleDetail.name')}</label>
          <input value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div className="admin-form-row">
          <label>{t('admin.roleDetail.description')}</label>
          <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2} />
        </div>
        <div className="admin-form-row">
          <label>{t('admin.roleDetail.priority')}</label>
          <input type="number" value={priority} onChange={e => setPriority(Number(e.target.value))} style={{ maxWidth: 120 }} />
          <small>{t('admin.roleDetail.priorityHint')}</small>
        </div>
      </div>

      <div className="admin-card">
        <h3>{t('admin.roleDetail.featurePermissions')}</h3>
        {Object.entries(FEATURE_GROUPS).map(([group, keys]) => (
          <div key={group} className="admin-feature-group">
            <div className="admin-feature-group-title">{GROUP_LABELS[group] || group}</div>
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
        <h3>{t('admin.roleDetail.limits')}</h3>
        <small style={{ display: 'block', marginBottom: 12, fontSize: 12, color: 'var(--text-muted)' }}>
          {t('admin.roleDetail.limitsHint')}
        </small>
        <div className="admin-limits-grid">
          {LIMIT_KEYS.map(({ key, label }) => (
            <div className="admin-form-row" key={key}>
              <label>{LIMIT_LABELS[key] || label}</label>
              <input
                type="number"
                value={limits[key] || ''}
                onChange={e => setLimits(prev => ({ ...prev, [key]: e.target.value }))}
                placeholder={t('admin.roleDetail.unlimited')}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="admin-card">
        <h3>{t('admin.roleDetail.chatContext')}</h3>
        <div className="admin-form-row">
          <label>{t('admin.roleDetail.allowedQueryTypes')}</label>
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
          <label>{t('admin.roleDetail.suggestionTemplateRole')}</label>
          <input value={suggestionRole} onChange={e => setSuggestionRole(e.target.value)} />
        </div>
      </div>

      <details className="admin-json-toggle">
        <summary>{t('admin.roleDetail.permissionsJSON')}</summary>
        <pre className="admin-json-preview">
          {JSON.stringify(role.permissions, null, 2)}
        </pre>
      </details>
    </div>
  )
}
