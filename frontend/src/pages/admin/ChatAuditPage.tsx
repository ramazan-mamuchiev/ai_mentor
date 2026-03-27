import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ArrowLeft, MessageSquare, Search, X, AlertTriangle, ChevronRight,
} from 'lucide-react'
import {
  listChatSessionsAdmin, getChatSessionAdmin, searchMessagesAdmin,
  type AdminChatSessionItem, type AdminChatSessionDetail, type AdminChatMessageSearchItem,
} from '../../api/admin'

function SessionDetail({ sessionId }: { sessionId: number }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<AdminChatSessionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setError('')
    getChatSessionAdmin(sessionId)
      .then(setDetail)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) return <div className="admin-loading">{t('admin.chats.loadingSession')}</div>
  if (error) return (
    <div>
      <button className="chat-audit-back" onClick={() => navigate('/app/admin/chats')}>
        <ArrowLeft size={14} /> {t('admin.chats.backToSessions')}
      </button>
      <div className="chat-audit-error"><AlertTriangle size={14} /> {error}</div>
    </div>
  )
  if (!detail) return <div className="admin-empty">{t('admin.chats.sessionNotFound')}</div>

  return (
    <div>
      <button className="chat-audit-back" onClick={() => navigate('/app/admin/chats')}>
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
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [msgResults, setMsgResults] = useState<AdminChatMessageSearchItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchMode, setSearchMode] = useState<'sessions' | 'messages'>('sessions')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const tenantId = searchParams.get('tenant_id') || undefined
  const pageSize = 50

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 400)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [search])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      if (searchMode === 'messages' && debouncedSearch.trim()) {
        const res = await searchMessagesAdmin(debouncedSearch)
        setMsgResults(res.items)
        setItems([])
        setTotal(res.total)
      } else {
        const res = await listChatSessionsAdmin({
          page, page_size: pageSize,
          search: debouncedSearch || undefined,
          tenant_id: tenantId,
        })
        setItems(res.items)
        setTotal(res.total)
        setMsgResults([])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    }
    setLoading(false)
  }, [page, debouncedSearch, tenantId, searchMode])

  useEffect(() => { load() }, [load])

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="chat-audit-page">
      <div className="admin-page-header">
        <h1><MessageSquare size={20} /> {t('admin.chats.title')}</h1>
        <p>{t('admin.chats.sessionsCount', { count: total })}{tenantId ? t('admin.chats.filteredByTenant') : ''}</p>
      </div>

      {/* Unified search toolbar */}
      <div className="chat-audit-toolbar">
        <div className="chat-audit-search-wrap">
          <Search size={14} className="chat-audit-search-wrap__icon" />
          <input
            className="chat-audit-search"
            placeholder={searchMode === 'messages'
              ? t('admin.chats.searchMsgPlaceholder')
              : t('admin.chats.filterByTitle')}
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          {search && (
            <button className="chat-audit-search-wrap__clear" onClick={() => setSearch('')} aria-label="Clear">
              <X size={14} />
            </button>
          )}
        </div>
        <div className="chat-audit-mode-chips">
          <button
            className={`chat-audit-mode-chip${searchMode === 'sessions' ? ' chat-audit-mode-chip--active' : ''}`}
            onClick={() => { setSearchMode('sessions'); setMsgResults([]) }}
          >
            {t('admin.chats.sessionTitle')}
          </button>
          <button
            className={`chat-audit-mode-chip${searchMode === 'messages' ? ' chat-audit-mode-chip--active' : ''}`}
            onClick={() => setSearchMode('messages')}
          >
            {t('admin.chats.content')}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="chat-audit-error">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {/* Message search results */}
      {searchMode === 'messages' && msgResults.length > 0 && !loading && (
        <div className="chat-audit-results">
          {msgResults.map(m => (
            <div
              key={m.message_id}
              className="chat-audit-msg-row"
              onClick={() => navigate(`/app/admin/chats/${m.session_id}`)}
            >
              <div className="chat-audit-msg-row__header">
                <span className={`badge ${m.role === 'user' ? 'badge--blue' : 'badge--gray'}`}>{m.role}</span>
                <span className="chat-audit-msg-row__tenant">{m.tenant_email || '—'}</span>
                <span className="chat-audit-msg-row__session">#{m.session_id}</span>
                <span className="chat-audit-msg-row__date">{new Date(m.created_at).toLocaleDateString()}</span>
                <ChevronRight size={14} className="chat-audit-msg-row__arrow" />
              </div>
              <div className="chat-audit-msg-row__content">{m.content}</div>
            </div>
          ))}
        </div>
      )}

      {/* Session list */}
      {searchMode === 'sessions' && (
        <>
          {loading ? (
            <div className="admin-loading">{t('admin.common.loading')}</div>
          ) : items.length === 0 && !error ? (
            <div className="admin-empty">{t('admin.chats.noSessions')}</div>
          ) : (
            <div className="chat-audit-results">
              {items.map(s => (
                <div
                  key={s.id}
                  className="chat-audit-session-row"
                  onClick={() => navigate(`/app/admin/chats/${s.id}`)}
                >
                  <div className="chat-audit-session-row__main">
                    <span className="chat-audit-session-row__id">#{s.id}</span>
                    <span className="chat-audit-session-row__title">
                      {s.title || t('admin.chats.untitled')}
                    </span>
                    <ChevronRight size={14} className="chat-audit-session-row__arrow" />
                  </div>
                  <div className="chat-audit-session-row__meta">
                    <span>{s.tenant_email || '—'}</span>
                    {s.product_filter && <span>· {s.product_filter}</span>}
                    <span>· {s.messages_count} {t('admin.chats.messages').toLowerCase()}</span>
                    <span>· {new Date(s.updated_at).toLocaleDateString()}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {totalPages > 1 && (
            <div className="admin-pagination">
              <span>{t('admin.common.page', { page, total: totalPages })}</span>
              <div className="admin-pagination-buttons">
                <button className="admin-btn admin-btn--sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                  {t('admin.common.prev')}
                </button>
                <button className="admin-btn admin-btn--sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                  {t('admin.common.next')}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Messages loading */}
      {searchMode === 'messages' && loading && (
        <div className="admin-loading">{t('admin.common.loading')}</div>
      )}
      {searchMode === 'messages' && !loading && msgResults.length === 0 && debouncedSearch && !error && (
        <div className="admin-empty">{t('admin.chats.noSessions')}</div>
      )}
    </div>
  )
}

export function ChatAuditPage() {
  const { id } = useParams<{ id: string }>()
  if (id) return <SessionDetail sessionId={Number(id)} />
  return <SessionListView />
}
