import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Target, Play, Loader2, Clock, ChevronDown, ChevronUp } from 'lucide-react'
import {
  startRagEval, getRagEvalRuns, getRagEvalRun, getLatestRagEval, cancelRagEval,
  type RagEvalRunDetail, type RagEvalRunItem,
} from '../../api/admin'

type Tab = 'overview' | 'retrieval' | 'generation' | 'system' | 'history' | 'details'

function fmtDuration(start: string, end: string | null): string {
  if (!end) return '—'
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (ms < 60000) return `${Math.round(ms / 1000)}s`
  const m = Math.floor(ms / 60000)
  const s = Math.round((ms % 60000) / 1000)
  return `${m}m ${s.toString().padStart(2, '0')}s`
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function metricColor(val: number | null, isRate = false): string {
  if (val == null) return 'var(--text-muted)'
  if (isRate) {
    if (val <= 0.05) return 'var(--success)'
    if (val <= 0.15) return 'var(--warning)'
    return 'var(--danger)'
  }
  if (val >= 0.8) return 'var(--success)'
  if (val >= 0.6) return 'var(--warning)'
  return 'var(--danger)'
}

function fmtMetric(val: number | null | undefined, suffix = ''): string {
  if (val == null) return '—'
  return `${val.toFixed(2)}${suffix}`
}

function fmtPct(val: number | null | undefined): string {
  if (val == null) return '—'
  return `${(val * 100).toFixed(1)}%`
}

function DeltaBadge({ current, previous, t }: { current: number | null; previous: number | null; t: (k: string) => string }) {
  if (current == null || previous == null) return null
  const d = current - previous
  if (Math.abs(d) < 0.005) return <span className="stat-card__sub">{t('admin.ragEval.stable')}</span>
  const sign = d > 0 ? '+' : ''
  const color = d > 0 ? 'var(--success)' : 'var(--danger)'
  return <span className="stat-card__sub" style={{ color }}>{sign}{d.toFixed(2)} {t('admin.ragEval.vsPrevious')}</span>
}

function StatCard({ label, value, sub, variant }: {
  label: string; value: string; sub?: React.ReactNode; variant?: string
}) {
  return (
    <div className={`stat-card animate-in${variant ? ` stat-card--${variant}` : ''}`}>
      <div className="stat-card__label">{label}</div>
      <div className="stat-card__value" style={variant ? undefined : { color: 'var(--accent2)' }}>{value}</div>
      {sub && <div className="stat-card__sub">{sub}</div>}
    </div>
  )
}

function GaugeCard({ name, value, max = 1, desc, isRate = false }: {
  name: string; value: number | null; max?: number; desc?: string; isRate?: boolean
}) {
  const pct = value != null ? Math.min(100, (value / max) * 100) : 0
  const color = metricColor(value, isRate)
  const display = isRate ? fmtPct(value) : fmtMetric(value)
  return (
    <div className="rag-eval-gauge-card">
      <div className="rag-eval-gauge-header">
        <span className="rag-eval-gauge-name">{name}</span>
        <span className="rag-eval-gauge-value" style={{ color }}>{display}</span>
      </div>
      <div className="rag-eval-gauge-track">
        <div className="rag-eval-gauge-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="rag-eval-gauge-labels">
        <span>{isRate ? '0%' : '0.0'}</span>
        <span>{isRate ? '100%' : max.toFixed(1)}</span>
      </div>
      {desc && <div className="rag-eval-gauge-desc">{desc}</div>}
    </div>
  )
}

export function RagEvalPage() {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('overview')
  const [latest, setLatest] = useState<RagEvalRunDetail | null>(null)
  const [previous, setPrevious] = useState<RagEvalRunItem | null>(null)
  const [runs, setRuns] = useState<RagEvalRunItem[]>([])
  const [total, setTotal] = useState(0)
  const [activeRun, setActiveRun] = useState<RagEvalRunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const [sampleSize, setSampleSize] = useState(50)
  const [expandedSample, setExpandedSample] = useState<number | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadData = useCallback(async () => {
    try {
      const [latestRes, runsRes] = await Promise.all([
        getLatestRagEval().catch(() => null),
        getRagEvalRuns(1, 50).catch(() => ({ items: [], total: 0 })),
      ])
      setLatest(latestRes)
      setRuns(runsRes.items)
      setTotal(runsRes.total)

      const completedRuns = runsRes.items.filter(r => r.status === 'completed')
      if (completedRuns.length >= 2) {
        setPrevious(completedRuns[1])
      }

      const runningRun = runsRes.items.find(r => r.status === 'running')
      if (runningRun) {
        const detail = await getRagEvalRun(runningRun.id).catch(() => null)
        if (detail) setActiveRun(detail)
      } else {
        setActiveRun(null)
      }
    } catch (e) {
      console.error('Failed to load RAG eval data', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  useEffect(() => {
    if (activeRun && activeRun.status === 'running') {
      pollRef.current = setInterval(async () => {
        try {
          const updated = await getRagEvalRun(activeRun.id)
          setActiveRun(updated)
          if (updated.status !== 'running') {
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
            await loadData()
          }
        } catch { /* ignore */ }
      }, 1500)
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [activeRun?.id, activeRun?.status, loadData])

  const handleStart = async () => {
    setStarting(true)
    try {
      const run = await startRagEval(sampleSize)
      const detail = await getRagEvalRun(run.id)
      setActiveRun(detail)
    } catch (e: any) {
      if (e?.message?.includes('409')) {
        alert(t('admin.ragEval.alreadyRunning'))
      }
    } finally {
      setStarting(false)
    }
  }

  const handleCancel = async () => {
    if (!activeRun) return
    try {
      await cancelRagEval(activeRun.id)
      setActiveRun(null)
      await loadData()
    } catch { /* ignore */ }
  }

  const isRunning = activeRun?.status === 'running'
  const data = latest

  if (loading) {
    return <div className="admin-loading">{t('admin.common.loading')}</div>
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: t('admin.ragEval.tab.overview') },
    { id: 'retrieval', label: t('admin.ragEval.tab.retrieval') },
    { id: 'generation', label: t('admin.ragEval.tab.generation') },
    { id: 'system', label: t('admin.ragEval.tab.system') },
    { id: 'history', label: t('admin.ragEval.tab.history') },
    { id: 'details', label: t('admin.ragEval.tab.details') },
  ]

  return (
    <div className="admin-page">
      {/* Header */}
      <div className="admin-page-header rag-eval-page-header">
        <div>
          <h1><Target size={20} /> {t('admin.ragEval.title')}</h1>
          {data && !isRunning && (
            <p>
              <span className={`rag-eval-dot rag-eval-dot--${data.status === 'completed' ? 'ok' : 'err'}`} />
              {t('admin.ragEval.lastRun')}: {fmtDate(data.started_at)} — {' '}
              <span style={{ color: data.status === 'completed' ? 'var(--success)' : 'var(--danger)' }}>
                {data.status === 'completed' ? t('admin.ragEval.completed') : t('admin.ragEval.failed')}
              </span>
              {' '}({fmtDuration(data.started_at, data.finished_at)})
              {' · '}{data.sample_size} {t('admin.ragEval.samples')}
            </p>
          )}
        </div>
        <div className="rag-eval-actions">
          {isRunning && activeRun ? (
            <div className="rag-eval-progress-inline">
              <div className="rag-eval-progress-inline-top">
                <Loader2 size={14} className="rag-eval-spin" />
                <span className="rag-eval-progress-inline-stage">{activeRun.progress_stage || t('admin.ragEval.running')}</span>
                <span className="rag-eval-progress-inline-time">
                  <Clock size={12} />
                  {fmtDuration(activeRun.started_at, new Date().toISOString())}
                </span>
              </div>
              <div className="rag-eval-progress-inline-bottom">
                <div className="rag-eval-progress-inline-track">
                  <div className="rag-eval-progress-inline-fill" style={{ width: `${activeRun.progress_percent}%` }} />
                </div>
                <button className="rag-eval-cancel-link" onClick={handleCancel}>
                  {t('admin.ragEval.cancel')}
                </button>
              </div>
            </div>
          ) : (
            <>
              <select
                className="admin-select"
                value={sampleSize}
                onChange={e => setSampleSize(Number(e.target.value))}
                disabled={starting}
              >
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <button
                className="admin-btn admin-btn--primary"
                onClick={handleStart}
                disabled={starting}
              >
                {starting ? <Loader2 size={16} className="rag-eval-spin" /> : <Play size={16} />}
                {t('admin.ragEval.runEval')}
              </button>
            </>
          )}
        </div>
      </div>

      {!data && !isRunning && (
        <div className="rag-eval-empty-state">
          <div className="rag-eval-empty-icon">
            <Target size={48} strokeWidth={1} />
          </div>
          <p className="rag-eval-empty-title">{t('admin.ragEval.noRuns')}</p>
          <p className="rag-eval-empty-hint">{t('admin.ragEval.noRunsHint')}</p>
        </div>
      )}

      {!data && isRunning && (
        <div className="rag-eval-empty-state">
          <div className="rag-eval-empty-icon">
            <Loader2 size={48} strokeWidth={1} className="rag-eval-spin" />
          </div>
          <p className="rag-eval-empty-title">{t('admin.ragEval.running')}</p>
          <p className="rag-eval-empty-hint">{activeRun?.progress_stage || ''}</p>
        </div>
      )}

      {data && (
        <div className="rag-eval-tabs">
          {tabs.map(t => (
            <button
              key={t.id}
              className={`rag-eval-tab${tab === t.id ? ' rag-eval-tab--active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {/* Overview */}
      {tab === 'overview' && data && (
        <>
          <div className="stats-grid">
            <StatCard
              label={t('admin.ragEval.contextPrecision')}
              value={fmtMetric(data.context_precision)}
              sub={<DeltaBadge current={data.context_precision} previous={previous?.context_precision ?? null} t={t} />}
              variant={data.context_precision != null && data.context_precision >= 0.8 ? 'success' : undefined}
            />
            <StatCard
              label={t('admin.ragEval.faithfulness')}
              value={fmtMetric(data.faithfulness)}
              sub={<DeltaBadge current={data.faithfulness} previous={previous?.faithfulness ?? null} t={t} />}
              variant={data.faithfulness != null && data.faithfulness >= 0.8 ? 'success' : undefined}
            />
            <StatCard
              label={t('admin.ragEval.mrr')}
              value={fmtMetric(data.mrr)}
              sub={<DeltaBadge current={data.mrr} previous={previous?.mrr ?? null} t={t} />}
              variant={data.mrr != null && data.mrr >= 0.8 ? 'success' : undefined}
            />
            <StatCard
              label={t('admin.ragEval.feedbackScore')}
              value={fmtPct(data.feedback_positive_rate)}
              sub={<DeltaBadge current={data.feedback_positive_rate} previous={previous?.feedback_positive_rate ?? null} t={t} />}
              variant={data.feedback_positive_rate != null && data.feedback_positive_rate >= 0.8 ? 'success' : undefined}
            />
            <StatCard
              label={t('admin.ragEval.emptyRetrieval')}
              value={fmtPct(data.empty_retrieval_rate)}
              variant={data.empty_retrieval_rate != null && data.empty_retrieval_rate <= 0.05 ? 'success' : undefined}
            />
            <StatCard
              label={t('admin.ragEval.vectorSearch')}
              value={data.vector_search_ms != null ? `${data.vector_search_ms.toFixed(1)}ms` : '—'}
            />
          </div>

          <div className="rag-eval-section-title">{t('admin.ragEval.qualityGauges')}</div>
          <div className="rag-eval-gauge-grid">
            <GaugeCard name={t('admin.ragEval.contextPrecision')} value={data.context_precision} desc={t('admin.ragEval.contextPrecisionDesc')} />
            <GaugeCard name={t('admin.ragEval.faithfulness')} value={data.faithfulness} desc={t('admin.ragEval.faithfulnessDesc')} />
            <GaugeCard name={t('admin.ragEval.mrr')} value={data.mrr} desc={t('admin.ragEval.mrrDesc')} />
            <GaugeCard name={t('admin.ragEval.noAnswerRate')} value={data.no_answer_rate} isRate desc={t('admin.ragEval.noAnswerRateDesc')} />
            <GaugeCard name={t('admin.ragEval.emptyRetrieval')} value={data.empty_retrieval_rate} isRate desc={t('admin.ragEval.emptyRetrievalDesc')} />
          </div>

          {/* Trend chart */}
          {runs.filter(r => r.status === 'completed').length > 1 && (
            <>
              <div className="rag-eval-section-title">{t('admin.ragEval.trendTitle')}</div>
              <div className="admin-chart">
                <div className="admin-chart-bars">
                  {runs.filter(r => r.status === 'completed').reverse().slice(-10).map((r, i) => (
                    <div
                      key={r.id}
                      className="admin-chart-bar"
                      style={{
                        height: `${(r.faithfulness ?? 0) * 100}%`,
                        background: r.id === data.id
                          ? 'linear-gradient(180deg, var(--success), var(--accent))'
                          : 'var(--accent)',
                      }}
                      title={`${fmtDate(r.started_at)}: ${fmtMetric(r.faithfulness)}`}
                    />
                  ))}
                </div>
                <div className="admin-chart-labels">
                  {(() => {
                    const completed = runs.filter(r => r.status === 'completed').reverse().slice(-10)
                    if (completed.length === 0) return null
                    return (
                      <>
                        <span>{fmtDate(completed[0].started_at).split(',')[0]}</span>
                        <span>{fmtDate(completed[completed.length - 1].started_at).split(',')[0]}</span>
                      </>
                    )
                  })()}
                </div>
              </div>
            </>
          )}

          {/* Segmentation */}
          {data.metrics_by_query_type && Object.keys(data.metrics_by_query_type).length > 0 && (
            <>
              <div className="rag-eval-section-title">{t('admin.ragEval.segment.queryType')}</div>
              <div className="admin-table-wrapper">
                <div className="admin-table-scroll">
                  <table className="admin-table">
                    <thead>
                      <tr>
                        <th>{t('admin.ragEval.col.queryType')}</th>
                        <th>{t('admin.ragEval.col.queries')}</th>
                        <th>{t('admin.ragEval.col.emptyRate')}</th>
                        <th>{t('admin.ragEval.col.avgSimilarity')}</th>
                        <th>{t('admin.ragEval.col.avgE2e')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(data.metrics_by_query_type).map(([qt, m]: [string, any]) => (
                        <tr key={qt}>
                          <td><span className="badge badge--blue">{qt}</span></td>
                          <td className="mono">{m.total}</td>
                          <td className="mono" style={{ color: metricColor(m.empty_retrieval_rate, true) }}>{fmtPct(m.empty_retrieval_rate)}</td>
                          <td className="mono">{m.avg_similarity?.toFixed(3) ?? '—'}</td>
                          <td className="mono">{m.avg_e2e_ms?.toFixed(0) ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </>
      )}

      {/* Retrieval tab */}
      {tab === 'retrieval' && data && (
        <>
          <div className="stats-grid">
            <StatCard label={t('admin.ragEval.similarityP50')} value={fmtMetric(data.similarity_p50)} />
            <StatCard label={t('admin.ragEval.similarityP75')} value={fmtMetric(data.similarity_p75)} />
            <StatCard label={t('admin.ragEval.similarityP90')} value={fmtMetric(data.similarity_p90)} />
            <StatCard label={t('admin.ragEval.searchLatencyP50')} value={data.search_latency_p50_ms != null ? `${data.search_latency_p50_ms.toFixed(0)}ms` : '—'} />
            <StatCard label={t('admin.ragEval.searchLatencyP95')} value={data.search_latency_p95_ms != null ? `${data.search_latency_p95_ms.toFixed(0)}ms` : '—'} />
          </div>
          <div className="rag-eval-gauge-grid">
            <GaugeCard name={t('admin.ragEval.contextPrecision')} value={data.context_precision} desc={t('admin.ragEval.contextPrecisionDesc')} />
            <GaugeCard name={t('admin.ragEval.mrr')} value={data.mrr} desc={t('admin.ragEval.mrrDesc')} />
            <GaugeCard name={t('admin.ragEval.emptyRetrieval')} value={data.empty_retrieval_rate} isRate desc={t('admin.ragEval.emptyRetrievalDesc')} />
          </div>
        </>
      )}

      {/* Generation tab */}
      {tab === 'generation' && data && (
        <>
          <div className="stats-grid">
            <StatCard
              label={t('admin.ragEval.faithfulness')}
              value={fmtMetric(data.faithfulness)}
              variant={data.faithfulness != null && data.faithfulness >= 0.8 ? 'success' : undefined}
            />
            <StatCard
              label={t('admin.ragEval.answerRelevance')}
              value={fmtMetric(data.answer_relevance)}
            />
            <StatCard
              label={t('admin.ragEval.feedbackScore')}
              value={fmtPct(data.feedback_positive_rate)}
              variant={data.feedback_positive_rate != null && data.feedback_positive_rate >= 0.8 ? 'success' : undefined}
            />
            <StatCard
              label={t('admin.ragEval.noAnswerRate')}
              value={fmtPct(data.no_answer_rate)}
            />
          </div>
          <div className="rag-eval-gauge-grid">
            <GaugeCard name={t('admin.ragEval.faithfulness')} value={data.faithfulness} desc={t('admin.ragEval.faithfulnessDesc')} />
            <GaugeCard name={t('admin.ragEval.answerRelevance')} value={data.answer_relevance} desc={t('admin.ragEval.answerRelevanceDesc')} />
            <GaugeCard name={t('admin.ragEval.noAnswerRate')} value={data.no_answer_rate} isRate desc={t('admin.ragEval.noAnswerRateDesc')} />
          </div>
        </>
      )}

      {/* System tab */}
      {tab === 'system' && data && (
        <>
          <div className="stats-grid">
            <StatCard label={t('admin.ragEval.totalVectors')} value={data.vector_count?.toLocaleString() ?? '—'} />
            <StatCard label={t('admin.ragEval.hnswIndex')} value={data.hnsw_index_size_mb != null ? `${data.hnsw_index_size_mb.toFixed(0)} MB` : '—'} />
            <StatCard label={t('admin.ragEval.vectorSearch')} value={data.vector_search_ms != null ? `${data.vector_search_ms.toFixed(1)}ms` : '—'} sub={t('admin.ragEval.warmCache')} />
            <StatCard label={t('admin.ragEval.e2eLatencyP50')} value={data.e2e_latency_p50_ms != null ? `${(data.e2e_latency_p50_ms / 1000).toFixed(1)}s` : '—'} />
            <StatCard label={t('admin.ragEval.e2eLatencyP95')} value={data.e2e_latency_p95_ms != null ? `${(data.e2e_latency_p95_ms / 1000).toFixed(1)}s` : '—'} />
          </div>
        </>
      )}

      {/* History tab */}
      {tab === 'history' && (
        <>
          <div className="rag-eval-section-title">{t('admin.ragEval.history')}</div>
          <div className="admin-table-wrapper">
            <div className="admin-table-scroll">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>{t('admin.ragEval.date')}</th>
                    <th>{t('admin.ragEval.status')}</th>
                    <th>{t('admin.ragEval.duration')}</th>
                    <th>{t('admin.ragEval.sampleSize')}</th>
                    <th>{t('admin.ragEval.col.precision')}</th>
                    <th>{t('admin.ragEval.col.faithful')}</th>
                    <th>{t('admin.ragEval.col.mrr')}</th>
                    <th>{t('admin.ragEval.col.feedback')}</th>
                    <th>{t('admin.ragEval.col.vectorMs')}</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map(r => (
                    <tr key={r.id}>
                      <td className="mono">{fmtDate(r.started_at)}</td>
                      <td>
                        <span className={`badge badge--${r.status === 'completed' ? 'green' : r.status === 'running' ? 'blue' : 'red'}`}>
                          {r.status}
                        </span>
                      </td>
                      <td className="mono">{fmtDuration(r.started_at, r.finished_at)}</td>
                      <td className="mono">{r.sample_size}</td>
                      <td className="mono" style={{ color: metricColor(r.context_precision) }}>{fmtMetric(r.context_precision)}</td>
                      <td className="mono" style={{ color: metricColor(r.faithfulness) }}>{fmtMetric(r.faithfulness)}</td>
                      <td className="mono" style={{ color: metricColor(r.mrr) }}>{fmtMetric(r.mrr)}</td>
                      <td className="mono" style={{ color: metricColor(r.feedback_positive_rate) }}>{fmtPct(r.feedback_positive_rate)}</td>
                      <td className="mono">{r.vector_search_ms?.toFixed(1) ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Details (drill-down) tab */}
      {tab === 'details' && data?.details && (
        <>
          <div className="rag-eval-section-title">{t('admin.ragEval.sampleDetails')} ({data.details.length})</div>
          <div className="admin-table-wrapper">
            <div className="admin-table-scroll">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>{t('admin.ragEval.question')}</th>
                    <th>{t('admin.ragEval.col.type')}</th>
                    <th>{t('admin.ragEval.col.faithful')}</th>
                    <th>{t('admin.ragEval.col.precision')}</th>
                    <th>{t('admin.ragEval.col.similarity')}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {[...data.details]
                    .sort((a, b) => (a.faithfulness ?? 1) - (b.faithfulness ?? 1))
                    .map((s: any, i: number) => (
                    <>
                      <tr key={i} className="admin-table-row-clickable" onClick={() => setExpandedSample(expandedSample === i ? null : i)}>
                        <td className="mono">{i + 1}</td>
                        <td style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.question}</td>
                        <td>{s.query_type ? <span className="badge badge--blue">{s.query_type}</span> : '—'}</td>
                        <td className="mono" style={{ color: metricColor(s.faithfulness) }}>{fmtMetric(s.faithfulness)}</td>
                        <td className="mono" style={{ color: metricColor(s.context_precision) }}>{fmtMetric(s.context_precision)}</td>
                        <td className="mono">{s.top_similarity?.toFixed(3) ?? '—'}</td>
                        <td>{expandedSample === i ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</td>
                      </tr>
                      {expandedSample === i && (
                        <tr key={`${i}-detail`}>
                          <td colSpan={7}>
                            <div className="rag-eval-sample-detail">
                              <div className="rag-eval-sample-section">
                                <strong>{t('admin.ragEval.question')}:</strong>
                                <p>{s.question}</p>
                              </div>
                              <div className="rag-eval-sample-section">
                                <strong>{t('admin.ragEval.answer')}:</strong>
                                <p>{s.answer}</p>
                              </div>
                              <div className="rag-eval-sample-meta">
                                <span>{t('admin.ragEval.chunks')}: {s.chunks_count}</span>
                                <span>{t('admin.ragEval.product')}: {s.product_filter ?? '—'}</span>
                                <span>{t('admin.ragEval.topSimilarity')}: {s.top_similarity?.toFixed(3)}</span>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
