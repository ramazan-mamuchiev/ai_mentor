import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import {
  listChatSessionsAdmin, getChatSessionAdmin, searchMessagesAdmin,
  type AdminChatSessionItem, type AdminChatSessionDetail, type AdminChatMessageSearchItem,
} from '../../api/admin'

function SessionDetail({ sessionId }: { sessionId: number }) {
  const navigate = useNavigate()
  const [detail, setDetail] = useState<AdminChatSessionDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getChatSessionAdmin(sessionId)
      .then(setDetail)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) return <div className="admin-loading">Loading session...</div>
  if (!detail) return <div className="admin-empty">Session not found</div>

  return (
    <div>
      <button className="admin-sidebar-back" onClick={() => navigate('/app/admin/chats')}>
        <ArrowLeft size={14} /> Back to sessions
      </button>
      <div className="admin-page-header" style={{ marginTop: 12 }}>
        <h1>{detail.title || `Session #${detail.id}`}</h1>
        <p>
          {detail.tenant_email || 'Unknown tenant'}
          {detail.product_filter ? ` · ${detail.product_filter}` : ''}
          {` · ${detail.messages_count} messages`}
        </p>
      </div>

      <div className="chat-viewer">
        {detail.messages.map(m => (
          <div key={m.id} className={`chat-viewer__msg chat-viewer__msg--${m.role}`}>
            {m.content}
            <div className="chat-viewer__meta">
              {m.role} · {new Date(m.created_at).toLocaleString()}
              {m.duration_ms ? ` · ${Math.round(m.duration_ms)}ms` : ''}
              {m.feedback ? ` · feedback: ${m.feedback}` : ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SessionListView() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [items, setItems] = useState<AdminChatSessionItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [msgSearch, setMsgSearch] = useState('')
  const [msgResults, setMsgResults] = useState<AdminChatMessageSearchItem[]>([])
  const [loading, setLoading] = useState(true)

  const tenantId = searchParams.get('tenant_id') || undefined
  const pageSize = 50

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listChatSessionsAdmin({
        page, page_size: pageSize,
        search: search || undefined,
        tenant_id: tenantId,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch { /* ignore */ }
    setLoading(false)
  }, [page, search, tenantId])

  useEffect(() => { load() }, [load])

  const handleMsgSearch = async () => {
    if (!msgSearch.trim()) return
    try {
      const res = await searchMessagesAdmin(msgSearch)
      setMsgResults(res.items)
    } catch { /* ignore */ }
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div>
      <div className="admin-page-header">
        <h1>Chat Audit</h1>
        <p>{total} sessions{tenantId ? ' (filtered by tenant)' : ''}</p>
      </div>

      <div className="admin-table-wrapper" style={{ marginBottom: 16 }}>
        <div className="admin-toolbar">
          <input
            className="admin-search"
            placeholder="Search message content..."
            value={msgSearch}
            onChange={e => setMsgSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleMsgSearch()}
          />
          <button className="admin-btn admin-btn--sm admin-btn--primary" onClick={handleMsgSearch}>
            Search Messages
          </button>
        </div>
        {msgResults.length > 0 && (
          <table className="admin-table">
            <thead>
              <tr>
                <th>Role</th>
                <th>Content</th>
                <th>Tenant</th>
                <th>Session</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {msgResults.map(m => (
                <tr
                  key={m.message_id}
                  className="admin-table-clickable"
                  onClick={() => navigate(`/app/admin/chats/${m.session_id}`)}
                >
                  <td><span className={`badge ${m.role === 'user' ? 'badge--blue' : 'badge--gray'}`}>{m.role}</span></td>
                  <td style={{ maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {m.content}
                  </td>
                  <td style={{ fontSize: 12 }}>{m.tenant_email || '—'}</td>
                  <td>#{m.session_id}</td>
                  <td style={{ fontSize: 12 }}>{new Date(m.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="admin-table-wrapper">
        <div className="admin-toolbar">
          <input
            className="admin-search"
            placeholder="Filter sessions by title..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
        </div>

        {loading ? (
          <div className="admin-loading">Loading...</div>
        ) : items.length === 0 ? (
          <div className="admin-empty">No sessions found</div>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Tenant</th>
                <th>Product</th>
                <th>Messages</th>
                <th>Created</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {items.map(s => (
                <tr
                  key={s.id}
                  className="admin-table-clickable"
                  onClick={() => navigate(`/app/admin/chats/${s.id}`)}
                >
                  <td>#{s.id}</td>
                  <td style={{ maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.title || '(untitled)'}
                  </td>
                  <td style={{ fontSize: 12 }}>{s.tenant_email || '—'}</td>
                  <td style={{ fontSize: 12 }}>{s.product_filter || '—'}</td>
                  <td>{s.messages_count}</td>
                  <td style={{ fontSize: 12 }}>{new Date(s.created_at).toLocaleDateString()}</td>
                  <td style={{ fontSize: 12 }}>{new Date(s.updated_at).toLocaleDateString()}</td>
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

export function ChatAuditPage() {
  const { id } = useParams<{ id: string }>()

  if (id) {
    return <SessionDetail sessionId={Number(id)} />
  }

  return <SessionListView />
}
