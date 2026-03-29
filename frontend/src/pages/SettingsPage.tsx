import { useCallback, useEffect, useState } from 'react'
import { Copy, Key, Plus, ShieldOff, Check, User, Save, X, ChevronDown, ChevronUp, Settings, Eye, EyeOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { getApiKeys, createApiKey, revokeApiKey, updateMe, getApiKeyUsage, type ApiKeyItem, type ApiKeyCreated, type ApiKeyUsageResponse } from '../auth/api'
import { useAuth } from '../auth/AuthContext'

type Tab = 'profile' | 'api-keys'

export function SettingsPage() {
  const { t } = useTranslation()
  const { user, refreshUser } = useAuth()
  const [activeTab, setActiveTab] = useState<Tab>('profile')

  return (
    <div className="settings-page">
      <h1 className="settings-title"><Settings size={20} /> {t('settings.title')}</h1>

      <div className="settings-tabs">
        <button
          className={`settings-tab ${activeTab === 'profile' ? 'settings-tab--active' : ''}`}
          onClick={() => setActiveTab('profile')}
        >
          <User size={16} />
          {t('settings.tabProfile')}
        </button>
        <button
          className={`settings-tab ${activeTab === 'api-keys' ? 'settings-tab--active' : ''}`}
          onClick={() => setActiveTab('api-keys')}
        >
          <Key size={16} />
          {t('settings.tabApiKeys')}
        </button>
      </div>

      {activeTab === 'profile' && <ProfileTab />}
      {activeTab === 'api-keys' && <ApiKeysTab />}
    </div>
  )
}

function ProfileTab() {
  const { t } = useTranslation()
  const { user, refreshUser } = useAuth()
  const [name, setName] = useState(user?.name || '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setName(user?.name || '')
  }, [user?.name])

  const dirty = name !== (user?.name || '')

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await updateMe({ name: name || undefined })
      await refreshUser()
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { /* ignore */ }
    setSaving(false)
  }

  if (!user) return null

  return (
    <section className="settings-section profile-section">
      <div className="profile-field">
        <label className="profile-label">{t('settings.profileName')}</label>
        <div className="profile-input-row">
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder={t('auth.namePlaceholder')}
            className="auth-input"
            maxLength={128}
          />
          <button
            onClick={handleSave}
            disabled={saving || !dirty}
            className="btn-primary"
          >
            {saved ? <Check size={16} /> : <Save size={16} />}
            {saved ? t('settings.saved') : t('settings.save')}
          </button>
        </div>
      </div>

      <div className="profile-field">
        <label className="profile-label">{t('settings.profileEmail')}</label>
        <input
          type="email"
          value={user.email}
          readOnly
          className="auth-input profile-readonly"
        />
      </div>

      <div className="profile-field">
        <label className="profile-label">{t('settings.profileTier')}</label>
        <span className="profile-tier-badge" data-tier={user.tier.toLowerCase()}>{user.tier}</span>
      </div>
    </section>
  )
}

const REVOKE_REASONS = ['compromised', 'rotation', 'unused', 'employee_left', 'other'] as const

