import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { listTenants, patchTenant, type TenantListItem } from '../../api/admin'

export function TenantsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [items, setItems] = useState<TenantListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [loading, setLoading] = useState(true)

  const pageSize = 50

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listTenants({
        page, page_size: pageSize, search: search || undefined,
        role: roleFilter || undefined,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch { /* ignore */ }
    setLoading(false)
  }, [page, search, roleFilter])

  useEffect(() => { load() }, [load])

  const handleToggleActive = async (tenant: TenantListItem) => {
    try {
      await patchTenant(tenant.id, { is_active: !tenant.is_active })
      load()
    } catch { /* ignore */ }
  }

  const handleChangeRole = async (tenant: TenantListItem, newRole: string) => {
    try {
      await patchTenant(tenant.id, { role: newRole })
      load()
    } catch { /* ignore */ }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div>
      <div className="admin-page-header">
        <h1>{t('admin.tenants.title')}</h1>
        <p>{t('admin.tenants.totalCount', { count: total })}</p>
      </div>

      <div className="admin-table-wrapper">
        <div className="admin-toolbar">
          <input
            className="admin-search"
            placeholder={t('admin.tenants.searchPlaceholder')}
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
          <select className="admin-select" value={roleFilter} onChange={e => { setRoleFilter(e.target.value); setPage(1) }}>
            <option value="">{t('admin.tenants.allRoles')}</option>
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>
        </div>

        {loading ? (
          <div className="admin-loading">{t('admin.common.loading')}</div>
        ) : items.length === 0 ? (
          <div className="admin-empty">{t('admin.tenants.noTenants')}</div>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>{t('admin.tenants.email')}</th>
                <th>{t('admin.tenants.name')}</th>
                <th>{t('admin.tenants.role')}</th>
                <th>{t('admin.tenants.tier')}</th>
                <th>{t('admin.tenants.status')}</th>
                <th>{t('admin.tenants.docs')}</th>
                <th>{t('admin.tenants.sessions')}</th>
                <th>{t('admin.tenants.created')}</th>
                <th>{t('admin.common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map(tenant => (
                <tr key={tenant.id} className="admin-table-clickable" onClick={() => navigate(`/app/admin/tenants/${tenant.id}`)}>
                  <td>{tenant.email}</td>
                  <td>{tenant.name || '—'}</td>
                  <td>
                    <span className={`badge ${tenant.role === 'admin' ? 'badge--blue' : 'badge--gray'}`}>
                      {tenant.role}
                    </span>
                  </td>
                  <td><span className="badge badge--gray">{tenant.tier}</span></td>
                  <td>
                    <span className={`badge ${tenant.is_active ? 'badge--green' : 'badge--red'}`}>
                      {tenant.is_active ? t('admin.tenants.active') : t('admin.tenants.blocked')}
                    </span>
                  </td>
                  <td>{tenant.documents_count}</td>
                  <td>{tenant.sessions_count}</td>
                  <td>{new Date(tenant.created_at).toLocaleDateString()}</td>
                  <td onClick={e => e.stopPropagation()}>
                    <div className="admin-actions">
                      <select
                        className="admin-select"
                        value={tenant.role}
                        onChange={e => handleChangeRole(tenant, e.target.value)}
                        style={{ width: 80 }}
                      >
                        <option value="user">user</option>
                        <option value="admin">admin</option>
                      </select>
                      <button
                        className={`admin-btn admin-btn--sm ${tenant.is_active ? 'admin-btn--danger' : 'admin-btn--primary'}`}
                        onClick={() => handleToggleActive(tenant)}
                      >
                        {tenant.is_active ? t('admin.tenants.block') : t('admin.tenants.unblock')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {totalPages > 1 && (
          <div className="admin-pagination">
            <span>{t('admin.common.page', { page, total: totalPages })}</span>
            <div className="admin-pagination-buttons">
              <button className="admin-btn admin-btn--sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>{t('admin.common.prev')}</button>
              <button className="admin-btn admin-btn--sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>{t('admin.common.next')}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
