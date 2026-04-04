import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ListTodo, RefreshCw, Radio, ShieldAlert, AlertTriangle,
  XCircle, RotateCcw, Clock, Loader, CheckCircle2,
  Globe, FileText, Activity, Github, Link, Layers,
  Trash2,
} from 'lucide-react'
import {
  listTasks, listWorkers, cancelTask, retryTask, rescueStaleTasks, bulkCancelTasks,
  type TaskItem, type TaskListResponse, type WorkerInfo,
} from '../../api/admin'

function fmtRuntime(sec: number | null): string {
  if (sec == null) return '—'
  if (sec < 60) return `${Math.round(sec)}s`
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  if (m < 60) return `${m}m ${s.toString().padStart(2, '0')}s`
  const h = Math.floor(m / 60)
  return `${h}h ${(m % 60).toString().padStart(2, '0')}m`
}

function fmtTime(date: Date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffH = diffMs / 3600000

  if (diffH < 24) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  if (diffH < 48) {
    return 'вчера ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString([], { day: 'numeric', month: 'short' }) +
    ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'active': return 'badge--blue'
    case 'reserved': return 'badge--gray'
    case 'pending': return 'badge--yellow'
    case 'processing': return 'badge--blue'
    case 'stale': return 'badge--red'
    case 'error': return 'badge--red'
    default: return 'badge--gray'
  }
}

const TASK_ICONS: Record<string, typeof Globe> = {
  'Site Crawl': Globe,
  'Confluence': Layers,
  'URL': Link,
  'GitHub': Github,
  'Document': FileText,
  'Reindex': RefreshCw,
  'Lifecycle': Activity,
  'Lifecycle Merge': Activity,
  'Delete Product': Trash2,
  'Archive': FileText,
  'Archive (S3)': FileText,
  'RAG Eval': Activity,
}

function TaskIcon({ name }: { name: string }) {
  const Icon = TASK_ICONS[name] || FileText
  return <Icon size={14} />
}

function HealthDot({ status }: { status: string }) {
  const cls = status === 'online' ? 'health-dot--ok' : 'health-dot--err'
  return <span className={`health-dot ${cls}`} />
}

interface Toast {
  id: number
  message: string
  type: 'success' | 'error'
}

