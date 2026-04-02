import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ArrowLeft, Shield, FileText, MessageSquare, Key,
  Calendar, Mail, Hash, CheckCircle, XCircle,
  Zap, Coins, BarChart3,
} from 'lucide-react'
import {
  getTenant,
  patchTenant,
  listRoles,
  getTenantRoles,
  assignTenantRole,
  unassignTenantRole,
  type TenantDetail,
  type RoleListItem,
  type TenantRoleItem,
} from '../../api/admin'
import { useAuth } from '../../auth/AuthContext'
import { ConfirmDialog } from '../../components/ConfirmDialog'

function formatCharge(raw: string): string {
  const n = parseFloat(raw)
  if (isNaN(n)) return raw
  return n.toFixed(2)
}

function getInitials(name: string | null, email: string): string {
  if (name) {
    const parts = name.trim().split(/\s+/)
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
    return name.slice(0, 2).toUpperCase()
  }
  return email.slice(0, 2).toUpperCase()
}

function getAvatarIndex(email: string): number {
  let hash = 0
  for (let i = 0; i < email.length; i++) {
    hash = email.charCodeAt(i) + ((hash << 5) - hash)
  }
  return Math.abs(hash) % 8
}

type Tab = 'overview' | 'content'

export function TenantDetailPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [tenant, setTenant] = useState<TenantDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [showBlockConfirm, setShowBlockConfirm] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  const [allRoles, setAllRoles] = useState<RoleListItem[]>([])
  const [tenantRoles, setTenantRoles] = useState<TenantRoleItem[]>([])
  const [rolesLoading, setRolesLoading] = useState(false)

  const isSelf = id === user?.id

  useEffect(() => {
    if (!id) return
    setLoading(true)
    getTenant(id)
      .then(setTenant)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    if (!id) return
    setRolesLoading(true)
    Promise.all([listRoles(), getTenantRoles(id)])
      .then(([roles, assigned]) => {
        setAllRoles(roles)
        setTenantRoles(assigned)
      })
      .catch(() => {})
      .finally(() => setRolesLoading(false))
  }, [id])

  const handlePatch = async (data: { role?: string; tier?: string; is_active?: boolean }) => {
    if (!id) return
    try {
      const updated = await patchTenant(id, data)
      setTenant(updated)
    } catch { /* ignore */ }
  }

  const handleToggleRole = async (role: RoleListItem) => {
    if (!id) return
    const isAssigned = tenantRoles.some(tr => tr.role_id === role.id)
    try {
      if (isAssigned) {
        await unassignTenantRole(id, role.id)
        setTenantRoles(prev => prev.filter(tr => tr.role_id !== role.id))
      } else {
        const assigned = await assignTenantRole(id, role.id)
        setTenantRoles(prev => [...prev, assigned])
      }
    } catch { /* ignore */ }
  }

  const handleToggleActive = () => {
    if (tenant?.is_active) {
      setShowBlockConfirm(true)
    } else {
      handlePatch({ is_active: true })
    }
  }

  const confirmBlock = () => {
    handlePatch({ is_active: false })
    setShowBlockConfirm(false)
  }

  if (loading) return <div className="admin-loading">{t('admin.tenantDetail.loading')}</div>
  if (!tenant) return <div className="admin-empty">{t('admin.tenantDetail.notFound')}</div>

  const assignedRoleIds = new Set(tenantRoles.map(tr => tr.role_id))
  const initials = getInitials(tenant.name, tenant.email)
  const avatarIdx = getAvatarIndex(tenant.email)

  return (
    <div className="td-page">
      {/* Back button */}
      <button className="td-back" onClick={() => navigate('/app/admin/tenants')}>
        <ArrowLeft size={14} />
        <span>{t('admin.tenantDetail.backToTenants')}</span>
      </button>

      {/* Hero section */}
      <div className="td-hero">
        <div className={`td-hero__avatar td-avatar--${avatarIdx}`}>
          {initials}
        </div>
        <div className="td-hero__info">
          <div className="td-hero__name-row">
            <h1 className="td-hero__name">{tenant.name || tenant.email.split('@')[0]}</h1>
            <span className={`td-status-badge ${tenant.is_active ? 'td-status-badge--active' : 'td-status-badge--blocked'}`}>
              {tenant.is_active ? t('admin.tenants.active') : t('admin.tenants.blocked')}
            </span>
            <span className={`td-tier-badge td-tier-badge--${tenant.tier}`}>
              {tenant.tier}
            </span>
          </div>
          <div className="td-hero__email">{tenant.email}</div>
          <div className="td-hero__meta">
            <span className="td-hero__meta-item">
              <Hash size={12} />
              {tenant.slug}
            </span>
            <span className="td-hero__meta-item">
              <Calendar size={12} />
              {new Date(tenant.created_at).toLocaleDateString()}
            </span>
            <span className="td-hero__meta-item">
              {tenant.email_verified
                ? <><CheckCircle size={12} className="td-icon--success" /> {t('admin.tenantDetail.emailVerified')}</>
                : <><XCircle size={12} className="td-icon--danger" /> {t('admin.tenantDetail.emailNotVerified')}</>
              }
            </span>
          </div>
        </div>
        <div className="td-hero__actions">
          <button
            className={`admin-btn ${tenant.is_active ? 'admin-btn--danger' : 'admin-btn--primary'}`}
            onClick={handleToggleActive}
            disabled={isSelf}
            title={isSelf ? t('admin.tenants.cannotBlockSelf') : undefined}
          >
            {tenant.is_active ? t('admin.tenants.block') : t('admin.tenants.unblock')}
          </button>
        </div>
      </div>

      {/* Stats strip */}
      <div className="td-stats">
        <div className="td-stat">
          <div className="td-stat__icon"><Zap size={16} /></div>
          <div className="td-stat__data">
            <div className="td-stat__value">{tenant.total_requests.toLocaleString()}</div>
            <div className="td-stat__label">{t('admin.tenantDetail.requests')}</div>
          </div>
        </div>
        <div className="td-stat">
          <div className="td-stat__icon"><BarChart3 size={16} /></div>
          <div className="td-stat__data">
            <div className="td-stat__value">{tenant.total_tokens.toLocaleString()}</div>
            <div className="td-stat__label">{t('admin.tenantDetail.tokens')}</div>
          </div>
        </div>
        <div className="td-stat">
          <div className="td-stat__icon"><Coins size={16} /></div>
          <div className="td-stat__data">
            <div className="td-stat__value">${formatCharge(tenant.total_charge_usd)}</div>
            <div className="td-stat__label">{t('admin.tenantDetail.charge')}</div>
          </div>
        </div>
        <div className="td-stat">
          <div className="td-stat__icon"><FileText size={16} /></div>
          <div className="td-stat__data">
            <div className="td-stat__value">{tenant.documents_count.toLocaleString()}</div>
            <div className="td-stat__label">{t('admin.tenantDetail.documents')}</div>
          </div>
        </div>
        <div className="td-stat">
          <div className="td-stat__icon"><MessageSquare size={16} /></div>
          <div className="td-stat__data">
            <div className="td-stat__value">{tenant.sessions_count.toLocaleString()}</div>
            <div className="td-stat__label">{t('admin.tenantDetail.chatSessions')}</div>
          </div>
        </div>
        <div className="td-stat">
          <div className="td-stat__icon"><Key size={16} /></div>
          <div className="td-stat__data">
            <div className="td-stat__value">{tenant.api_keys_count}</div>
            <div className="td-stat__label">{t('admin.tenantDetail.apiKeys')}</div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="td-tabs">
        <button
          className={`td-tab ${activeTab === 'overview' ? 'td-tab--active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <Shield size={14} />
          {t('admin.tenantDetail.access')}
        </button>
        <button
          className={`td-tab ${activeTab === 'content' ? 'td-tab--active' : ''}`}
          onClick={() => setActiveTab('content')}
        >
          <FileText size={14} />
          {t('admin.tenantDetail.content')}
        </button>
      </div>

      {/* Tab content */}
      <div className="td-tab-content">
        {activeTab === 'overview' && (
          <div className="td-section-grid">
            {/* Roles */}
            <div className="td-card">
              <h3 className="td-card__title">
                <Shield size={15} />
                {t('admin.tenantDetail.roles')}
              </h3>
              <div className="td-card__body">
                {rolesLoading ? (
                  <div className="td-card__loading">…</div>
                ) : (
                  <div className="td-role-list">
                    {allRoles.map(role => {
                      const isBase = role.slug === 'user'
                      const checked = assignedRoleIds.has(role.id)
                      return (
                        <label key={role.id} className={`td-role-item ${checked ? 'td-role-item--active' : ''}`}>
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={isBase}
                            onChange={() => handleToggleRole(role)}
                          />
                          <span className="td-role-item__name">{role.name}</span>
                          {isBase && <span className="td-role-item__tag">{t('admin.tenantDetail.rolesBase')}</span>}
                        </label>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Tier */}
            <div className="td-card">
              <h3 className="td-card__title">
                <Coins size={15} />
                {t('admin.tenantDetail.tier')}
              </h3>
              <div className="td-card__body">
                <select
                  className="td-tier-select"
                  value={tenant.tier}
                  onChange={e => handlePatch({ tier: e.target.value })}
                >
                  <option value="free">Free</option>
                  <option value="pro">Pro</option>
                  <option value="enterprise">Enterprise</option>
                </select>
              </div>
            </div>

            {/* Details */}
            <div className="td-card">
              <h3 className="td-card__title">
                <Mail size={15} />
                {t('admin.tenantDetail.profile')}
              </h3>
              <div className="td-card__body">
                <div className="td-detail-list">
                  <div className="td-detail-item">
                    <span className="td-detail-item__label">{t('admin.tenantDetail.name')}</span>
                    <span className="td-detail-item__value">{tenant.name || '—'}</span>
                  </div>
                  <div className="td-detail-item">
                    <span className="td-detail-item__label">{t('admin.tenantDetail.slug')}</span>
                    <span className="td-detail-item__value">{tenant.slug}</span>
                  </div>
                  <div className="td-detail-item">
                    <span className="td-detail-item__label">{t('admin.tenantDetail.created')}</span>
                    <span className="td-detail-item__value">{new Date(tenant.created_at).toLocaleString()}</span>
                  </div>
                  <div className="td-detail-item">
                    <span className="td-detail-item__label">{t('admin.tenantDetail.updated')}</span>
                    <span className="td-detail-item__value">{new Date(tenant.updated_at).toLocaleString()}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'content' && (
          <div className="td-content-section">
            <div className="td-content-cards">
              <button
                className="td-content-card"
                onClick={() => navigate(`/app/admin/documents?tenant_id=${tenant.id}`)}
              >
                <div className="td-content-card__icon td-content-card__icon--docs">
                  <FileText size={22} />
                </div>
                <div className="td-content-card__data">
                  <div className="td-content-card__count">{tenant.documents_count.toLocaleString()}</div>
                  <div className="td-content-card__label">{t('admin.tenantDetail.documents')}</div>
                </div>
                <div className="td-content-card__arrow">
                  <ArrowLeft size={14} style={{ transform: 'rotate(180deg)' }} />
                </div>
              </button>
              <button
                className="td-content-card"
                onClick={() => navigate(`/app/admin/chats?tenant_id=${tenant.id}`)}
              >
                <div className="td-content-card__icon td-content-card__icon--chats">
                  <MessageSquare size={22} />
                </div>
                <div className="td-content-card__data">
                  <div className="td-content-card__count">{tenant.sessions_count.toLocaleString()}</div>
                  <div className="td-content-card__label">{t('admin.tenantDetail.chatSessions')}</div>
                </div>
                <div className="td-content-card__arrow">
                  <ArrowLeft size={14} style={{ transform: 'rotate(180deg)' }} />
                </div>
              </button>
            </div>
          </div>
        )}
      </div>

      {showBlockConfirm && tenant && (
        <ConfirmDialog
          title={t('admin.tenants.confirmBlockTitle')}
          message={t('admin.tenants.confirmBlockMessage', { email: tenant.email })}
          confirmLabel={t('admin.tenants.block')}
          cancelLabel={t('admin.common.cancel')}
          variant="danger"
          onConfirm={confirmBlock}
          onCancel={() => setShowBlockConfirm(false)}
        />
      )}
    </div>
  )
}
