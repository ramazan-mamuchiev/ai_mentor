import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { getLogs, type LogEntry } from '../../api/admin'

const SERVICES = ['api', 'worker', 'beat', 'web', 'postgres', 'redis'] as const
const LEVELS = ['', 'info', 'warning', 'error', 'debug'] as const

export function LogsPage() {
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [service, setService] = useState('api')
  const [level, setLevel] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await getLogs({
        service, level: level || undefined,
        search: search || undefined, limit: 500,
      })
      setEntries(res.entries)
    } catch { /* ignore */ }
    setLoading(false)
  }, [service, level, search])

  useEffect(() => {
    setLoading(true)
    load()
  }, [load])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(load, 3000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [autoRefresh, load])

  const formatTimestamp = (ts: string): string => {
    try {
      const ns = BigInt(ts)
      const ms = Number(ns / BigInt(1_000_000))
      return new Date(ms).toLocaleString()
    } catch {
      return ts
    }
  }

  return (
    <div>
      <div className="admin-page-header">
        <h1>Logs</h1>
        <p>View platform logs via Loki</p>
      </div>

      <div className="admin-toolbar" style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', marginBottom: 16 }}>
        <select className="admin-select" value={service} onChange={e => setService(e.target.value)}>
          {SERVICES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="admin-select" value={level} onChange={e => setLevel(e.target.value)}>
          <option value="">All levels</option>
          {LEVELS.filter(Boolean).map(l => <option key={l} value={l}>{l}</option>)}
        </select>
        <input
          className="admin-search"
          placeholder="Search logs..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && load()}
        />
        <button className="admin-btn admin-btn--sm" onClick={load}>
          <RefreshCw size={14} />
        </button>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer' }}>
          <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
          Live tail
        </label>
      </div>

      {loading ? (
        <div className="admin-loading">Loading logs...</div>
      ) : entries.length === 0 ? (
        <div className="admin-empty">No log entries found. Loki might not be reachable from the backend.</div>
      ) : (
        <div className="log-viewer" ref={containerRef}>
          {entries.map((entry, i) => (
            <div key={i} className="log-entry">
              <span className="log-entry__ts">{formatTimestamp(entry.timestamp)}</span>
              <span className={`log-entry__level log-entry__level--${entry.level.toLowerCase()}`}>
                {entry.level || 'info'}
              </span>
              <span className="log-entry__msg">{entry.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
