import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft } from 'lucide-react'
import { getTenant, patchTenant, type TenantDetail } from '../../api/admin'
import { useAuth } from '../../auth/AuthContext'
import { ConfirmDialog } from '../../components/ConfirmDialog'

export function TenantDetailPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [tenant, setTenant] = useState<TenantDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [showBlockConfirm, setShowBlockConfirm] = useState(false)

  const isSelf = id === user?.id

  useEffect(() => {
    if (!id) return
    setLoading(true)
    getTenant(id)
      .then(setTenant)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [id])

  const handlePatch = async (data: { role?: string; tier?: string; is_active?: boolean }) => {
    if (!id) return
    try {
      const updated = await patchTenant(id, data)
      setTenant(updated)
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

  return (
    <div>
      <div className="admin-page-header">
        <button className="admin-sidebar-back" onClick={() => navigate('/app/admin/tenants')}>
          <ArrowLeft size={14} /> {t('admin.tenantDetail.backToTenants')}
        </button>
        <h1>{tenant.email}</h1>
        <p>{t('admin.tenantDetail.details')}</p>
      </div>

      <div className="admin-detail-grid">
        <div className="admin-detail-card">
          <h3>{t('admin.tenantDetail.profile')}</h3>
          <dl>
            <div className="admin-detail-row"><dt>{t('admin.tenantDetail.name')}</dt><dd>{tenant.name || '—'}</dd></div>
            <div className="admin-detail-row"><dt>{t('admin.tenantDetail.slug')}</dt><dd>{tenant.slug}</dd></div>
            <div className="admin-detail-row"><dt>{t('admin.tenantDetail.emailVerified')}</dt><dd>{tenant.email_verified ? t('admin.tenantDetail.yes') : t('admin.tenantDetail.no')}</dd></div>
            <div className="admin-detail-row"><dt>{t('admin.tenantDetail.created')}</dt><dd>{new Date(tenant.created_at).toLocaleString()}</dd></div>
            <div className="admin-detail-row"><dt>{t('admin.tenantDetail.updated')}</dt><dd>{new Date(tenant.updated_at).toLocaleString()}</dd></div>
          </dl>
        </div>

        <div className="admin-detail-card">
          <h3>{t('admin.tenantDetail.access')}</h3>
          <dl>
            <div className="admin-detail-row">
              <dt>{t('admin.tenantDetail.role')}</dt>
              <dd>
                <select
                  className="admin-select"
                  value={tenant.role}
                  onChange={e => handlePatch({ role: e.target.value })}
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </dd>
            </div>
            <div className="admin-detail-row">
              <dt>{t('admin.tenantDetail.tier')}</dt>
              <dd>
                <select
                  className="admin-select"
                  value={tenant.tier}
                  onChange={e => handlePatch({ tier: e.target.value })}
                >
                  <option value="free">free</option>
                  <option value="pro">pro</option>
                  <option value="enterprise">enterprise</option>
                </select>
              </dd>
            </div>
            <div className="admin-detail-row">
              <dt>{t('admin.tenantDetail.status')}</dt>
              <dd>
                <button
                  className={`admin-btn admin-btn--sm ${tenant.is_active ? 'admin-btn--danger' : 'admin-btn--primary'}`}
                  onClick={handleToggleActive}
                  disabled={isSelf}
                  title={isSelf ? t('admin.tenants.cannotBlockSelf') : undefined}
                >
                  {tenant.is_active ? t('admin.tenants.block') : t('admin.tenants.unblock')}
                </button>
              </dd>
            </div>
            <div className="admin-detail-row"><dt>{t('admin.tenantDetail.apiKeys')}</dt><dd>{tenant.api_keys_count}</dd></div>
          </dl>
        </div>

        <div className="admin-detail-card">
          <h3>{t('admin.tenantDetail.usage30d')}</h3>
          <dl>
            <div className="admin-detail-row"><dt>{t('admin.tenantDetail.requests')}</dt><dd>{tenant.total_requests.toLocaleString()}</dd></div>
            <div className="admin-detail-row"><dt>{t('admin.tenantDetail.tokens')}</dt><dd>{tenant.total_tokens.toLocaleString()}</dd></div>
            <div className="admin-detail-row"><dt>{t('admin.tenantDetail.charge')}</dt><dd>${tenant.total_charge_usd}</dd></div>
          </dl>
        </div>

        <div className="admin-detail-card">
          <h3>{t('admin.tenantDetail.content')}</h3>
          <dl>
            <div className="admin-detail-row"><dt>{t('admin.tenantDetail.documents')}</dt><dd>{tenant.documents_count}</dd></div>
            <div className="admin-detail-row"><dt>{t('admin.tenantDetail.chatSessions')}</dt><dd>{tenant.sessions_count}</dd></div>
          </dl>
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <button
              className="admin-btn admin-btn--sm"
              onClick={() => navigate(`/app/admin/documents?tenant_id=${tenant.id}`)}
            >
              {t('admin.tenantDetail.viewDocuments')}
            </button>
            <button
              className="admin-btn admin-btn--sm"
              onClick={() => navigate(`/app/admin/chats?tenant_id=${tenant.id}`)}
            >
              {t('admin.tenantDetail.viewChats')}
            </button>
          </div>
        </div>
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
