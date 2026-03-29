import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  ArrowLeft, MessageSquare, Search, X, AlertTriangle, ChevronRight, Clock,
  FileSearch, Bug, ChevronDown, Copy, Check, RefreshCw, Download, Radio, Loader2,
} from 'lucide-react'
import {
  listChatSessionsAdmin, getChatSessionAdmin, searchMessagesAdmin,
  type AdminChatSessionItem, type AdminChatSessionDetail, type AdminChatMessage, type AdminChatMessageSearchItem,
  type TenantSearchResult,
} from '../../api/admin'
import { MarkdownRenderer } from '../../components/MarkdownRenderer'
import { RightPanel } from '../../components/RightPanel'
import { TenantFilterCombo } from '../../components/TenantFilterCombo'
import { TIME_RANGES, timeRangeToISO, fmtTsShort, fmtDuration, fmtUsd, highlightSearch, downloadBlob, exportItemsJSON, exportItemsCSV } from '../../utils/auditUtils'
import type { SourceInfo, DebugInfo } from '../../types'

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

function ChatSessionRow({ item, search, onClick }: {
  item: AdminChatSessionItem
  search: string
  onClick: () => void
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  const title = item.title || t('admin.chats.untitled')

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(JSON.stringify(item, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const handleClick = () => {
    if (window.getSelection()?.toString()) return
    setExpanded(v => !v)
  }

  const details: [string, string][] = [
    ['session_id', item.id.slice(0, 8)],
    ['email', item.tenant_email || '—'],
    ['product', item.product_filter?.replace(/\n/g, ', ') || '—'],
    ['messages', String(item.messages_count)],
    ['total_tokens', item.total_tokens.toLocaleString()],
    ['duration', fmtDuration(item.total_duration_ms)],
    ['charge', fmtUsd(item.total_charge_usd)],
    ['created', fmtTsShort(item.created_at)],
    ['updated', fmtTsShort(item.updated_at)],
  ]

  return (
    <div className={`log-row${expanded ? ' log-row--expanded' : ''}`} onClick={handleClick}>
      <div className="log-row__header">
        <span className="log-row__expand">
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
        <span className="log-row__ts">{fmtTsShort(item.updated_at)}</span>
        <span className="log-row__level log-row__level--tenant">
          {item.tenant_email?.split('@')[0] || '—'}
        </span>
        <span className="log-row__summary">{highlightSearch(title, search)}</span>
        <span className="log-row__meta-pill">{item.messages_count} msg</span>
        {item.total_tokens > 0 && (
          <span className="log-row__meta-pill">{item.total_tokens.toLocaleString()} tok</span>
        )}
        <span className="log-row__meta-pill">{fmtUsd(item.total_charge_usd)}</span>
        {item.total_duration_ms > 0 && (
          <span className="log-row__meta-pill">{fmtDuration(item.total_duration_ms)}</span>
        )}
        <button className="log-row__copy" onClick={handleCopy} title="Copy JSON">
          {copied ? <Check size={12} /> : <Copy size={12} />}
        </button>
      </div>
      {expanded && (
        <div className="log-row__details">
          {details.map(([k, v]) => (
            <div className="log-row__field" key={k}>
              <span className="log-row__key">{k}</span>
              <span className="log-row__value">{v}</span>
            </div>
          ))}
          <div className="log-row__actions">
            <button className="admin-btn admin-btn--sm" onClick={e => { e.stopPropagation(); onClick() }}>
              <ChevronRight size={12} /> {t('admin.chats.openSession', { defaultValue: 'Open session' })}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function SessionDetail({ sessionId }: { sessionId: string }) {
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
    sessionId?: string
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

  const handleShowSources = useCallback((sources: SourceInfo[], sid?: string, mid?: number) => {
    setRightPanel({ mode: 'sources', sources, sessionId: sid, messageId: mid })
  }, [])

  const handleShowDebug = useCallback((debug: DebugInfo, sid?: string, mid?: number) => {
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
            <h1>{detail.title || detail.id.slice(0, 8)}</h1>
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
                      <span className="message-ids">S: {String(detail.id).slice(0, 8)} · M: {m.id}</span>
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
                      <span className="message-ids">S: {String(detail.id).slice(0, 8)} · M: {m.id}</span>
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
  const [msgResults, setMsgResults] = useState<AdminChatMessageSearchItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchMode, setSearchMode] = useState<'sessions' | 'messages'>('sessions')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const exportRef = useRef<HTMLDivElement>(null)

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

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(load, 5000)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [autoRefresh, load])

  useEffect(() => {
    if (!exportOpen) return
    const handler = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) setExportOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [exportOpen])

  const handleExport = useCallback((format: 'json' | 'csv') => {
    setExportOpen(false)
    setExporting(true)
    try {
      const date = new Date().toISOString().slice(0, 10)
      const base = `lexiro-chat-audit_${date}`
      if (format === 'json') {
        downloadBlob(exportItemsJSON(items), `${base}.json`, 'application/json')
      } else {
        const cols = ['id', 'tenant_email', 'title', 'messages_count', 'total_tokens', 'total_duration_ms', 'total_charge_usd', 'created_at', 'updated_at']
        downloadBlob(exportItemsCSV(items as unknown as Record<string, unknown>[], cols), `${base}.csv`, 'text/csv')
      }
    } finally {
      setExporting(false)
    }
  }, [items])

  const totalPages = Math.ceil(total / pageSize)

  const chatSummary = useMemo(() => {
    let messages = 0, tokens = 0, charge = 0, durationMs = 0
    for (const i of items) {
      messages += i.messages_count
      tokens += i.total_tokens
      charge += parseFloat(i.total_charge_usd) || 0
      durationMs += i.total_duration_ms
    }
    return { messages, tokens, charge, durationMs }
  }, [items])

  return (
    <div className="chat-audit-page">
      <div className="admin-page-header">
        <h1><MessageSquare size={20} /> {t('admin.chats.title')}</h1>
        <p>{t('admin.chats.sessionsCount', { count: total })}{activeTenantId ? t('admin.chats.filteredByTenant') : ''}</p>
      </div>

      <div className="logs-toolbar">
        <div className="logs-toolbar__row">
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

          <TenantFilterCombo
            value={tenantFilter}
            onChange={v => { setTenantFilter(v); setPage(1) }}
          />

          <div className="logs-search-wrap">
            <Search size={14} className="logs-search-wrap__icon" />
            <input
              className="logs-search"
              placeholder={searchMode === 'messages'
                ? t('admin.chats.searchMsgPlaceholder')
                : t('admin.chats.filterByTitle')}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button className="logs-search-wrap__clear" onClick={() => setSearch('')} aria-label="Clear">
                <X size={14} />
              </button>
            )}
          </div>

          <button className="logs-icon-btn" onClick={load}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
          <div className="logs-export-wrap" ref={exportRef}>
            <button
              className="logs-icon-btn"
              onClick={() => setExportOpen(v => !v)}
              disabled={exporting || items.length === 0}
            >
              {exporting ? <Loader2 size={14} className="spin" /> : <Download size={14} />}
            </button>
            {exportOpen && (
              <div className="logs-export-dropdown">
                <button className="logs-export-dropdown__item" onClick={() => handleExport('json')}>JSON</button>
                <button className="logs-export-dropdown__item" onClick={() => handleExport('csv')}>CSV</button>
              </div>
            )}
          </div>
          <button
            className={`logs-live-btn${autoRefresh ? ' logs-live-btn--active' : ''}`}
            onClick={() => setAutoRefresh(v => !v)}
          >
            <Radio size={13} />
            {t('admin.logs.live')}
          </button>
        </div>

        <div className="logs-toolbar__row">
          <div className="logs-level-chips" role="group" aria-label="Search mode">
            <button
              className={`logs-level-chip logs-level-chip--all${searchMode === 'sessions' ? ' logs-level-chip--active' : ''}`}
              onClick={() => { setSearchMode('sessions'); setMsgResults([]) }}
            >
              {t('admin.chats.sessionTitle')}
            </button>
            <button
              className={`logs-level-chip logs-level-chip--all${searchMode === 'messages' ? ' logs-level-chip--active' : ''}`}
              onClick={() => setSearchMode('messages')}
            >
              {t('admin.chats.content')}
            </button>
          </div>
          <div className="logs-summary-inline">
            <span className="logs-count">{total} {t('admin.chats.sessionsLabel', { defaultValue: 'sessions' })}</span>
            {items.length > 0 && !isMessageSearch && (
              <>
                <span className="logs-summary__metric">
                  <span className="logs-summary__label">msg</span>
                  <span className="logs-summary__value">{chatSummary.messages.toLocaleString()}</span>
                </span>
                <span className="logs-summary__metric">
                  <span className="logs-summary__label">tokens</span>
                  <span className="logs-summary__value">{chatSummary.tokens.toLocaleString()}</span>
                </span>
                <span className="logs-summary__metric">
                  <span className="logs-summary__label">charge</span>
                  <span className="logs-summary__value">{fmtUsd(chatSummary.charge)}</span>
                </span>
                <span className="logs-summary__metric">
                  <span className="logs-summary__label">duration</span>
                  <span className="logs-summary__value">{fmtDuration(chatSummary.durationMs)}</span>
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="chat-audit-error">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {loading ? (
        <div className="admin-loading">{t('admin.common.loading')}</div>
      ) : isMessageSearch && msgResults.length > 0 ? (
        <div className="log-viewer">
          {msgResults.map(m => (
            <div
              key={m.message_id}
              className="log-row"
              onClick={() => navigate(`/app/admin/chats/${m.session_id}`)}
              style={{ cursor: 'pointer' }}
            >
              <div className="log-row__header">
                <span className="log-row__expand"><ChevronRight size={12} /></span>
                <span className="log-row__ts">{fmtTsShort(m.created_at)}</span>
                <span className={`log-row__level log-row__level--${m.role === 'user' ? 'info' : 'debug'}`}>{m.role}</span>
                <span className="log-row__summary">{highlightSearch(m.content, debouncedSearch)}</span>
                <span className="log-row__meta-pill">{m.tenant_email?.split('@')[0] || '—'}</span>
                <span className="log-row__meta-pill">{m.session_id.slice(0, 8)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : isMessageSearch && msgResults.length === 0 && !error ? (
        <div className="admin-empty">{t('admin.chats.noSessions')}</div>
      ) : items.length === 0 && !error ? (
        <div className="admin-empty">{t('admin.chats.noSessions')}</div>
      ) : (
        <>
          <div className="log-viewer">
            {items.map(s => (
              <ChatSessionRow
                key={s.id}
                item={s}
                search={debouncedSearch}
                onClick={() => navigate(`/app/admin/chats/${s.id}`)}
              />
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
  if (id) return <SessionDetail sessionId={id} />
  return <SessionListView />
}
