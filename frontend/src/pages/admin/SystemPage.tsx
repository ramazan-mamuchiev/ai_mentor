import { useEffect, useState, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Activity, RefreshCw, Database, HardDrive, Cpu, MemoryStick, Server, Layers } from 'lucide-react'
import { getSystemInfo, type SystemInfo } from '../../api/admin'

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

function HealthDot({ status }: { status: string }) {
  const color = status === 'ok'
    ? 'var(--success, #22c55e)'
    : status === 'degraded'
      ? 'var(--warning, #f59e0b)'
      : 'var(--danger, #ef4444)'
  return (
    <span
      className="health-dot"
      style={{ background: color }}
    />
  )
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

export function SystemPage() {
  const { t } = useTranslation()
  const [data, setData] = useState<SystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true)
    try {
      const info = await getSystemInfo()
      setData(info)
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
      intervalRef.current = setInterval(() => fetchData(), 30000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [autoRefresh, fetchData])

  if (loading) return <div className="admin-loading">{t('admin.common.loading')}</div>
  if (!data) return <div className="admin-empty">{t('admin.system.loadFailed')}</div>

  const topTableMax = Math.max(...data.db_top_tables.map(t => t.size_bytes), 1)

  return (
    <div>
      <div className="admin-page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1><Activity size={20} /> {t('admin.system.title')}</h1>
          <p>{t('admin.system.subtitle')}</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label className="system-auto-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={e => setAutoRefresh(e.target.checked)}
            />
            <span>{t('admin.system.autoRefresh')}</span>
          </label>
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

      {/* Services Health */}
      <div className="admin-card system-health-bar">
        {data.services.map((svc, i) => (
          <div key={i} className="system-health-item">
            <HealthDot status={svc.status} />
            <span className="system-health-name">{svc.name}</span>
            <span className="system-health-latency">{svc.latency_ms.toFixed(0)}ms</span>
          </div>
        ))}
      </div>

      {/* Activity strip */}
      <div className="system-activity-strip">
        <div className="system-activity-item">
          <span className="system-activity-value">{data.active_requests}</span>
          <span className="system-activity-label">{t('admin.system.activeRequests')}</span>
        </div>
        <div className="system-activity-divider" />
        <div className="system-activity-item">
          <span className="system-activity-value">{data.online_users_5min}</span>
          <span className="system-activity-label">{t('admin.system.onlineUsers')}</span>
        </div>
        <div className="system-activity-divider" />
        <div className="system-activity-item">
          <span className="system-activity-value">{data.active_chat_sessions_5min}</span>
          <span className="system-activity-label">{t('admin.system.chatSessions')}</span>
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
        <div className="system-progress-card">
          <div className="system-progress-header">
            <span className="system-progress-label">{t('admin.system.uptime')}</span>
          </div>
          <span className="system-progress-value-large">{fmtUptime(data.uptime_sec)}</span>
          <span className="system-progress-sub">{data.cpu_count} {t('admin.system.cores')}</span>
        </div>
      </div>

      {/* PostgreSQL & Redis */}
      <div className="system-two-cols">
        <div className="admin-card">
          <h3 className="system-card-title"><Database size={16} /> PostgreSQL</h3>
          <div className="system-kv-list">
            <div className="system-kv">
              <span>{t('admin.system.dbSize')}</span>
              <strong>{fmtBytes(data.db_size_bytes)}</strong>
            </div>
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
          <h3 className="system-card-title"><Server size={16} /> Redis & {t('admin.system.queues')}</h3>
          <div className="system-kv-list">
            <div className="system-kv">
              <span>{t('admin.system.memory')}</span>
              <strong>{fmtBytes(data.redis_used_memory_bytes)}</strong>
            </div>
            <div className="system-kv">
              <span>{t('admin.system.totalKeys')}</span>
              <strong>{data.redis_total_keys.toLocaleString()}</strong>
            </div>
            <div className="system-kv-divider" />
            <div className="system-kv">
              <span>Queue: celery</span>
              <strong>{data.redis_queue_celery}</strong>
            </div>
            <div className="system-kv">
              <span>Queue: monitoring</span>
              <strong>{data.redis_queue_monitoring}</strong>
            </div>
          </div>
        </div>
      </div>

      {/* Ingestion & S3 */}
      <div className="system-two-cols">
        <div className="admin-card">
          <h3 className="system-card-title"><Layers size={16} /> {t('admin.system.ingestion')}</h3>
          <div className="system-badges">
            <span className="badge badge--warning">⏳ {t('admin.system.pending')}: {data.ingestion.pending}</span>
            <span className="badge badge--accent">⚙ {t('admin.system.processing')}: {data.ingestion.processing}</span>
            <span className="badge badge--danger">✕ {t('admin.system.errors')}: {data.ingestion.error}</span>
          </div>
          <div className="system-kv-list" style={{ marginTop: 12 }}>
            <div className="system-kv">
              <span>{t('admin.system.speed')}</span>
              <strong>~{data.ingestion.docs_per_hour_24h} {t('admin.system.docsPerHour')}</strong>
            </div>
            <div className="system-kv">
              <span>{t('admin.system.stale')}</span>
              <strong>{data.ingestion.stale_count}</strong>
            </div>
            <div className="system-kv">
              <span>{t('admin.system.tusUploads')}</span>
              <strong>{data.ingestion.tus_uploads_active}</strong>
            </div>
          </div>
          <div className="system-kv-divider" />
          <span className="system-mini-label">LLM ({t('admin.system.lastHour')})</span>
          <div className="system-kv-list">
            <div className="system-kv">
              <span>{data.llm.provider} / {data.llm.model}</span>
              <strong>{data.llm.avg_response_ms != null ? `${(data.llm.avg_response_ms / 1000).toFixed(1)}s avg` : '—'}</strong>
            </div>
            <div className="system-kv">
              <span>{t('admin.system.llmErrors')}</span>
              <strong>{data.llm.errors_last_hour} err / {data.llm.timeouts_last_hour} timeout</strong>
            </div>
          </div>
        </div>

        <div className="admin-card">
          <h3 className="system-card-title"><HardDrive size={16} /> S3 / MinIO</h3>
          <div className="system-kv-list">
            <div className="system-kv">
              <span>{t('admin.system.bucketSize')}</span>
              <strong>{fmtBytes(data.s3_bucket_size_bytes)}</strong>
            </div>
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
              <span className="system-mini-label">{t('admin.system.quota')}</span>
              <ProgressBar
                label=""
                pct={(data.s3_bucket_size_bytes / data.s3_quota_bytes) * 100}
                sub={`${fmtBytes(data.s3_bucket_size_bytes)} / ${fmtBytes(data.s3_quota_bytes)}`}
              />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