function ApiKeysTab() {
  const { t } = useTranslation()
  const [keys, setKeys] = useState<ApiKeyItem[]>([])
  const [loading, setLoading] = useState(true)
  const [newKey, setNewKey] = useState<ApiKeyCreated | null>(null)
  const [keyName, setKeyName] = useState('')
  const [creating, setCreating] = useState(false)
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyItem | null>(null)
  const [revokeReason, setRevokeReason] = useState<string>('')
  const [showRevoked, setShowRevoked] = useState(false)
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const [usageData, setUsageData] = useState<Record<string, ApiKeyUsageResponse>>({})
  const [usageLoading, setUsageLoading] = useState<string | null>(null)

  useEffect(() => {
    if (!revokeTarget) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') { setRevokeTarget(null); setRevokeReason('') } }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [revokeTarget])

  const load = useCallback(async () => {
    try {
      const data = await getApiKeys(showRevoked)
      setKeys(data)
    } catch { /* ignore */ }
    setLoading(false)
  }, [showRevoked])

  useEffect(() => { load() }, [load])

  const handleCreate = async () => {
    setCreating(true)
    try {
      const created = await createApiKey(keyName.trim())
      setNewKey(created)
      setKeyName('')
      await load()
    } catch { /* ignore */ }
    setCreating(false)
  }

  const handleRevokeConfirm = async () => {
    if (!revokeTarget) return
    await revokeApiKey(revokeTarget.id, revokeReason || undefined)
    setRevokeTarget(null)
    setRevokeReason('')
    await load()
  }

  const toggleUsage = async (keyId: string) => {
    if (expandedKey === keyId) {
      setExpandedKey(null)
      return
    }
    setExpandedKey(keyId)
    if (!usageData[keyId]) {
      setUsageLoading(keyId)
      try {
        const data = await getApiKeyUsage(keyId)
        setUsageData(prev => ({ ...prev, [keyId]: data }))
      } catch { /* ignore */ }
      setUsageLoading(null)
    }
  }

  return (
    <section className="settings-section">
      <p className="settings-hint">{t('settings.apiKeysHint')}</p>

      <div className="api-key-create">
        <input
          value={keyName}
          onChange={e => setKeyName(e.target.value)}
          placeholder={t('settings.keyNamePlaceholder')}
          className="auth-input"
        />
        <button onClick={handleCreate} disabled={creating || !keyName.trim()} className="btn-primary">
          <Plus size={16} />
          {t('settings.createKey')}
        </button>
      </div>

      <label className="show-revoked-toggle">
        <input
          type="checkbox"
          checked={showRevoked}
          onChange={e => setShowRevoked(e.target.checked)}
        />
        {showRevoked ? <Eye size={14} /> : <EyeOff size={14} />}
        {t('settings.showRevoked')}
      </label>

      {newKey && (
        <NewKeyModal
          newKey={newKey}
          onClose={() => setNewKey(null)}
        />
      )}

      {loading ? (
        <p className="settings-loading">{t('settings.loading')}</p>
      ) : keys.length === 0 ? (
        <p className="settings-empty">{t('settings.noKeys')}</p>
      ) : (
        <table className="api-keys-table">
          <thead>
            <tr>
              <th>{t('settings.keyName')}</th>
              <th>{t('settings.keyPrefix')}</th>
              <th className="hide-mobile">{t('settings.keyCreated')}</th>
              <th className="hide-mobile">{t('settings.keyLastUsed')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {keys.map(k => (
              <>
                <tr
                  key={k.id}
                  className={`${expandedKey === k.id ? 'row-expanded' : ''} ${!k.is_active ? 'row-revoked' : ''}`}
                  style={{ cursor: 'pointer' }}
                  onClick={() => toggleUsage(k.id)}
                >
                  <td>
                    {expandedKey === k.id ? <ChevronUp size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} /> : <ChevronDown size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />}
                    {k.name || '—'}
                    {!k.is_active && (
                      <span className="revoked-badge" title={k.revoke_reason ? t(`settings.reason.${k.revoke_reason}`) : undefined}>
                        {t('settings.revoked')}
                      </span>
                    )}
                  </td>
                  <td><code className={!k.is_active ? 'text-muted' : ''}>{k.key_prefix}</code></td>
                  <td className="hide-mobile">{new Date(k.created_at).toLocaleDateString()}</td>
                  <td className="hide-mobile">
                    {!k.is_active && k.revoked_at
                      ? new Date(k.revoked_at).toLocaleDateString()
                      : k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : '—'}
                  </td>
                  <td>
                    {k.is_active && (
                      <button onClick={e => { e.stopPropagation(); setRevokeTarget(k) }} className="btn-icon btn-danger" title={t('settings.revokeKey')}>
                        <ShieldOff size={16} />
                      </button>
                    )}
                  </td>
                </tr>
                {expandedKey === k.id && (
                  <tr key={`${k.id}-usage`} className="usage-detail-row">
                    <td colSpan={5}>
                      {usageLoading === k.id ? (
                        <p className="settings-loading">{t('settings.loading')}</p>
                      ) : usageData[k.id] ? (
                        <KeyUsagePanel usage={usageData[k.id]} />
                      ) : null}
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      )}

      {revokeTarget && (
        <div className="api-key-modal-overlay" onClick={() => { setRevokeTarget(null); setRevokeReason('') }}>
          <div className="api-key-modal api-key-modal--small" onClick={e => e.stopPropagation()}>
            <div className="api-key-modal-header">
              <h3>{t('settings.revokeKeyTitle')}</h3>
              <button onClick={() => { setRevokeTarget(null); setRevokeReason('') }} className="btn-icon">
                <X size={18} />
              </button>
            </div>
            <p className="confirm-delete-text">
              {t('settings.revokeKeyConfirm', { name: revokeTarget.name || revokeTarget.key_prefix })}
            </p>
            <div className="revoke-reason-field">
              <label className="profile-label">{t('settings.revokeReason')}</label>
              <select
                value={revokeReason}
                onChange={e => setRevokeReason(e.target.value)}
                className="auth-input"
              >
                <option value="">{t('settings.reason.none')}</option>
                {REVOKE_REASONS.map(r => (
                  <option key={r} value={r}>{t(`settings.reason.${r}`)}</option>
                ))}
              </select>
            </div>
            <div className="api-key-modal-footer">
              <button onClick={() => { setRevokeTarget(null); setRevokeReason('') }} className="btn-secondary">
                {t('settings.cancel')}
              </button>
              <button onClick={handleRevokeConfirm} className="btn-danger-solid">
                <ShieldOff size={16} />
                {t('settings.revokeKey')}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

function KeyUsagePanel({ usage }: { usage: ApiKeyUsageResponse }) {
  const { t } = useTranslation()
  const formatNum = (n: number) => n.toLocaleString()

  return (
    <div className="key-usage-panel">
      <div className="key-usage-kpi">
        <div className="kpi-card">
          <span className="kpi-value">{formatNum(usage.total_requests)}</span>
          <span className="kpi-label">{t('analytics.kpiRequests')}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-value">{formatNum(usage.total_tokens)}</span>
          <span className="kpi-label">{t('analytics.kpiTokens')}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-value">${usage.total_charge_usd}</span>
          <span className="kpi-label">{t('analytics.kpiCharge')}</span>
        </div>
      </div>

      {usage.daily.length > 0 && (
        <div className="key-usage-chart">
          <ResponsiveContainer width="100%" height={120}>
            <AreaChart data={usage.daily}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={d => d.slice(5)} />
              <YAxis hide />
              <Tooltip />
              <Area type="monotone" dataKey="requests" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.15} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {usage.by_action.length > 0 && (
        <table className="usage-breakdown-table">
          <thead>
            <tr>
              <th>{t('analytics.action')}</th>
              <th>{t('analytics.kpiRequests')}</th>
              <th>{t('analytics.kpiTokens')}</th>
            </tr>
          </thead>
          <tbody>
            {usage.by_action.map(a => (
              <tr key={a.action}>
                <td><code>{a.action}</code></td>
                <td>{formatNum(a.count)}</td>
                <td>{formatNum(a.tokens)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {usage.total_requests === 0 && (
        <p className="settings-empty">{t('analytics.noData')}</p>
      )}
    </div>
  )
}

function NewKeyModal({ newKey, onClose }: { newKey: ApiKeyCreated; onClose: () => void }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState<string | null>(null)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopied(id)
    setTimeout(() => setCopied(null), 2000)
  }

  const mcpConfig = JSON.stringify({
    mcpServers: {
      lexiro: {
        url: `${window.location.origin}/mcp`,
        headers: {
          Authorization: `Bearer ${newKey.key}`,
        },
      },
    },
  }, null, 2)

  return (
    <div className="api-key-modal-overlay" onClick={onClose}>
      <div className="api-key-modal" onClick={e => e.stopPropagation()}>
        <div className="api-key-modal-header">
          <h3>{t('settings.newKeyTitle')}</h3>
          <button onClick={onClose} className="btn-icon">
            <X size={18} />
          </button>
        </div>

        <p className="api-key-warning">{t('settings.keyShownOnce')}</p>

        <div className="api-key-value">
          <code>{newKey.key}</code>
          <button
            onClick={() => handleCopy(newKey.key, 'new-key')}
            className="btn-icon"
          >
            {copied === 'new-key' ? <Check size={16} /> : <Copy size={16} />}
          </button>
        </div>

        <h4>{t('settings.mcpConfig')}</h4>
        <div className="api-key-value mcp-config">
          <pre>{mcpConfig}</pre>
          <button
            onClick={() => handleCopy(mcpConfig, 'mcp-config')}
            className="btn-icon"
          >
            {copied === 'mcp-config' ? <Check size={16} /> : <Copy size={16} />}
          </button>
        </div>

        <div className="api-key-modal-footer">
          <button onClick={onClose} className="btn-primary">
            {t('settings.done')}
          </button>
        </div>
      </div>
    </div>
  )
}