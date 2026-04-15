import { useCallback, useEffect, useMemo, useState } from 'react'
import { Copy, Key, Link2, Plus, ShieldOff, Check, User, Save, X, ChevronDown, ChevronUp, Settings, Eye, EyeOff, RotateCcw, Trash2, ExternalLink } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { getApiKeys, createApiKey, revokeApiKey, updateMe, getApiKeyUsage, type ApiKeyItem, type ApiKeyCreated, type ApiKeyUsageResponse } from '../auth/api'
import { listSharedLinks, deleteSharedLink } from '../api/share'
import type { SharedLinkResponse } from '../types'
import { useAuth } from '../auth/AuthContext'
import { usePageTour } from '../hooks/usePageTour'
import { getSettingsSteps } from '../tour/steps/settingsSteps'
import { resetAllHelpTours } from '../tour/HelpTourContext'
import { fmtUsd } from '../utils/format'

type Tab = 'profile' | 'api-keys' | 'shared-links'

export function SettingsPage() {
  const { t } = useTranslation()
  const { user, refreshUser } = useAuth()
  const settingsTourSteps = useMemo(() => getSettingsSteps(t), [t])
  usePageTour('settings', settingsTourSteps)
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
        <button
          className={`settings-tab ${activeTab === 'shared-links' ? 'settings-tab--active' : ''}`}
          onClick={() => setActiveTab('shared-links')}
        >
          <Link2 size={16} />
          {t('settings.tabSharedLinks')}
        </button>
      </div>

      {activeTab === 'profile' && <ProfileTab />}
      {activeTab === 'api-keys' && <ApiKeysTab />}
      {activeTab === 'shared-links' && <SharedLinksTab />}
    </div>
  )
}

function ProfileTab() {
  const { t } = useTranslation()
  const { user, refreshUser } = useAuth()
  const [name, setName] = useState(user?.name || '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [helpReset, setHelpReset] = useState(false)

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

      <div className="profile-field">
        <button
          className="btn"
          onClick={() => {
            resetAllHelpTours()
            setHelpReset(true)
            setTimeout(() => setHelpReset(false), 2000)
          }}
        >
          {helpReset ? <Check size={16} /> : <RotateCcw size={16} />}
          {helpReset ? t('help.resetAllDone') : t('help.resetAll')}
        </button>
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
          <span className="kpi-value">{fmtUsd(usage.total_charge_usd)}</span>
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

const SHARE_TYPE_LABELS: Record<string, string> = {
  session: 'Chat',
  message: 'Answer',
  debug_chat: 'Debug (chat)',
  debug_document: 'Debug (doc)',
  debug_product: 'Debug (product)',
  document_preview: 'Document',
  lifecycle: 'Lifecycle',
}

function SharedLinksTab() {
  const { t } = useTranslation()
  const [links, setLinks] = useState<SharedLinkResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [showInactive, setShowInactive] = useState(false)
  const [revokeToken, setRevokeToken] = useState<string | null>(null)
  const [copiedToken, setCopiedToken] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await listSharedLinks({ includeInactive: showInactive })
      setLinks(data)
    } catch { /* ignore */ }
    setLoading(false)
  }, [showInactive])

  useEffect(() => { setLoading(true); load() }, [load])

  const handleRevoke = async (token: string) => {
    try {
      await deleteSharedLink(token)
      setLinks(prev => prev.map(l => l.token === token ? { ...l, is_active: false } : l))
    } catch { /* ignore */ }
    setRevokeToken(null)
  }

  const handleCopy = (url: string, token: string) => {
    navigator.clipboard.writeText(url)
    setCopiedToken(token)
    setTimeout(() => setCopiedToken(null), 2000)
  }

  return (
    <section className="settings-section">
      <p className="settings-hint">{t('settings.sharedLinksHint')}</p>

      <label className="show-revoked-toggle">
        <input type="checkbox" checked={showInactive} onChange={e => setShowInactive(e.target.checked)} />
        {showInactive ? <Eye size={14} /> : <EyeOff size={14} />}
        {t('settings.showInactive')}
      </label>

      {loading ? (
        <p className="settings-loading">{t('settings.loading')}</p>
      ) : links.length === 0 ? (
        <p className="settings-empty">{t('settings.noSharedLinks')}</p>
      ) : (
        <div className="shared-links-scroll">
          <table className="api-keys-table shared-links-table">
            <thead>
              <tr>
                <th>{t('settings.sharedLinkTitle')}</th>
                <th>{t('settings.sharedLinkType')}</th>
                <th className="hide-mobile">{t('settings.sharedLinkViews')}</th>
                <th className="hide-mobile">{t('settings.keyCreated')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {links.map(link => (
                <tr key={link.token} className={!link.is_active ? 'row-revoked' : ''}>
                  <td className="shared-link-title-cell">
                    <span className="shared-link-title-text">{link.title || '—'}</span>
                  </td>
                  <td>
                    <span className={`shared-link-type-badge shared-link-type--${link.share_type}`}>
                      {SHARE_TYPE_LABELS[link.share_type] || link.share_type}
                    </span>
                  </td>
                  <td className="hide-mobile">{link.view_count}</td>
                  <td className="hide-mobile">{new Date(link.created_at).toLocaleDateString()}</td>
                  <td className="shared-link-actions">
                    <button
                      className="btn-icon"
                      onClick={() => handleCopy(link.url, link.token)}
                      title={t('share.copyLink')}
                    >
                      {copiedToken === link.token ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                    <a
                      className="btn-icon"
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={t('settings.sharedLinkOpen')}
                    >
                      <ExternalLink size={14} />
                    </a>
                    {link.is_active && (
                      <button
                        className="btn-icon btn-danger"
                        onClick={() => setRevokeToken(link.token)}
                        title={t('share.deactivate')}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                    {!link.is_active && (
                      <span className="revoked-badge">{t('settings.sharedLinkInactive')}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {revokeToken && (
        <div className="api-key-modal-overlay" onClick={() => setRevokeToken(null)}>
          <div className="api-key-modal api-key-modal--small" onClick={e => e.stopPropagation()}>
            <div className="api-key-modal-header">
              <h3>{t('settings.revokeSharedLinkTitle')}</h3>
              <button onClick={() => setRevokeToken(null)} className="btn-icon"><X size={18} /></button>
            </div>
            <p className="confirm-delete-text">{t('settings.revokeSharedLinkConfirm')}</p>
            <div className="api-key-modal-footer">
              <button onClick={() => setRevokeToken(null)} className="btn-secondary">{t('settings.cancel')}</button>
              <button onClick={() => handleRevoke(revokeToken)} className="btn-danger-solid">
                <Trash2 size={16} />
                {t('share.deactivate')}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
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