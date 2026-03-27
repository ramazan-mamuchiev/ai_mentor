import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft } from 'lucide-react'
import {
  listChatSessionsAdmin, getChatSessionAdmin, searchMessagesAdmin,
  type AdminChatSessionItem, type AdminChatSessionDetail, type AdminChatMessageSearchItem,
} from '../../api/admin'

function SessionDetail({ sessionId }: { sessionId: number }) {
  const { t } = useTranslation()
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

  if (loading) return <div className="admin-loading">{t('admin.chats.loadingSession')}</div>
  if (!detail) return <div className="admin-empty">{t('admin.chats.sessionNotFound')}</div>

  return (
    <div>
      <button className="admin-sidebar-back" onClick={() => navigate('/app/admin/chats')}>
        <ArrowLeft size={14} /> {t('admin.chats.backToSessions')}
      </button>
      <div className="admin-page-header" style={{ marginTop: 12 }}>
        <h1>{detail.title || `#${detail.id}`}</h1>
        <p>
          {detail.tenant_email || t('admin.chats.unknownTenant')}
          {detail.product_filter ? ` · ${detail.product_filter}` : ''}
          {` · ${t('admin.chats.messagesCount', { count: detail.messages_count })}`}
        </p>
      </div>

      <div className="chat-viewer">
        {detail.messages.map(m => (
          <div key={m.id} className={`chat-viewer__msg chat-viewer__msg--${m.role}`}>
            {m.content}
            <div className="chat-viewer__meta">
              {m.role} · {new Date(m.created_at).toLocaleString()}
              {m.duration_ms ? ` · ${Math.round(m.duration_ms)}ms` : ''}
              {m.feedback ? ` · ${t('admin.chats.feedback')}: ${m.feedback}` : ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SessionListView() {
  const { t } = useTranslation()
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
        <h1>{t('admin.chats.title')}</h1>
        <p>
          {t('admin.chats.sessionsCount', { count: total })}
          {tenantId ? t('admin.chats.filteredByTenant') : ''}
        </p>
      </div>

      <div className="admin-table-wrapper" style={{ marginBottom: 16 }}>
        <div className="admin-toolbar">
          <input
            className="admin-search"
            placeholder={t('admin.chats.searchMsgPlaceholder')}
            value={msgSearch}
            onChange={e => setMsgSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleMsgSearch()}
          />
          <button className="admin-btn admin-btn--sm admin-btn--primary" onClick={handleMsgSearch}>
            {t('admin.chats.searchMessages')}
          </button>
        </div>
        {msgResults.length > 0 && (
          <table className="admin-table">
            <thead>
              <tr>
                <th>{t('admin.chats.role')}</th>
                <th>{t('admin.chats.content')}</th>
                <th>{t('admin.chats.tenant')}</th>
                <th>{t('admin.chats.session')}</th>
                <th>{t('admin.chats.date')}</th>
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
            placeholder={t('admin.chats.filterByTitle')}
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
        </div>

        {loading ? (
          <div className="admin-loading">{t('admin.common.loading')}</div>
        ) : items.length === 0 ? (
          <div className="admin-empty">{t('admin.chats.noSessions')}</div>
        ) : (
          <table className="admin-table">
            <thead>
              <tr>
                <th>{t('admin.chats.id')}</th>
                <th>{t('admin.chats.sessionTitle')}</th>
                <th>{t('admin.chats.tenant')}</th>
                <th>{t('admin.chats.product')}</th>
                <th>{t('admin.chats.messages')}</th>
                <th>{t('admin.chats.created')}</th>
                <th>{t('admin.chats.updated')}</th>
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
                    {s.title || t('admin.chats.untitled')}
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

export function ChatAuditPage() {
  const { id } = useParams<{ id: string }>()

  if (id) {
    return <SessionDetail sessionId={Number(id)} />
  }

  return <SessionListView />
}
