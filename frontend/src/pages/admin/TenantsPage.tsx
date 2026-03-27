import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listTenants, patchTenant, type TenantListItem } from '../../api/admin'

export function TenantsPage() {
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

  const handleToggleActive = async (t: TenantListItem) => {
    try {
      await patchTenant(t.id, { is_active: !t.is_active })
      load()
    } catch { /* ignore */ }
  }

  const handleChangeRole = async (t: TenantListItem, newRole: string) => {
    try {
      await patchTenant(t.id, { role: newRole })
      load()
    } catch { /* ignore */ }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div>
      <div className="admin-page-header">
        <h1>Tenants</h1>
        <p>{total} total tenants</p>
      </div>

      <div className="admin-table-wrapper">
        <div className="admin-toolbar">
          <input
            className="admin-search"
            placeholder="Search by email or name..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
          <select className="admin-select" value={roleFilter} onChange={e => { setRoleFilter(e.target.value); setPage(1) }}>
            <option value="">All roles</option>
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>
        </div>

        {loading ? (
          <div className="admin-loading">Loading...</div>
        ) : items.length === 0 ? (
          <div className="admin-empty">No tenants found</div>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Name</th>
                <th>Role</th>
                <th>Tier</th>
                <th>Status</th>
                <th>Docs</th>
                <th>Sessions</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map(t => (
                <tr key={t.id} className="admin-table-clickable" onClick={() => navigate(`/app/admin/tenants/${t.id}`)}>
                  <td>{t.email}</td>
                  <td>{t.name || '—'}</td>
                  <td>
                    <span className={`badge ${t.role === 'admin' ? 'badge--blue' : 'badge--gray'}`}>
                      {t.role}
                    </span>
                  </td>
                  <td><span className="badge badge--gray">{t.tier}</span></td>
                  <td>
                    <span className={`badge ${t.is_active ? 'badge--green' : 'badge--red'}`}>
                      {t.is_active ? 'Active' : 'Blocked'}
                    </span>
                  </td>
                  <td>{t.documents_count}</td>
                  <td>{t.sessions_count}</td>
                  <td>{new Date(t.created_at).toLocaleDateString()}</td>
                  <td onClick={e => e.stopPropagation()}>
                    <div className="admin-actions">
                      <select
                        className="admin-select"
                        value={t.role}
                        onChange={e => handleChangeRole(t, e.target.value)}
                        style={{ width: 80 }}
                      >
                        <option value="user">user</option>
                        <option value="admin">admin</option>
                      </select>
                      <button
                        className={`admin-btn admin-btn--sm ${t.is_active ? 'admin-btn--danger' : 'admin-btn--primary'}`}
                        onClick={() => handleToggleActive(t)}
                      >
                        {t.is_active ? 'Block' : 'Unblock'}
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
            <span>Page {page} of {totalPages}</span>
            <div className="admin-pagination-buttons">
              <button className="admin-btn admin-btn--sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</button>
              <button className="admin-btn admin-btn--sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
