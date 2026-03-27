import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ArrowLeft, MessageSquare, Search, X, AlertTriangle, ChevronRight, Clock, User,
  FileSearch, Bug,
} from 'lucide-react'
import {
  listChatSessionsAdmin, getChatSessionAdmin, searchMessagesAdmin, searchTenants,
  type AdminChatSessionItem, type AdminChatSessionDetail, type AdminChatMessage, type AdminChatMessageSearchItem,
  type TenantSearchResult,
} from '../../api/admin'
import { MarkdownRenderer } from '../../components/MarkdownRenderer'
import { RightPanel } from '../../components/RightPanel'
import type { SourceInfo, DebugInfo } from '../../types'

const TIME_RANGES = [
  { value: '', label: 'All' },
  { value: '24h', label: '24h' },
  { value: '7d', label: '7d' },
  { value: '30d', label: '30d' },
  { value: '90d', label: '90d' },
] as const

function timeRangeToISO(range: string): { start?: string; end?: string } {
  if (!range) return {}
  const now = Date.now()
  const units: Record<string, number> = { h: 3_600_000, d: 86_400_000 }
  const match = range.match(/^(\d+)([hd])$/)
  if (!match) return {}
  const ms = parseInt(match[1]) * units[match[2]]
  return {
    start: new Date(now - ms).toISOString(),
    end: new Date(now).toISOString(),
  }
}

function toSourceInfos(sources: AdminChatMessage['sources']): SourceInfo[] {
  if (!sources || !Array.isArray(sources)) return []
  return sources.map(s => ({
    doc_title: s.doc_title || '',
    heading_path: s.heading_path || '',
    similarity: s.similarity || 0,
    content_preview: s.content_preview || '',
    product_name: s.product_name || '',
    firmware_version: '',
    document_id: s.document_id ?? null,
  }))
}

