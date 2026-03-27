import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { getTenant, patchTenant, type TenantDetail } from '../../api/admin'

export function TenantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [tenant, setTenant] = useState<TenantDetail | null>(null)
  const [loading, setLoading] = useState(true)

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

  if (loading) return <div className="admin-loading">Loading tenant...</div>
  if (!tenant) return <div className="admin-empty">Tenant not found</div>

  return (
    <div>
      <div className="admin-page-header">
        <button className="admin-sidebar-back" onClick={() => navigate('/app/admin/tenants')}>
          <ArrowLeft size={14} /> Back to tenants
        </button>
        <h1>{tenant.email}</h1>
        <p>Tenant details</p>
      </div>

      <div className="admin-detail-grid">
        <div className="admin-detail-card">
          <h3>Profile</h3>
          <dl>
            <div className="admin-detail-row"><dt>Name</dt><dd>{tenant.name || '—'}</dd></div>
            <div className="admin-detail-row"><dt>Slug</dt><dd>{tenant.slug}</dd></div>
            <div className="admin-detail-row"><dt>Email verified</dt><dd>{tenant.email_verified ? 'Yes' : 'No'}</dd></div>
            <div className="admin-detail-row"><dt>Created</dt><dd>{new Date(tenant.created_at).toLocaleString()}</dd></div>
            <div className="admin-detail-row"><dt>Updated</dt><dd>{new Date(tenant.updated_at).toLocaleString()}</dd></div>
          </dl>
        </div>

        <div className="admin-detail-card">
          <h3>Access</h3>
          <dl>
            <div className="admin-detail-row">
              <dt>Role</dt>
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
              <dt>Tier</dt>
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
              <dt>Status</dt>
              <dd>
                <button
                  className={`admin-btn admin-btn--sm ${tenant.is_active ? 'admin-btn--danger' : 'admin-btn--primary'}`}
                  onClick={() => handlePatch({ is_active: !tenant.is_active })}
                >
                  {tenant.is_active ? 'Block' : 'Unblock'}
                </button>
              </dd>
            </div>
            <div className="admin-detail-row"><dt>API Keys</dt><dd>{tenant.api_keys_count}</dd></div>
          </dl>
        </div>

        <div className="admin-detail-card">
          <h3>Usage (30d)</h3>
          <dl>
            <div className="admin-detail-row"><dt>Requests</dt><dd>{tenant.total_requests.toLocaleString()}</dd></div>
            <div className="admin-detail-row"><dt>Tokens</dt><dd>{tenant.total_tokens.toLocaleString()}</dd></div>
            <div className="admin-detail-row"><dt>Charge</dt><dd>${tenant.total_charge_usd}</dd></div>
          </dl>
        </div>

        <div className="admin-detail-card">
          <h3>Content</h3>
          <dl>
            <div className="admin-detail-row"><dt>Documents</dt><dd>{tenant.documents_count}</dd></div>
            <div className="admin-detail-row"><dt>Chat Sessions</dt><dd>{tenant.sessions_count}</dd></div>
          </dl>
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <button
              className="admin-btn admin-btn--sm"
              onClick={() => navigate(`/app/admin/documents?tenant_id=${tenant.id}`)}
            >
              View Documents
            </button>
            <button
              className="admin-btn admin-btn--sm"
              onClick={() => navigate(`/app/admin/chats?tenant_id=${tenant.id}`)}
            >
              View Chats
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
