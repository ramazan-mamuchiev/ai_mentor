import { useEffect, useState, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity, RefreshCw, Database, HardDrive, Cpu, Server, Layers,
  Clock, Loader, AlertTriangle, Zap, MessageSquare, Users, Radio,
  Trash2, CheckCircle, XCircle, Play, ChevronDown, ChevronRight,
} from 'lucide-react'
import {
  getSystemInfo, type SystemInfo,
  getVacuumStatus, runVacuumFull, runVacuumAll,
  type VacuumTableInfo, type VacuumHistoryItem,
} from '../../api/admin'
import { SYSTEM_REFRESH_INTERVAL } from './constants'
import { ConfirmDialog } from '../../components/ConfirmDialog'

function fmtBytes(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`
  return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function fmtUptime(sec: number) {
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function fmtTime(date: Date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function progressColor(pct: number) {
  if (pct >= 90) return 'var(--danger, #ef4444)'
  if (pct >= 70) return 'var(--warning, #f59e0b)'
  return 'var(--success, #22c55e)'
}

function ProgressBar({ pct, label, sub }: { pct: number; label: string; sub: string }) {
  return (
    <div className="system-progress-card">
      <div className="system-progress-header">
        <span className="system-progress-label">{label}</span>
        <span className="system-progress-value">{pct.toFixed(1)}%</span>
      </div>
      <div className="system-progress-track">
        <div
          className="system-progress-fill"
          style={{ width: `${Math.min(pct, 100)}%`, background: progressColor(pct) }}
        />
      </div>
      <span className="system-progress-sub">{sub}</span>
    </div>
  )
}

function InlineProgress({ pct, sub }: { pct: number; sub: string }) {
  return (
    <div className="system-inline-progress">
      <div className="system-progress-track">
        <div
          className="system-progress-fill"
          style={{ width: `${Math.min(pct, 100)}%`, background: progressColor(pct) }}
        />
      </div>
      <span className="system-progress-sub">{sub}</span>
    </div>
  )
}

function HealthDot({ status }: { status: string }) {
  const cls = status === 'ok' ? 'health-dot--ok'
    : status === 'degraded' ? 'health-dot--warn'
      : 'health-dot--err'
  return <span className={`health-dot ${cls}`} />
}

function HorizBar({ items }: { items: Array<{ label: string; pct: number; sub: string }> }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {items.map((it, i) => (
        <div key={i}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 2 }}>
            <span>{it.label}</span>
            <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{it.sub}</span>
          </div>
          <div style={{ height: 6, borderRadius: 3, background: 'var(--border)' }}>
            <div style={{ height: '100%', borderRadius: 3, width: `${Math.min(it.pct, 100)}%`, background: 'var(--accent)' }} />
          </div>
        </div>
      ))}
    </div>
  )
}

interface VacuumGroup {
  key: string
  items: VacuumHistoryItem[]
  startedAt: Date
  isMulti: boolean
  totalFreed: number
  totalDuration: number
  status: string
  hasError: boolean
}

function groupVacuumHistory(history: VacuumHistoryItem[]): VacuumGroup[] {
  const groups: VacuumGroup[] = []
  const used = new Set<number>()

  for (let i = 0; i < history.length; i++) {
    if (used.has(history[i].id)) continue
    const anchor = new Date(history[i].started_at).getTime()
    const items = [history[i]]
    used.add(history[i].id)

    for (let j = i + 1; j < history.length; j++) {
      if (used.has(history[j].id)) continue
      const t = new Date(history[j].started_at).getTime()
      if (Math.abs(t - anchor) < 3000) {
        items.push(history[j])
        used.add(history[j].id)
      }
    }

    const totalFreed = items.reduce((sum, h) => {
      if (h.size_before_bytes != null && h.size_after_bytes != null)
        return sum + Math.max(0, h.size_before_bytes - h.size_after_bytes)
      return sum
    }, 0)
    const totalDuration = items.reduce((sum, h) => sum + (h.duration_ms ?? 0), 0)
    const hasError = items.some(h => h.status === 'error')
    const hasPending = items.some(h => h.status === 'pending')
    const hasRunning = items.some(h => h.status === 'running')
    const allDone = items.every(h => h.status === 'completed')
    const status = hasRunning ? 'running' : hasPending ? 'pending' : hasError ? 'error' : allDone ? 'completed' : 'completed'

    groups.push({
      key: `${items[0].id}`,
      items,
      startedAt: new Date(history[i].started_at),
      isMulti: items.length > 1,
      totalFreed,
      totalDuration,
      status,
      hasError,
    })
  }
  return groups
}

function VacuumHistoryGrouped({ history, expandedGroup, onToggle }: {
  history: VacuumHistoryItem[]
  expandedGroup: number | null
  onToggle: (idx: number) => void
}) {
  const groups = groupVacuumHistory(history)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
      {groups.slice(0, 8).map((g, idx) => {
        const expanded = expandedGroup === idx
        const StatusIcon = g.status === 'completed' ? CheckCircle
          : g.status === 'error' ? XCircle
          : g.status === 'running' ? Loader
          : Clock
        const iconColor = g.status === 'completed' ? 'var(--success, #22c55e)'
          : g.status === 'error' ? 'var(--danger, #ef4444)'
          : g.status === 'running' ? 'var(--accent)'
          : 'var(--text-muted)'
        const label = g.isMulti
          ? `VACUUM ALL (${g.items.length})`
          : g.items[0].table_name

        return (
          <div key={g.key}>
            <div
              style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, cursor: g.isMulti ? 'pointer' : 'default' }}
              onClick={() => g.isMulti && onToggle(idx)}
            >
              <StatusIcon size={14} style={{ color: iconColor, flexShrink: 0 }} className={g.status === 'running' ? 'spin' : ''} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
                  <span style={{ fontWeight: 500 }}>{label}</span>
                  {g.status === 'completed' && (
                    <span style={{ color: 'var(--text-muted)' }}>{(g.totalDuration / 1000).toFixed(1)}s</span>
                  )}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                  {g.startedAt.toLocaleString()}
                </div>
                {g.status === 'completed' && g.totalFreed > 0 && (
                  <div style={{ fontSize: 11, color: 'var(--success, #22c55e)', fontWeight: 500 }}>
                    −{fmtBytes(g.totalFreed)}
                  </div>
                )}
                {g.hasError && !g.isMulti && g.items[0].error_message && (
                  <div style={{ fontSize: 11, color: 'var(--danger, #ef4444)' }} title={g.items[0].error_message}>
                    {g.items[0].error_message.slice(0, 80)}
                  </div>
                )}
              </div>
              {g.isMulti && (
                expanded
                  ? <ChevronDown size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                  : <ChevronRight size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
              )}
            </div>

            {g.isMulti && expanded && (
              <div style={{ marginLeft: 22, marginTop: 4, display: 'flex', flexDirection: 'column', gap: 4, borderLeft: '2px solid var(--border)', paddingLeft: 8 }}>
                {g.items.map(h => (
                  <div key={h.id} style={{ fontSize: 11, display: 'flex', gap: 6, alignItems: 'baseline' }}>
                    {h.status === 'completed' && <CheckCircle size={11} style={{ color: 'var(--success, #22c55e)' }} />}
                    {h.status === 'error' && <XCircle size={11} style={{ color: 'var(--danger, #ef4444)' }} />}
                    {h.status === 'running' && <Loader size={11} className="spin" style={{ color: 'var(--accent)' }} />}
                    {h.status === 'pending' && <Clock size={11} style={{ color: 'var(--text-muted)' }} />}
                    <span style={{ fontFamily: 'var(--font-mono)' }}>{h.table_name}</span>
                    {h.status === 'completed' && h.duration_ms != null && (
                      <span style={{ color: 'var(--text-muted)' }}>{(h.duration_ms / 1000).toFixed(1)}s</span>
                    )}
                    {h.status === 'completed' && h.size_before_bytes != null && h.size_after_bytes != null && h.size_before_bytes > h.size_after_bytes && (
                      <span style={{ color: 'var(--success, #22c55e)' }}>
                        −{fmtBytes(h.size_before_bytes - h.size_after_bytes)}
                      </span>
                    )}
                    {h.status === 'error' && h.error_message && (
                      <span style={{ color: 'var(--danger, #ef4444)' }}>{h.error_message.slice(0, 50)}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function VacuumCard() {
  const { t } = useTranslation()
  const [tables, setTables] = useState<VacuumTableInfo[]>([])
  const [history, setHistory] = useState<VacuumHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [runningTable, setRunningTable] = useState<string | null>(null)
  const [confirmTable, setConfirmTable] = useState<string | null>(null)
  const [confirmAll, setConfirmAll] = useState(false)
  const [expandedGroup, setExpandedGroup] = useState<number | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getVacuumStatus()
      setTables(data.tables)
      setHistory(data.history)

      const hasRunning = data.history.some(h => h.status === 'running' || h.status === 'pending')
      if (!hasRunning && pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
        setRunningTable(null)
      }
    } catch { /* keep old data */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    fetchStatus()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [fetchStatus])

  const handleConfirmedRun = async () => {
    const tableName = confirmTable
    setConfirmTable(null)
    if (!tableName || runningTable) return
    try {
      setRunningTable(tableName)
      await runVacuumFull(tableName)
      await fetchStatus()
      pollRef.current = setInterval(fetchStatus, 3000)
    } catch {
      setRunningTable(null)
    }
  }

  const handleConfirmedRunAll = async () => {
    setConfirmAll(false)
    if (runningTable) return
    try {
      setRunningTable('__all__')
      await runVacuumAll()
      await fetchStatus()
      pollRef.current = setInterval(fetchStatus, 3000)
    } catch {
      setRunningTable(null)
    }
  }

  if (loading) return null

  const lastRun = history.find(h => h.status !== 'running')
  const isRunning = !!runningTable || history.some(h => h.status === 'running' || h.status === 'pending')

  const totalSize = tables.reduce((s, t) => s + t.size_bytes, 0)
  const totalDead = tables.reduce((s, t) => s + t.dead_tuples, 0)
  const maxSize = Math.max(...tables.map(t => t.size_bytes), 1)

  return (
    <>
    <div className="system-two-cols">
      {/* Left: tables with bars */}
      <div className="admin-card">
        <div className="system-card-header">
          <h3 className="system-card-title"><Trash2 size={16} /> {t('admin.system.vacuumTitle')}</h3>
          <span className="system-card-hero">{fmtBytes(totalSize)}</span>
        </div>

        <div className="system-kv-list">
          <div className="system-kv">
            <span>{t('admin.system.vacuumDeadTuples')}</span>
            <strong className={totalDead > 1000 ? 'system-val--warn' : ''}>{totalDead.toLocaleString()}</strong>
          </div>
        </div>

        <button
          className="admin-btn admin-btn--sm"
          disabled={isRunning}
          onClick={() => setConfirmAll(true)}
          style={{ marginTop: 8, width: '100%' }}
        >
          {isRunning && runningTable === '__all__'
            ? <><Loader size={12} className="spin" /> {t('admin.system.vacuumRunning')}</>
            : <><Play size={12} /> {t('admin.system.vacuumAll')}</>
          }
        </button>

        {isRunning && (
          <div className="system-badges" style={{ marginTop: 8 }}>
            <span className="system-badge system-badge--accent">
              <Loader size={12} className="spin" /> {t('admin.system.vacuumRunning')}
            </span>
          </div>
        )}

        <div className="system-kv-divider" />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {tables.map(tbl => {
            const bloatPct = tbl.live_tuples > 0
              ? (tbl.dead_tuples / (tbl.live_tuples + tbl.dead_tuples)) * 100
              : 0
            const tblRunning = runningTable === tbl.name || history.some(h => h.table_name === tbl.name && (h.status === 'running' || h.status === 'pending'))

            return (
              <div key={tbl.name}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                    <span style={{ fontFamily: 'var(--font-mono)' }}>{tbl.name}</span>
                    <span style={{ color: 'var(--text-muted)' }}>{fmtBytes(tbl.size_bytes)}</span>
                    {bloatPct > 10 && (
                      <span style={{ color: 'var(--warning, #f59e0b)', fontWeight: 600 }}>
                        {bloatPct.toFixed(0)}% bloat
                      </span>
                    )}
                  </div>
                  <button
                    className="admin-btn admin-btn--sm"
                disabled={isRunning}
                onClick={() => setConfirmTable(tbl.name)}
                    style={{ padding: '2px 8px', fontSize: 11 }}
                  >
                    {tblRunning
                      ? <Loader size={11} className="spin" />
                      : <><Play size={11} /> VACUUM</>
                    }
                  </button>
                </div>
                <div style={{ height: 6, borderRadius: 3, background: 'var(--border)', position: 'relative' }}>
                  <div style={{
                    height: '100%', borderRadius: 3,
                    width: `${(tbl.size_bytes / maxSize) * 100}%`,
                    background: bloatPct > 30 ? 'var(--warning, #f59e0b)' : 'var(--accent)',
                  }} />
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>
                  {tbl.live_tuples.toLocaleString()} live · {tbl.dead_tuples.toLocaleString()} dead
                  {tbl.last_autovacuum && ` · vacuum ${new Date(tbl.last_autovacuum).toLocaleDateString()}`}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Right: history (grouped) */}
      <div className="admin-card">
        <h3 className="system-card-title"><Clock size={16} /> {t('admin.system.vacuumHistory')}</h3>
        {history.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '16px 0' }}>
            {t('admin.system.vacuumNoHistory')}
          </div>
        ) : (
          <VacuumHistoryGrouped
            history={history}
            expandedGroup={expandedGroup}
            onToggle={idx => setExpandedGroup(expandedGroup === idx ? null : idx)}
          />
        )}
      </div>

    </div>

      {confirmTable && (
        <ConfirmDialog
          title={t('admin.system.vacuumDialogTitle')}
          message={t('admin.system.vacuumDialogMessage')}
          details={confirmTable}
          confirmLabel={t('admin.system.vacuumDialogConfirm')}
          cancelLabel={t('admin.system.vacuumDialogCancel')}
          variant="danger"
          onConfirm={handleConfirmedRun}
          onCancel={() => setConfirmTable(null)}
        />
      )}
      {confirmAll && (
        <ConfirmDialog
          title={t('admin.system.vacuumAllDialogTitle')}
          message={t('admin.system.vacuumAllDialogMessage')}
          details={tables.map(t => t.name).join(', ')}
          confirmLabel={t('admin.system.vacuumDialogConfirm')}
          cancelLabel={t('admin.system.vacuumDialogCancel')}
          variant="danger"
          onConfirm={handleConfirmedRunAll}
          onCancel={() => setConfirmAll(false)}
        />
      )}
    </>
  )
}

export function SystemPage() {
  const { t } = useTranslation()
  const [data, setData] = useState<SystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true)
    try {
      const info = await getSystemInfo()
      setData(info)
      setLastUpdated(new Date())
    } catch {
      // keep old data on error
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(() => fetchData(), SYSTEM_REFRESH_INTERVAL)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [autoRefresh, fetchData])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('admin.system.loadFailed')}</div>

  const topTableMax = Math.max(...data.db_top_tables.map(t => t.size_bytes), 1)
  const s3QuotaPct = data.s3_quota_bytes > 0
    ? (data.s3_bucket_size_bytes / data.s3_quota_bytes) * 100
    : 0

  return (
    <div>
      {/* Header */}
      <div className="admin-page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1><Activity size={20} /> {t('admin.system.title')}</h1>
          <p>{t('admin.system.subtitle')}</p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {lastUpdated && (
            <span className="system-last-updated">{fmtTime(lastUpdated)}</span>
          )}
          <button
            className={`logs-live-btn${autoRefresh ? ' logs-live-btn--active' : ''}`}
            onClick={() => setAutoRefresh(v => !v)}
          >
            <Radio size={13} />
            {t('admin.system.autoRefresh')}
          </button>
          <button
            className="admin-btn admin-btn--sm"
            onClick={() => fetchData(true)}
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? 'spin' : ''} />
            {t('admin.system.refresh')}
          </button>
        </div>
      </div>

      {/* Services Health + Activity (merged) */}
      <div className="system-status-bar">
        <div className="system-health-section">
          {data.services.map((svc, i) => (
            <div key={i} className={`system-health-pill system-health-pill--${svc.status}`}>
              <HealthDot status={svc.status} />
              <span className="system-health-name">{svc.name}</span>
              <span className="system-health-latency">{svc.latency_ms.toFixed(0)}ms</span>
            </div>
          ))}
        </div>
        <div className="system-activity-section">
          <div className="system-activity-item">
            <Zap size={13} />
            <span className="system-activity-value">{data.active_requests}</span>
            <span className="system-activity-label">{t('admin.system.activeRequests')}</span>
          </div>
          <div className="system-activity-divider" />
          <div className="system-activity-item">
            <Users size={13} />
            <span className="system-activity-value">{data.online_users_5min}</span>
            <span className="system-activity-label">{t('admin.system.onlineUsers')}</span>
          </div>
          <div className="system-activity-divider" />
          <div className="system-activity-item">
            <MessageSquare size={13} />
            <span className="system-activity-value">{data.active_chat_sessions_5min}</span>
            <span className="system-activity-label">{t('admin.system.chatSessions')}</span>
          </div>
        </div>
      </div>

      {/* Server Resources */}
      <h3 className="system-section-title"><Cpu size={16} /> {t('admin.system.serverResources')}</h3>
      <div className="system-resources-grid">
        <ProgressBar
          label="CPU"
          pct={data.cpu_percent}
          sub={`${data.cpu_count} ${t('admin.system.cores')}`}
        />
        <ProgressBar
          label="RAM"
          pct={data.ram_percent}
          sub={`${fmtBytes(data.ram_used_bytes)} / ${fmtBytes(data.ram_total_bytes)}`}
        />
        <ProgressBar
          label={t('admin.system.disk')}
          pct={data.disk_percent}
          sub={`${fmtBytes(data.disk_used_bytes)} / ${fmtBytes(data.disk_total_bytes)}`}
        />
        <div className="system-progress-card system-uptime-card">
          <div className="system-progress-header">
            <span className="system-progress-label"><Clock size={12} /> {t('admin.system.uptime')}</span>
          </div>
          <span className="system-progress-value-large">{fmtUptime(data.uptime_sec)}</span>
        </div>
      </div>

      {/* PostgreSQL & Redis */}
      <div className="system-two-cols">
        <div className="admin-card">
          <div className="system-card-header">
            <h3 className="system-card-title"><Database size={16} /> PostgreSQL</h3>
            <span className="system-card-hero">{fmtBytes(data.db_size_bytes)}</span>
          </div>
          <div className="system-kv-list">
            <div className="system-kv">
              <span>{t('admin.system.activeConnections')}</span>
              <strong>{data.db_active_connections}</strong>
            </div>
            <div className="system-kv">
              <span>{t('admin.system.pool')}</span>
              <strong>{data.db_pool_checked_out}/{data.db_pool_size} used, {data.db_pool_overflow} overflow</strong>
            </div>
          </div>
          {data.db_top_tables.length > 0 && (
            <>
              <div className="system-kv-divider" />
              <span className="system-mini-label">{t('admin.system.topTables')}</span>
              <HorizBar
                items={data.db_top_tables.map(tbl => ({
                  label: tbl.name,
                  pct: (tbl.size_bytes / topTableMax) * 100,
                  sub: fmtBytes(tbl.size_bytes),
                }))}
              />
            </>
          )}
        </div>

        <div className="admin-card">
          <div className="system-card-header">
            <h3 className="system-card-title"><Server size={16} /> Redis & {t('admin.system.queues')}</h3>
            <span className="system-card-hero">{fmtBytes(data.redis_used_memory_bytes)}</span>
          </div>
          <div className="system-kv-list">
            <div className="system-kv">
              <span>{t('admin.system.totalKeys')}</span>
              <strong>{data.redis_total_keys.toLocaleString()}</strong>
            </div>
            <div className="system-kv-divider" />
            <div className="system-kv">
              <span>Queue: celery</span>
              <strong className={data.redis_queue_celery > 10 ? 'system-val--warn' : ''}>{data.redis_queue_celery}</strong>
            </div>
            <div className="system-kv">
              <span>Queue: monitoring</span>
              <strong>{data.redis_queue_monitoring}</strong>
            </div>
          </div>
        </div>
      </div>

      {/* Database Maintenance */}
      <h3 className="system-section-title"><Database size={16} /> {t('admin.system.vacuumSection')}</h3>
      <VacuumCard />

      {/* Ingestion + LLM | S3 */}
      <div className="system-two-cols">
        <div className="admin-card">
          <h3 className="system-card-title"><Layers size={16} /> {t('admin.system.ingestion')}</h3>
          <div className="system-badges">
            <span className={`system-badge ${data.ingestion.pending > 0 ? 'system-badge--warning' : 'system-badge--muted'}`}>
              <Clock size={12} /> {t('admin.system.pending')}: {data.ingestion.pending}
            </span>
            <span className={`system-badge ${data.ingestion.processing > 0 ? 'system-badge--accent' : 'system-badge--muted'}`}>
              <Loader size={12} /> {t('admin.system.processing')}: {data.ingestion.processing}
            </span>
            <span className={`system-badge ${data.ingestion.error > 0 ? 'system-badge--danger' : 'system-badge--muted'}`}>
              <AlertTriangle size={12} /> {t('admin.system.errors')}: {data.ingestion.error}
            </span>
          </div>
          <div className="system-kv-list" style={{ marginTop: 12 }}>
            <div className="system-kv">
              <span>{t('admin.system.speed')}</span>
              <strong>~{data.ingestion.docs_per_hour_24h} {t('admin.system.docsPerHour')}</strong>
            </div>
            <div className="system-kv">
              <span>{t('admin.system.stale')}</span>
              <strong className={data.ingestion.stale_count > 0 ? 'system-val--danger' : ''}>{data.ingestion.stale_count}</strong>
            </div>
            <div className="system-kv">
              <span>{t('admin.system.tusUploads')}</span>
              <strong>{data.ingestion.tus_uploads_active}</strong>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* LLM card */}
          <div className="admin-card">
            <h3 className="system-card-title"><Zap size={16} /> LLM</h3>
            <div className="system-kv-list">
              <div className="system-kv">
                <span>{data.llm.provider} / {data.llm.model}</span>
                <strong>{data.llm.avg_response_ms != null ? `${(data.llm.avg_response_ms / 1000).toFixed(1)}s avg` : '—'}</strong>
              </div>
              <div className="system-kv">
                <span>{t('admin.system.llmErrors')}</span>
                <strong className={data.llm.errors_last_hour > 0 ? 'system-val--danger' : ''}>
                  {data.llm.errors_last_hour} err / {data.llm.timeouts_last_hour} timeout
                </strong>
              </div>
            </div>
          </div>

          {/* S3 card */}
          <div className="admin-card">
            <div className="system-card-header">
              <h3 className="system-card-title"><HardDrive size={16} /> S3 / MinIO</h3>
              <span className="system-card-hero">{fmtBytes(data.s3_bucket_size_bytes)}</span>
            </div>
            <div className="system-kv-list">
              <div className="system-kv">
                <span>{t('admin.system.objects')}</span>
                <strong>{data.s3_objects_count.toLocaleString()}</strong>
              </div>
              <div className="system-kv">
                <span>{t('admin.system.health')}</span>
                <strong>
                  <HealthDot status={data.services.find(s => s.name.includes('S3'))?.status || 'ok'} />
                  {' '}{data.services.find(s => s.name.includes('S3'))?.status === 'ok' ? 'OK' : 'Error'}
                </strong>
              </div>
            </div>
            {data.s3_quota_bytes > 0 && (
              <>
                <div className="system-kv-divider" />
                <div className="system-kv" style={{ marginBottom: 4 }}>
                  <span>{t('admin.system.quota')}</span>
                  <strong>{s3QuotaPct.toFixed(1)}%</strong>
                </div>
                <InlineProgress
                  pct={s3QuotaPct}
                  sub={`${fmtBytes(data.s3_bucket_size_bytes)} / ${fmtBytes(data.s3_quota_bytes)}`}
                />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