function SessionDetail({ sessionId }: { sessionId: number }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<AdminChatSessionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [rightPanel, setRightPanel] = useState<{
    mode: 'sources' | 'debug'
    sources?: SourceInfo[]
    debug?: DebugInfo
    sessionId?: number
    messageId?: number
  } | null>(null)

  useEffect(() => {
    setLoading(true)
    setError('')
    getChatSessionAdmin(sessionId)
      .then(setDetail)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [sessionId])

  const handleShowSources = useCallback((sources: SourceInfo[], sid?: number, mid?: number) => {
    setRightPanel({ mode: 'sources', sources, sessionId: sid, messageId: mid })
  }, [])

  const handleShowDebug = useCallback((debug: DebugInfo, sid?: number, mid?: number) => {
    setRightPanel({ mode: 'debug', debug, sessionId: sid, messageId: mid })
  }, [])

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

  const fmtTime = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: 'numeric' })
      + ', ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  return (
    <div className="audit-detail-layout">
      <div className="main-area">
        <div className="main-area-chat">
          <div className="audit-detail-header">
          <button className="chat-audit-back" onClick={() => navigate('/app/admin/chats')}>
            <ArrowLeft size={14} /> {t('admin.chats.backToSessions')}
          </button>
          <div className="admin-page-header" style={{ marginTop: 8 }}>
            <h1>{detail.title || `#${detail.id}`}</h1>
            <p>
              {detail.tenant_email || t('admin.chats.unknownTenant')}
              {detail.product_filter ? ` · ${detail.product_filter}` : ''}
              {` · ${t('admin.chats.messagesCount', { count: detail.messages_count })}`}
            </p>
          </div>
        </div>

        <div className="messages-container">
          {detail.messages.map(m => {
            const sources = toSourceInfos(m.sources)
            const debug = m.debug as DebugInfo | null
            const isAssistant = m.role === 'assistant'

            return (
              <div key={m.id} className={`message ${m.role}`}>
                <div className="message-body">
                  <div className="message-content">
                    {m.role === 'user' ? m.content : <MarkdownRenderer content={m.content} />}
                  </div>
                  {isAssistant && sources.length > 0 && (
                    <div className="sources-container">
                      <button
                        className="sources-toggle"
                        onClick={() => handleShowSources(sources, detail.id, m.id)}
                      >
                        <FileSearch size={16} />
                        <span className="sources-label">{t('chat.sources', { count: sources.length })}</span>
                      </button>
                    </div>
                  )}
                  {isAssistant && (
                    <div className="message-footer">
                      <span className="audit-meta-role">{m.role}</span>
                      <span className="audit-meta-sep">·</span>
                      <span className="audit-meta-time">{fmtTime(m.created_at)}</span>
                      {m.duration_ms != null && (
                        <>
                          <span className="audit-meta-sep">·</span>
                          <span className="message-duration">{(m.duration_ms / 1000).toFixed(1)}s</span>
                        </>
                      )}
                      <span className="audit-meta-sep">·</span>
                      <span className="message-ids">S#{detail.id} M#{m.id}</span>
                      {m.feedback && (
                        <>
                          <span className="audit-meta-sep">·</span>
                          <span className="audit-feedback-badge">{m.feedback === 'up' ? '👍' : '👎'}</span>
                        </>
                      )}
                      {debug && (
                        <div className="message-footer-actions">
                          <button
                            className="message-action-btn debug-toggle"
                            onClick={() => handleShowDebug(debug, detail.id, m.id)}
                            data-tooltip={t('chat.debug')}
                          >
                            <Bug size={12} />
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                  {m.role === 'user' && (
                    <div className="message-footer">
                      <span className="audit-meta-role">{m.role}</span>
                      <span className="audit-meta-sep">·</span>
                      <span className="audit-meta-time">{fmtTime(m.created_at)}</span>
                      <span className="audit-meta-sep">·</span>
                      <span className="message-ids">S#{detail.id} M#{m.id}</span>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {rightPanel && (
        <RightPanel
          content={
            rightPanel.mode === 'sources'
              ? { mode: 'sources', sources: rightPanel.sources! }
              : { mode: 'debug', debug: rightPanel.debug! }
          }
          sessionId={rightPanel.sessionId}
          messageId={rightPanel.messageId}
          onClose={() => setRightPanel(null)}
        />
      )}
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
  const [timeRange, setTimeRange] = useState('')
  const [tenantFilter, setTenantFilter] = useState<TenantSearchResult | null>(null)
  const [tenantQuery, setTenantQuery] = useState('')
  const [tenantOptions, setTenantOptions] = useState<TenantSearchResult[]>([])
  const [tenantDropdownOpen, setTenantDropdownOpen] = useState(false)
  const tenantDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const tenantWrapRef = useRef<HTMLDivElement>(null)
  const [msgResults, setMsgResults] = useState<AdminChatMessageSearchItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchMode, setSearchMode] = useState<'sessions' | 'messages'>('sessions')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const tenantIdFromUrl = searchParams.get('tenant_id') || undefined
  const activeTenantId = tenantFilter?.id || tenantIdFromUrl
  const pageSize = 50

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 400)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [search])

  useEffect(() => {
    if (tenantDebounceRef.current) clearTimeout(tenantDebounceRef.current)
    if (!tenantQuery || tenantQuery.length < 1) { setTenantOptions([]); return }
    tenantDebounceRef.current = setTimeout(async () => {
      try {
        const results = await searchTenants(tenantQuery)
        setTenantOptions(results)
        setTenantDropdownOpen(true)
      } catch { setTenantOptions([]) }
    }, 300)
    return () => { if (tenantDebounceRef.current) clearTimeout(tenantDebounceRef.current) }
  }, [tenantQuery])

  useEffect(() => {
    if (!tenantDropdownOpen) return
    const handler = (e: MouseEvent) => {
      if (tenantWrapRef.current && !tenantWrapRef.current.contains(e.target as Node)) {
        setTenantDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [tenantDropdownOpen])

  const isMessageSearch = searchMode === 'messages' && !!debouncedSearch.trim()

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      if (isMessageSearch) {
        const res = await searchMessagesAdmin(debouncedSearch)
        setMsgResults(res.items)
        setItems([])
        setTotal(res.total)
      } else {
        const { start, end } = timeRangeToISO(timeRange)
        const res = await listChatSessionsAdmin({
          page, page_size: pageSize,
          search: debouncedSearch || undefined,
          tenant_id: activeTenantId,
          created_after: start,
          created_before: end,
        })
        setItems(res.items)
        setTotal(res.total)
        setMsgResults([])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    }
    setLoading(false)
  }, [page, debouncedSearch, activeTenantId, isMessageSearch, timeRange])

  useEffect(() => { load() }, [load])

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="chat-audit-page">
      <div className="admin-page-header">
        <h1><MessageSquare size={20} /> {t('admin.chats.title')}</h1>
        <p>{t('admin.chats.sessionsCount', { count: total })}{activeTenantId ? t('admin.chats.filteredByTenant') : ''}</p>
      </div>

      {/* Toolbar row 1: search + mode */}
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

      {/* Toolbar row 2: time range + tenant filter */}
      <div className="chat-audit-toolbar chat-audit-toolbar--filters">
        <div className="logs-chips" role="group" aria-label="Time range">
          <Clock size={13} className="logs-chips__icon" />
          {TIME_RANGES.map(r => (
            <button
              key={r.value}
              className={`logs-chip${timeRange === r.value ? ' logs-chip--active' : ''}`}
              onClick={() => { setTimeRange(r.value); setPage(1) }}
            >
              {r.label}
            </button>
          ))}
        </div>

        {/* Tenant autocomplete combo — same as Logs */}
        <div className="logs-tenant-combo" ref={tenantWrapRef}>
          {tenantFilter ? (
            <div className="logs-tenant-chip">
              <User size={12} />
              <span className="logs-tenant-chip__name">{tenantFilter.name}</span>
              <button
                className="logs-tenant-chip__clear"
                onClick={() => { setTenantFilter(null); setTenantQuery(''); setPage(1) }}
                aria-label="Clear"
              >
                <X size={12} />
              </button>
            </div>
          ) : (
            <>
              <User size={13} className="logs-tenant-combo__icon" />
              <input
                className="logs-tenant-input"
                placeholder={t('admin.logs.tenantPlaceholder', { defaultValue: 'User...' })}
                value={tenantQuery}
                onChange={e => setTenantQuery(e.target.value)}
                onFocus={() => { if (tenantOptions.length) setTenantDropdownOpen(true) }}
              />
              {tenantQuery && (
                <button className="logs-tenant-combo__clear" onClick={() => { setTenantQuery(''); setTenantOptions([]); setTenantDropdownOpen(false) }}>
                  <X size={12} />
                </button>
              )}
            </>
          )}
          {tenantDropdownOpen && tenantOptions.length > 0 && (
            <div className="logs-tenant-dropdown">
              {tenantOptions.map(opt => (
                <button
                  key={opt.id}
                  className="logs-tenant-dropdown__item"
                  onClick={() => {
                    setTenantFilter(opt)
                    setTenantQuery('')
                    setTenantDropdownOpen(false)
                    setPage(1)
                  }}
                >
                  <span className="logs-tenant-dropdown__name">{opt.name}</span>
                  <span className="logs-tenant-dropdown__email">{opt.email}</span>
                </button>
              ))}
            </div>
          )}
          {tenantDropdownOpen && tenantQuery && tenantOptions.length === 0 && (
            <div className="logs-tenant-dropdown">
              <div className="logs-tenant-dropdown__empty">{t('admin.logs.noTenantsFound', { defaultValue: 'No users found' })}</div>
            </div>
          )}
        </div>

        <span className="logs-count">{total} {t('admin.chats.sessionsLabel', { defaultValue: 'sessions' })}</span>
      </div>

      {/* Error */}
      {error && (
        <div className="chat-audit-error">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {/* Results */}
      {loading ? (
        <div className="admin-loading">{t('admin.common.loading')}</div>
      ) : isMessageSearch && msgResults.length > 0 ? (
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
      ) : isMessageSearch && msgResults.length === 0 && !error ? (
        <div className="admin-empty">{t('admin.chats.noSessions')}</div>
      ) : items.length === 0 && !error ? (
        <div className="admin-empty">{t('admin.chats.noSessions')}</div>
      ) : (
        <>
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
    </div>
  )
}

export function ChatAuditPage() {
  const { id } = useParams<{ id: string }>()
  if (id) return <SessionDetail sessionId={Number(id)} />
  return <SessionListView />
}
