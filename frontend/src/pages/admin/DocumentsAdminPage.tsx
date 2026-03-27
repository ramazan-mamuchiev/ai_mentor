import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import {
  listDocumentsAdmin, patchDocumentAdmin, deleteDocumentAdmin,
  type AdminDocumentItem,
} from '../../api/admin'

function statusBadge(status: string) {
  const map: Record<string, string> = {
    ready: 'badge--green',
    pending: 'badge--yellow',
    processing: 'badge--blue',
    error: 'badge--red',
    blocked: 'badge--red',
  }
  return map[status] || 'badge--gray'
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function DocumentsAdminPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const [items, setItems] = useState<AdminDocumentItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)

  const tenantId = searchParams.get('tenant_id') || undefined
  const pageSize = 50

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listDocumentsAdmin({
        page, page_size: pageSize,
        search: search || undefined,
        status: statusFilter || undefined,
        tenant_id: tenantId,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch { /* ignore */ }
    setLoading(false)
  }, [page, search, statusFilter, tenantId])

  useEffect(() => { load() }, [load])

  const handleStatusChange = async (id: number, newStatus: string) => {
    try {
      await patchDocumentAdmin(id, { status: newStatus })
      load()
    } catch { /* ignore */ }
  }

  const handleDelete = async (id: number) => {
    if (!confirm(t('admin.docs.confirmDelete'))) return
    try {
      await deleteDocumentAdmin(id)
      load()
    } catch { /* ignore */ }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div>
      <div className="admin-page-header">
        <h1>{t('admin.docs.title')}</h1>
        <p>{t('admin.docs.count', { count: total })}{tenantId ? t('admin.docs.filteredByTenant') : ''}</p>
      </div>

      <div className="admin-table-wrapper">
        <div className="admin-toolbar">
          <input
            className="admin-search"
            placeholder={t('admin.docs.searchPlaceholder')}
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
          <select
            className="admin-select"
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); setPage(1) }}
          >
            <option value="">{t('admin.docs.allStatuses')}</option>
            <option value="ready">{t('admin.status.ready')}</option>
            <option value="pending">{t('admin.status.pending')}</option>
            <option value="processing">{t('admin.status.processing')}</option>
            <option value="error">{t('admin.status.error')}</option>
            <option value="blocked">{t('admin.status.blocked')}</option>
          </select>
          {tenantId && (
            <button
              className="admin-btn admin-btn--sm"
              onClick={() => { setSearchParams({}); setPage(1) }}
            >
              {t('admin.docs.clearTenantFilter')}
            </button>
          )}
        </div>

        {loading ? (
          <div className="admin-loading">{t('admin.common.loading')}</div>
        ) : items.length === 0 ? (
          <div className="admin-empty">{t('admin.docs.noDocuments')}</div>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>{t('admin.docs.title_col')}</th>
                <th>{t('admin.docs.tenant')}</th>
                <th>{t('admin.docs.product')}</th>
                <th>{t('admin.docs.status')}</th>
                <th>{t('admin.docs.format')}</th>
                <th>{t('admin.docs.size')}</th>
                <th>{t('admin.docs.chunks')}</th>
                <th>{t('admin.docs.uploaded')}</th>
                <th>{t('admin.common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map(d => (
                <tr key={d.id}>
                  <td>
                    <div style={{ maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {d.title || d.original_filename}
                    </div>
                  </td>
                  <td style={{ fontSize: 12 }}>{d.tenant_email || '—'}</td>
                  <td style={{ fontSize: 12 }}>
                    {d.manufacturer && d.product_name ? `${d.manufacturer} / ${d.product_name}` : d.product_name || '—'}
                  </td>
                  <td><span className={`badge ${statusBadge(d.status)}`}>{d.status}</span></td>
                  <td><span className="badge badge--gray">{d.format}</span></td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{formatBytes(d.file_size_bytes)}</td>
                  <td>{d.total_chunks}</td>
                  <td style={{ fontSize: 12 }}>{new Date(d.uploaded_at).toLocaleDateString()}</td>
                  <td>
                    <div className="admin-actions">
                      <select
                        className="admin-select"
                        value={d.status}
                        onChange={e => handleStatusChange(d.id, e.target.value)}
                        style={{ width: 100 }}
                      >
                        <option value="ready">ready</option>
                        <option value="pending">pending</option>
                        <option value="blocked">blocked</option>
                        <option value="error">error</option>
                      </select>
                      <button
                        className="admin-btn admin-btn--sm admin-btn--danger"
                        onClick={() => handleDelete(d.id)}
                      >
                        {t('admin.common.delete')}
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
