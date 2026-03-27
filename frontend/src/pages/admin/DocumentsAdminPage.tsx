import { useCallback, useEffect, useState } from 'react'
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
    if (!confirm('Delete this document and all its chunks?')) return
    try {
      await deleteDocumentAdmin(id)
      load()
    } catch { /* ignore */ }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div>
      <div className="admin-page-header">
        <h1>Documents</h1>
        <p>{total} documents{tenantId ? ' (filtered by tenant)' : ''}</p>
      </div>

      <div className="admin-table-wrapper">
        <div className="admin-toolbar">
          <input
            className="admin-search"
            placeholder="Search by title or filename..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
          <select
            className="admin-select"
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); setPage(1) }}
          >
            <option value="">All statuses</option>
            <option value="ready">Ready</option>
            <option value="pending">Pending</option>
            <option value="processing">Processing</option>
            <option value="error">Error</option>
            <option value="blocked">Blocked</option>
          </select>
          {tenantId && (
            <button
              className="admin-btn admin-btn--sm"
              onClick={() => { setSearchParams({}); setPage(1) }}
            >
              Clear tenant filter
            </button>
          )}
        </div>

        {loading ? (
          <div className="admin-loading">Loading...</div>
        ) : items.length === 0 ? (
          <div className="admin-empty">No documents found</div>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Tenant</th>
                <th>Product</th>
                <th>Status</th>
                <th>Format</th>
                <th>Size</th>
                <th>Chunks</th>
                <th>Uploaded</th>
                <th>Actions</th>
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
                        Delete
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
