import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Ban, MoreHorizontal, ShieldCheck, Trash2, Unlock, Users } from 'lucide-react'
import { deleteTenant, listTenants, patchTenant, type TenantListItem } from '../../api/admin'
import { useAuth } from '../../auth/AuthContext'
import { ConfirmDialog } from '../../components/ConfirmDialog'

function TenantActions({
  tenant,
  isSelf,
  onChangeRole,
  onToggleActive,
  onDelete,
}: {
  tenant: TenantListItem
  isSelf: boolean
  onChangeRole: (role: string) => void
  onToggleActive: () => void
  onDelete?: () => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const dropRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: -9999, left: -9999 })

  useEffect(() => {
    if (!open) return
    const onMouseDown = (e: MouseEvent) => {
      if (dropRef.current && !dropRef.current.contains(e.target as Node) &&
          btnRef.current && !btnRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    const onScroll = () => setOpen(false)
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKey)
    document.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('scroll', onScroll, true)
    }
  }, [open])

  useEffect(() => {
    if (!open || !dropRef.current || !btnRef.current) return
    const rect = btnRef.current.getBoundingClientRect()
    const dropRect = dropRef.current.getBoundingClientRect()
    const dropW = dropRect.width || 220
    const dropH = dropRect.height
    let left = rect.right - dropW
    if (left < 8) left = 8
    if (left + dropW > window.innerWidth - 8) left = window.innerWidth - dropW - 8
    const top = (rect.bottom + 4 + dropH > window.innerHeight)
      ? rect.top - dropH - 4
      : rect.bottom + 4
    setPos({ top, left })
  }, [open])

  return (
    <div className="docs-actions">
      <button
        ref={btnRef}
        className="docs-action-btn"
        onClick={() => {
          if (!open) setPos({ top: -9999, left: -9999 })
          setOpen(v => !v)
        }}
      >
        <MoreHorizontal size={16} />
      </button>
      {open && createPortal(
        <div ref={dropRef} className="docs-actions-dropdown" style={{ top: pos.top, left: pos.left }}>
          {tenant.role !== 'admin' && (
            <button className="docs-actions-dropdown-item" onClick={() => { onChangeRole('admin'); setOpen(false) }}>
              <ShieldCheck size={15} />
              {t('admin.tenants.makeAdmin')}
            </button>
          )}
          {tenant.role !== 'user' && (
            <button className="docs-actions-dropdown-item" onClick={() => { onChangeRole('user'); setOpen(false) }}>
              <Users size={15} />
              {t('admin.tenants.makeUser')}
            </button>
          )}
          {!isSelf && (
            <button
              className={`docs-actions-dropdown-item ${tenant.is_active ? 'docs-actions-dropdown-item--danger' : ''}`}
              onClick={() => { onToggleActive(); setOpen(false) }}
            >
              {tenant.is_active ? <Ban size={15} /> : <Unlock size={15} />}
              {tenant.is_active ? t('admin.tenants.block') : t('admin.tenants.unblock')}
            </button>
          )}
          {onDelete && !isSelf && (
            <button className="docs-actions-dropdown-item docs-actions-dropdown-item--danger" onClick={() => { onDelete(); setOpen(false) }}>
              <Trash2 size={15} />
              {t('admin.tenants.delete')}
            </button>
          )}
        </div>,
        document.body
      )}
    </div>
  )
}

export function TenantsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [items, setItems] = useState<TenantListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [blockTarget, setBlockTarget] = useState<TenantListItem | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<TenantListItem | null>(null)

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

  const handleToggleActive = (tenant: TenantListItem) => {
    if (tenant.is_active) {
      setBlockTarget(tenant)
    } else {
      confirmToggleActive(tenant)
    }
  }

  const confirmToggleActive = async (tenant: TenantListItem) => {
    try {
      await patchTenant(tenant.id, { is_active: !tenant.is_active })
      load()
    } catch { /* ignore */ }
    setBlockTarget(null)
  }

  const confirmDeleteTenant = async (tenant: TenantListItem) => {
    try {
      await deleteTenant(tenant.id)
      load()
    } catch { /* ignore */ }
    setDeleteTarget(null)
  }

  const handleChangeRole = async (tenant: TenantListItem, newRole: string) => {
    try {
      await patchTenant(tenant.id, { role: newRole })
      load()
    } catch { /* ignore */ }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h1><Users size={20} /> {t('admin.tenants.title')}</h1>
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
          <div className="admin-table-scroll">
            <table className="admin-table admin-table--wide">
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
              {[...items].sort((a, b) => a.email.localeCompare(b.email)).map(tenant => (
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
                    <span className={`badge ${!tenant.is_active ? 'badge--red' : tenant.email_verified ? 'badge--green' : 'badge--yellow'}`}>
                      {!tenant.is_active ? t('admin.tenants.blocked') : tenant.email_verified ? t('admin.tenants.active') : t('admin.tenants.unverified')}
                    </span>
                  </td>
                  <td>{tenant.documents_count}</td>
                  <td>{tenant.sessions_count}</td>
                  <td>{new Date(tenant.created_at).toLocaleDateString()}</td>
                  <td onClick={e => e.stopPropagation()}>
                    <TenantActions
                      tenant={tenant}
                      isSelf={tenant.id === user?.id}
                      onChangeRole={role => handleChangeRole(tenant, role)}
                      onToggleActive={() => handleToggleActive(tenant)}
                      onDelete={!tenant.email_verified ? () => setDeleteTarget(tenant) : undefined}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
            </table>
          </div>
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

      {blockTarget && (
        <ConfirmDialog
          title={t('admin.tenants.confirmBlockTitle')}
          message={t('admin.tenants.confirmBlockMessage', { email: blockTarget.email })}
          confirmLabel={t('admin.tenants.block')}
          cancelLabel={t('admin.common.cancel')}
          variant="danger"
          onConfirm={() => confirmToggleActive(blockTarget)}
          onCancel={() => setBlockTarget(null)}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title={t('admin.tenants.confirmDeleteTitle')}
          message={t('admin.tenants.confirmDeleteMessage', { email: deleteTarget.email })}
          confirmLabel={t('admin.tenants.delete')}
          cancelLabel={t('admin.common.cancel')}
          variant="danger"
          onConfirm={() => confirmDeleteTenant(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}