export function TaskQueuePage() {
  const { t } = useTranslation()
  const [data, setData] = useState<TaskListResponse | null>(null)
  const [workers, setWorkers] = useState<WorkerInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const [statusFilter, setStatusFilter] = useState('')
  const [taskFilter, setTaskFilter] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 50

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [toasts, setToasts] = useState<Toast[]>([])
  const [confirmAction, setConfirmAction] = useState<{
    title: string
    message: string
    onConfirm: () => void
  } | null>(null)

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const toastIdRef = useRef(0)

  const addToast = useCallback((message: string, type: 'success' | 'error' = 'success') => {
    const id = ++toastIdRef.current
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3000)
  }, [])

  const fetchData = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true)
    try {
      const [tasksRes, workersRes] = await Promise.all([
        listTasks({
          status: statusFilter || undefined,
          task_name: taskFilter || undefined,
          search: search || undefined,
          page,
          page_size: pageSize,
        }),
        listWorkers(),
      ])
      setData(tasksRes)
      setWorkers(workersRes.workers)
      setLastUpdated(new Date())
    } catch {
      // keep old data
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [statusFilter, taskFilter, search, page])

  useEffect(() => { fetchData() }, [fetchData])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(() => fetchData(), 10000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [autoRefresh, fetchData])

  const handleCancel = useCallback(async (taskId: string) => {
    try {
      await cancelTask(taskId)
      addToast(t('admin.tasks.cancelledOk'))
      fetchData()
    } catch {
      addToast(t('admin.tasks.cancelFailed'), 'error')
    }
  }, [fetchData, addToast, t])

  const handleRetry = useCallback(async (docId: number) => {
    try {
      await retryTask(docId)
      addToast(t('admin.tasks.retryOk'))
      fetchData()
    } catch {
      addToast(t('admin.tasks.retryFailed'), 'error')
    }
  }, [fetchData, addToast, t])

  const handleRescue = useCallback(async () => {
    try {
      const res = await rescueStaleTasks()
      addToast(t('admin.tasks.rescueOk', { docs: res.rescued_documents, jobs: res.rescued_reindex_jobs }))
      fetchData()
    } catch {
      addToast(t('admin.tasks.rescueFailed'), 'error')
    }
  }, [fetchData, addToast, t])

  const handleBulkCancel = useCallback(() => {
    const ids = Array.from(selected)
    if (ids.length === 0) return
    setConfirmAction({
      title: t('admin.tasks.bulkCancelTitle'),
      message: t('admin.tasks.bulkCancelMsg', { count: ids.length }),
      onConfirm: async () => {
        setConfirmAction(null)
        try {
          const res = await bulkCancelTasks({ task_ids: ids })
          addToast(t('admin.tasks.bulkCancelOk', { count: res.cancelled }))
          setSelected(new Set())
          fetchData()
        } catch {
          addToast(t('admin.tasks.bulkCancelFailed'), 'error')
        }
      },
    })
  }, [selected, fetchData, addToast, t])

  const toggleSelect = (taskId: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(taskId)) next.delete(taskId)
      else next.add(taskId)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (!data) return
    const allIds = data.items.filter(i => i.task_id).map(i => i.task_id!)
    if (selected.size === allIds.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(allIds))
    }
  }

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0
  const workersOnline = workers.filter(w => w.status === 'online').length
  const workersOffline = workers.length === 0

  return (
    <div className="admin-page tq-page">
      {/* Header */}
      <div className="admin-page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1><ListTodo size={20} /> {t('admin.tasks.title')}</h1>
          <p>{lastUpdated ? t('admin.tasks.updatedAt', { time: fmtTime(lastUpdated) }) : t('admin.tasks.subtitle')}</p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button
            className="admin-btn admin-btn--sm"
            onClick={handleRescue}
            title={t('admin.tasks.rescueHint')}
          >
            <ShieldAlert size={14} />
            {t('admin.tasks.rescue')}
          </button>
          <button
            className={`logs-live-btn${autoRefresh ? ' logs-live-btn--active' : ''}`}
            onClick={() => setAutoRefresh(v => !v)}
          >
            <Radio size={13} />
            {t('admin.tasks.live')}
          </button>
          <button
            className="admin-btn admin-btn--sm"
            onClick={() => fetchData(true)}
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
            {t('admin.tasks.refresh')}
          </button>
        </div>
      </div>

      {/* Workers offline alert */}
      {workersOffline && (
        <div className="tq-alert tq-alert--warning">
          <AlertTriangle size={16} />
          <span>{t('admin.tasks.workersOffline')}</span>
        </div>
      )}

      {/* Summary + Workers bar */}
      <div className="system-status-bar">
        <div className="tq-summary-section">
          <span className={`system-badge ${(data?.active_count || 0) > 0 ? 'system-badge--accent' : 'system-badge--muted'}`}>
            <Loader size={12} /> {t('admin.tasks.active')}: {data?.active_count || 0}
          </span>
          <span className={`system-badge ${(data?.pending_count || 0) > 0 ? 'system-badge--warning' : 'system-badge--muted'}`}>
            <Clock size={12} /> {t('admin.tasks.pending')}: {data?.pending_count || 0}
          </span>
          <span className={`system-badge ${(data?.stale_count || 0) > 0 ? 'system-badge--danger' : 'system-badge--muted'}`}>
            <AlertTriangle size={12} /> {t('admin.tasks.stale')}: {data?.stale_count || 0}
          </span>
          <span className={`system-badge ${(data?.error_count || 0) > 0 ? 'system-badge--danger' : 'system-badge--muted'}`}>
            <XCircle size={12} /> {t('admin.tasks.errors')}: {data?.error_count || 0}
          </span>
        </div>
        <div className="tq-workers-section">
          {workers.length > 0 ? workers.map((w, i) => (
            <div key={i} className="tq-worker-pill">
              <HealthDot status={w.status} />
              <span className="tq-worker-name">{w.name}</span>
              <span className="tq-worker-count">{w.active_tasks}</span>
            </div>
          )) : (
            <div className="tq-worker-pill">
              <HealthDot status="offline" />
              <span className="tq-worker-name" style={{ color: 'var(--text-muted)' }}>
                {t('admin.tasks.noWorkers')}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Toolbar */}
      <div className="admin-table-wrapper">
        <div className="admin-toolbar">
          <input
            className="admin-search"
            placeholder={t('admin.tasks.searchPlaceholder')}
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
          <select
            className="admin-select"
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); setPage(1) }}
          >
            <option value="">{t('admin.tasks.allStatuses')}</option>
            <option value="active">{t('admin.tasks.statusActive')}</option>
            <option value="pending">{t('admin.tasks.statusPending')}</option>
            <option value="reserved">{t('admin.tasks.statusReserved')}</option>
            <option value="stale">{t('admin.tasks.statusStale')}</option>
            <option value="error">{t('admin.tasks.statusError')}</option>
          </select>
          <select
            className="admin-select"
            value={taskFilter}
            onChange={e => { setTaskFilter(e.target.value); setPage(1) }}
          >
            <option value="">{t('admin.tasks.allTypes')}</option>
            <option value="Site Crawl">Site Crawl</option>
            <option value="Confluence">Confluence</option>
            <option value="Document">Document</option>
            <option value="Reindex">Reindex</option>
            <option value="Lifecycle">Lifecycle</option>
            <option value="GitHub">GitHub</option>
            <option value="URL">URL</option>
          </select>
          <div style={{ flex: 1 }} />
          {selected.size > 0 && (
            <button
              className="admin-btn admin-btn--sm admin-btn--danger"
              onClick={handleBulkCancel}
            >
              <XCircle size={14} />
              {t('admin.tasks.cancelSelected', { count: selected.size })}
            </button>
          )}
        </div>

        {/* Table or Empty State */}
        {!data || data.items.length === 0 ? (
          <div className="tq-empty">
            <CheckCircle2 size={48} strokeWidth={1} className="tq-empty-icon" />
            <p className="tq-empty-title">{t('admin.tasks.allClear')}</p>
            <p className="tq-empty-hint">{t('admin.tasks.allClearHint')}</p>
          </div>
        ) : (
          <div className="admin-table-scroll">
            <table className="admin-table admin-table--wide tq-table">
              <thead>
                <tr>
                  <th style={{ width: 32 }}>
                    <input
                      type="checkbox"
                      checked={selected.size > 0 && selected.size === data.items.filter(i => i.task_id).length}
                      onChange={toggleSelectAll}
                    />
                  </th>
                  <th>{t('admin.tasks.col.status')}</th>
                  <th>{t('admin.tasks.col.task')}</th>
                  <th>{t('admin.tasks.col.target')}</th>
                  <th>{t('admin.tasks.col.progress')}</th>
                  <th>{t('admin.tasks.col.created')}</th>
                  <th>{t('admin.tasks.col.worker')}</th>
                  <th>{t('admin.tasks.col.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item, i) => (
                  <tr
                    key={item.task_id || `${item.source}-${item.document_id}-${i}`}
                    className={
                      item.status === 'stale' ? 'tq-row--stale' :
                      item.status === 'error' ? 'tq-row--error' :
                      item.status === 'active' ? 'tq-row--active' : ''
                    }
                  >
                    <td>
                      {item.task_id && (
                        <input
                          type="checkbox"
                          checked={selected.has(item.task_id)}
                          onChange={() => toggleSelect(item.task_id!)}
                        />
                      )}
                    </td>
                    <td>
                      <span className={`badge ${statusBadgeClass(item.status)}`}>
                        {item.status}
                      </span>
                    </td>
                    <td>
                      <div className="tq-task-cell">
                        <TaskIcon name={item.task_name} />
                        <span>{item.task_name}</span>
                      </div>
                    </td>
                    <td>
                      <div className="tq-target-cell">
                        <span className="tq-target-title">
                          {item.document_title || item.args_summary || '—'}
                        </span>
                        {item.tenant_email && (
                          <span className="tq-target-sub">{item.tenant_email}</span>
                        )}
                        {!item.tenant_email && item.product_name && (
                          <span className="tq-target-sub">{item.product_name}</span>
                        )}
                      </div>
                    </td>
                    <td>
                      {item.progress_percent != null ? (
                        <div className="tq-progress">
                          <div className="tq-progress-track">
                            <div
                              className="tq-progress-fill"
                              style={{ width: `${Math.min(item.progress_percent, 100)}%` }}
                            />
                          </div>
                          <span className="tq-progress-pct">{item.progress_percent}%</span>
                          {item.progress_stage && (
                            <span className="tq-progress-stage">{item.progress_stage}</span>
                          )}
                        </div>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>—</span>
                      )}
                    </td>
                    <td>
                      <div className="tq-created-cell">
                        <span className="mono" style={{ fontSize: 12 }}>
                          {fmtDate(item.created_at)}
                        </span>
                        {item.status === 'active' && item.runtime_sec != null && (
                          <span className="tq-runtime-sub">{fmtRuntime(item.runtime_sec)}</span>
                        )}
                      </div>
                    </td>
                    <td>
                      {item.worker ? (
                        <span className="mono" style={{ fontSize: 12 }}>{item.worker}</span>
                      ) : item.status === 'reserved' ? (
                        <span style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: 12 }}>
                          {t('admin.tasks.queued')}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>—</span>
                      )}
                    </td>
                    <td>
                      <div className="tq-actions">
                        {item.task_id && item.status !== 'error' && (
                          <button
                            className="tq-action-btn tq-action-btn--cancel"
                            onClick={() => handleCancel(item.task_id!)}
                            title={t('admin.tasks.cancelOne')}
                          >
                            <XCircle size={15} />
                          </button>
                        )}
                        {item.document_id && (item.status === 'error' || item.status === 'stale' || item.status === 'cancelled') && (
                          <button
                            className="tq-action-btn tq-action-btn--retry"
                            onClick={() => handleRetry(item.document_id!)}
                            title={t('admin.tasks.retryOne')}
                          >
                            <RotateCcw size={15} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
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
      </div>

      {/* Confirmation Dialog */}
      {confirmAction && (
        <div className="tq-overlay" onClick={() => setConfirmAction(null)}>
          <div className="tq-confirm" onClick={e => e.stopPropagation()}>
            <div className="tq-confirm-icon">
              <AlertTriangle size={32} />
            </div>
            <h3>{confirmAction.title}</h3>
            <p>{confirmAction.message}</p>
            <div className="tq-confirm-actions">
              <button className="admin-btn admin-btn--sm" onClick={() => setConfirmAction(null)}>
                {t('admin.tasks.confirmCancel')}
              </button>
              <button className="admin-btn admin-btn--sm admin-btn--danger" onClick={confirmAction.onConfirm}>
                {t('admin.tasks.confirmOk')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toasts */}
      {toasts.length > 0 && (
        <div className="tq-toasts">
          {toasts.map(toast => (
            <div key={toast.id} className={`tq-toast tq-toast--${toast.type}`}>
              {toast.type === 'success' ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
              <span>{toast.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
