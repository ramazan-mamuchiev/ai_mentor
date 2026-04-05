import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  X, Loader2, AlertCircle, Activity, Maximize2, Minimize2, Share2,
  Play, RefreshCw, ChevronDown, ChevronUp, AlertTriangle, CheckCircle, XCircle, Trash2,
  FileText, Layers,
} from 'lucide-react'
import {
  getProductLifecycle, analyzeProductLifecycle, deleteProductLifecycle,
} from '../api/products'
import type { ProductLifecycle, LifecyclePayload } from '../api/products'
import { ConfirmDialog } from './ConfirmDialog'
import { ShareModal } from './ShareModal'
import { MermaidDiagram } from './MermaidDiagram'
import { SkeletonCodeViewer } from './SkeletonCodeViewer'

const POLL_INTERVAL = 4000

interface Props {
  productId: number
  productName: string
  canRun?: boolean
  onClose: () => void
  onDeleted?: () => void
  onAnalyzed?: () => void
}

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation()
  const icon = status === 'ready' ? <CheckCircle size={12} /> :
    status === 'error' ? <XCircle size={12} /> :
    status === 'pending' || status === 'processing' ? <Loader2 size={12} className="spin-icon" /> : null
  return (
    <span className={`lc-modal-status lc-modal-status--${status}`}>
      {icon} {t(`lifecycle.status.${status}`, status)}
    </span>
  )
}

interface AggregatedUsage {
  prompt_tokens: number
  completion_tokens: number
  analysis_ms: number
}

interface LifecycleContentProps {
  lc: LifecyclePayload
  productId?: number
  documentId?: number
  issues?: Array<{ document_id: number; issue_type: string; severity: string; description: string; affected_entity?: string; suggestion?: string }>
  aggregatedUsage?: AggregatedUsage
}

export function LifecycleContent({ lc, productId, documentId, issues = [], aggregatedUsage }: LifecycleContentProps) {
  const { t } = useTranslation()
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    prereqs: true, dataFlows: true, phases: true, dataModels: true, errors: true,
    accessPatterns: true, patterns: true, deps: true, skeleton: false,
    coverage: true, issues: true,
  })
  const toggle = (key: string) => setOpenSections(prev => ({ ...prev, [key]: !prev[key] }))

  const phases = lc.phases ?? []
  const patterns = lc.unique_patterns ?? []
  const deps = lc.dependency_chains ?? []
  const dataModels = lc.data_models ?? []
  const errorCatalog = lc.error_catalog ?? []
  const prereqs = lc.prerequisites ?? []
  const accessPatterns = lc.data_access_patterns ?? []
  const coverage = lc.endpoint_coverage ?? []
  const dataFlows = lc.integration_data_flows ?? {}
  const flowComponents = dataFlows.components ?? []
  const flowEdges = dataFlows.flows ?? []
  const flowMermaid = dataFlows.diagram_mermaid ?? ''
  const avgCompleteness = coverage.length > 0
    ? Math.round(coverage.reduce((s: number, e: { completeness?: number }) => s + (e.completeness ?? 0), 0) / coverage.length * 100)
    : null

  return (
    <>
      <div className="lc-modal-meta">
        <StatusBadge status={lc.status} />
        {(lc.updated_at || lc.created_at) && (() => {
          const d = new Date(lc.updated_at || lc.created_at!)
          const datePart = d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
          const timePart = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
          return (
            <span className="lc-modal-date" title={d.toLocaleString()}>
              {datePart} {timePart}
            </span>
          )
        })()}
        {avgCompleteness !== null && (
          <span className={`lc-modal-quality lc-modal-quality--${avgCompleteness >= 80 ? 'good' : avgCompleteness >= 50 ? 'partial' : 'low'}`}>
            {t('lifecycle.docQuality', { pct: avgCompleteness })}
          </span>
        )}
        {lc.model && <span className="lc-modal-model">{lc.model}</span>}
        {(() => {
          const ms = aggregatedUsage?.analysis_ms ?? lc.analysis_ms
          const pt = aggregatedUsage?.prompt_tokens ?? lc.prompt_tokens
          const ct = aggregatedUsage?.completion_tokens ?? lc.completion_tokens
          return (
            <>
              {ms != null && ms > 0 && <span className="lc-modal-time">{(ms / 1000).toFixed(1)}s</span>}
              {pt != null && pt > 0 && (
                <span className="lc-modal-tokens">{pt.toLocaleString()} + {(ct ?? 0).toLocaleString()} {t('lifecycle.tokens', 'tokens')}</span>
              )}
            </>
          )
        })()}
        {lc.validation_retries != null && lc.validation_retries > 0 && (
          <span className="lc-modal-retries">{lc.validation_retries} {t('lifecycleModal.retries')}</span>
        )}
      </div>

      {lc.status !== 'ready' && (
        <div className="lc-modal-empty">
          <AlertCircle size={28} />
          <p>{t(`lifecycle.status.${lc.status}`, lc.status)}</p>
        </div>
      )}

      {lc.status === 'ready' && (
        <>
          <div className="lc-modal-collapse-bar">
            <button
              className="lc-modal-collapse-btn"
              onClick={() => {
                const allOpen = Object.values(openSections).every(Boolean)
                const next: Record<string, boolean> = {}
                for (const k of Object.keys(openSections)) next[k] = !allOpen
                setOpenSections(next)
              }}
            >
              {Object.values(openSections).every(Boolean) ? (
                <><ChevronUp size={14} /> {t('lifecycleModal.collapseAll', 'Свернуть все')}</>
              ) : (
                <><ChevronDown size={14} /> {t('lifecycleModal.expandAll', 'Развернуть все')}</>
              )}
            </button>
          </div>

          {prereqs.length > 0 && (
            <div className="lc-modal-section">
              <button className="lc-modal-section-toggle" onClick={() => toggle('prereqs')}>
                {openSections.prereqs ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                <span>{t('lifecycle.prerequisites', 'Prerequisites')}</span>
                <span className="lc-modal-count">{prereqs.length}</span>
              </button>
              {openSections.prereqs && (
                <div className="lc-modal-prereqs">
                  {prereqs.map((p, i) => (
                    <div key={i} className="lc-modal-prereq">
                      <span className="lc-modal-prereq-name">{p.name}</span>
                      <span className={`lc-modal-prereq-type lc-modal-prereq-type--${p.type}`}>{p.type}</span>
                      <span className="lc-modal-prereq-desc">{p.description}</span>
                      {p.example_value && <code className="lc-modal-prereq-example">{p.example_value}</code>}
                      {p.how_to_obtain && <div className="lc-modal-prereq-how">{p.how_to_obtain}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {(flowComponents.length > 0 || flowEdges.length > 0) && (
            <div className="lc-modal-section">
              <button className="lc-modal-section-toggle" onClick={() => toggle('dataFlows')}>
                {openSections.dataFlows ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                <span>{t('lifecycle.dataFlows', 'Integration Data Flows')}</span>
                <span className="lc-modal-count">{flowComponents.length} / {flowEdges.length}</span>
              </button>
              {openSections.dataFlows && (
                <div className="lc-data-flows">
                  {flowMermaid && <MermaidDiagram chart={flowMermaid} className="lc-data-flows-diagram" />}
                  {flowComponents.length > 0 && (
                    <table className="lc-data-flows-table">
                      <thead><tr><th>{t('lifecycle.dfComponent', 'Component')}</th><th>{t('lifecycle.dfType', 'Type')}</th><th>{t('lifecycle.dfDescription', 'Description')}</th></tr></thead>
                      <tbody>
                        {flowComponents.map((c, i) => (
                          <tr key={i}>
                            <td><strong>{c.name}</strong></td>
                            <td><span className={`lc-df-type lc-df-type--${c.type}`}>{c.type}</span></td>
                            <td>{c.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  {flowEdges.length > 0 && (
                    <table className="lc-data-flows-table">
                      <thead><tr><th>{t('lifecycle.dfFrom', 'From')}</th><th></th><th>{t('lifecycle.dfTo', 'To')}</th><th>{t('lifecycle.dfLabel', 'Data')}</th><th>{t('lifecycle.dfProtocol', 'Protocol')}</th></tr></thead>
                      <tbody>
                        {flowEdges.map((f, i) => (
                          <tr key={i}>
                            <td><code>{f.from}</code></td>
                            <td className="lc-df-arrow">→</td>
                            <td><code>{f.to}</code></td>
                            <td>{f.label}</td>
                            <td><span className="lc-df-protocol">{f.protocol}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          )}

          {phases.length > 0 && (
            <div className="lc-modal-section">
              <button className="lc-modal-section-toggle" onClick={() => toggle('phases')}>
                {openSections.phases ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                <span>{t('lifecycle.phases')}</span>
                <span className="lc-modal-count">{phases.length}</span>
              </button>
              {openSections.phases && (
                <div className="lc-modal-phases">
                  {[...phases].sort((a: { step_order: number }, b: { step_order: number }) => a.step_order - b.step_order).map((p, i) => (
                    <div key={i} className={`lc-modal-phase lc-modal-phase--${p.phase_name}`}>
                      <div className="lc-modal-phase-head">
                        <span className="lc-modal-phase-order">{p.step_order}</span>
                        <span className="lc-modal-phase-name">{p.phase_name}</span>
                        <span className="lc-modal-phase-action">{p.action}</span>
                        {p.is_required && <span className="lc-modal-phase-req">{t('lifecycle.required', 'REQ')}</span>}
                      </div>
                      {p.api_call && <code className="lc-modal-phase-api">{p.api_call}</code>}
                      {p.notes && <div className="lc-modal-phase-notes">{p.notes}</div>}
                      <div className="lc-modal-phase-io">
                        {p.inputs?.length > 0 && <span className="lc-modal-io-in">← {p.inputs.join(', ')}</span>}
                        {p.outputs?.length > 0 && <span className="lc-modal-io-out">→ {p.outputs.join(', ')}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {dataModels.length > 0 && (
            <div className="lc-modal-section">
              <button className="lc-modal-section-toggle" onClick={() => toggle('dataModels')}>
                {openSections.dataModels ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                <span>{t('lifecycle.dataModels', 'Data Models')}</span>
                <span className="lc-modal-count">{dataModels.length}</span>
              </button>
              {openSections.dataModels && (
                <div className="lc-modal-models">
                  {dataModels.map((md, i) => (
                    <details key={i} className="lc-modal-model-card">
                      <summary>
                        <strong>{md.model_name}</strong>
                        <span className={`lc-modal-direction lc-modal-direction--${md.direction}`}>{md.direction}</span>
                        {md.content_type && <span className="lc-modal-ct">{md.content_type}</span>}
                        <span className="lc-modal-count">{md.fields?.length ?? 0} {t('lifecycle.fields_many', 'fields')}</span>
                      </summary>
                      {(md.used_in?.length ?? 0) > 0 && <div className="lc-modal-model-used">{t('lifecycle.usedBy', { list: md.used_in!.join(', ') })}</div>}
                      <table className="lc-modal-fields-table">
                        <thead><tr><th>{t('lifecycle.thField', 'Field')}</th><th>{t('lifecycle.thType', 'Type')}</th><th>{t('lifecycle.thReq', 'Req')}</th><th>{t('lifecycle.thDescription', 'Description')}</th></tr></thead>
                        <tbody>
                          {(md.fields || []).map((f: { name: string; type: string; constraints?: string; required?: boolean; description?: string; example_value?: string }, j: number) => (
                            <tr key={j}>
                              <td><code>{f.name}</code></td>
                              <td>{f.type}{f.constraints ? <small> ({f.constraints})</small> : ''}</td>
                              <td>{f.required ? '✓' : ''}</td>
                              <td>{f.description}{f.example_value ? <> — <code>{f.example_value}</code></> : ''}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </details>
                  ))}
                </div>
              )}
            </div>
          )}

          {errorCatalog.length > 0 && (
            <div className="lc-modal-section">
              <button className="lc-modal-section-toggle" onClick={() => toggle('errors')}>
                {openSections.errors ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                <span>{t('lifecycle.errorHandling', 'Error Handling')}</span>
                <span className="lc-modal-count">{errorCatalog.length}</span>
              </button>
              {openSections.errors && (
                <table className="lc-modal-errors-table">
                  <thead><tr><th>{t('lifecycle.thStatus', 'Status')}</th><th>{t('lifecycle.thCode', 'Code')}</th><th>{t('lifecycle.thMeaning', 'Meaning')}</th><th>{t('lifecycle.thRecovery', 'Recovery')}</th></tr></thead>
                  <tbody>
                    {errorCatalog.map((e: { http_status: number; error_code?: string; meaning: string; recovery_action: string; retry_after_seconds?: number }, i: number) => (
                      <tr key={i}>
                        <td><strong>{e.http_status}</strong></td>
                        <td>{e.error_code || '—'}</td>
                        <td>{e.meaning}</td>
                        <td><span className={`lc-modal-recovery lc-modal-recovery--${e.recovery_action}`}>{e.recovery_action}</span>
                          {e.retry_after_seconds ? ` (${e.retry_after_seconds}s)` : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {accessPatterns.length > 0 && (
            <div className="lc-modal-section">
              <button className="lc-modal-section-toggle" onClick={() => toggle('accessPatterns')}>
                {openSections.accessPatterns ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                <span>{t('lifecycle.accessPatterns', 'Data Access Patterns')}</span>
                <span className="lc-modal-count">{accessPatterns.length}</span>
              </button>
              {openSections.accessPatterns && (
                <div className="lc-modal-patterns">
                  {accessPatterns.map((ap: { pattern_type: string; endpoint: string; mechanism: string; code_hint?: string }, i: number) => (
                    <div key={i} className="lc-modal-pattern">
                      <strong className="lc-modal-pattern-type">{ap.pattern_type}</strong>
                      <code>{ap.endpoint}</code>
                      <span>{ap.mechanism}</span>
                      {ap.code_hint && <pre className="lc-modal-pattern-code">{ap.code_hint}</pre>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {patterns.length > 0 && (
            <div className="lc-modal-section">
              <button className="lc-modal-section-toggle" onClick={() => toggle('patterns')}>
                {openSections.patterns ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                <span>{t('lifecycle.patterns')}</span>
                <span className="lc-modal-count">{patterns.length}</span>
              </button>
              {openSections.patterns && (
                <div className="lc-modal-patterns">
                  {patterns.map((p: { pattern: string; description: string; code_hint?: string }, i: number) => (
                    <div key={i} className="lc-modal-pattern">
                      <strong>{p.pattern}</strong>
                      <span>{p.description}</span>
                      {p.code_hint && <code className="lc-modal-code-hint">{p.code_hint}</code>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {deps.length > 0 && (
            <div className="lc-modal-section">
              <button className="lc-modal-section-toggle" onClick={() => toggle('deps')}>
                {openSections.deps ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                <span>{t('lifecycle.dependencies')}</span>
                <span className="lc-modal-count">{deps.length}</span>
              </button>
              {openSections.deps && (
                <div className="lc-modal-deps">
                  {deps.map((d: { from_action: string; to_action: string; data_flow: string }, i: number) => (
                    <div key={i} className="lc-modal-dep">
                      <span className="lc-modal-dep-from">{d.from_action}</span>
                      <span className="lc-modal-dep-arrow">→</span>
                      <span className="lc-modal-dep-to">{d.to_action}</span>
                      <span className="lc-modal-dep-flow">{d.data_flow}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {lc.code_skeleton && (
            <div className="lc-modal-section">
              <button className="lc-modal-section-toggle" onClick={() => toggle('skeleton')}>
                {openSections.skeleton ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                <span>{t('lifecycle.codeSkeleton')}</span>
              </button>
              {openSections.skeleton && (
                <SkeletonCodeViewer
                  pythonSkeleton={lc.code_skeleton}
                  staticTranslations={lc.code_skeleton_translations}
                />
              )}
            </div>
          )}

          {coverage.length > 0 && (
            <div className="lc-modal-section">
              <button className="lc-modal-section-toggle" onClick={() => toggle('coverage')}>
                {openSections.coverage ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                <span>{t('lifecycle.endpointCoverage', 'Endpoint Coverage')}</span>
                <span className="lc-modal-count">{coverage.length}</span>
              </button>
              {openSections.coverage && (
                <table className="lc-modal-coverage-table">
                  <thead><tr><th>{t('lifecycle.thEndpoint', 'Endpoint')}</th><th>{t('lifecycle.thReqBody', 'Req')}</th><th>{t('lifecycle.thResp', 'Resp')}</th><th>{t('lifecycle.thErr', 'Err')}</th><th>{t('lifecycle.thEx', 'Ex')}</th><th>{t('lifecycle.thScore', 'Score')}</th></tr></thead>
                  <tbody>
                    {coverage.map((e: { method: string; endpoint: string; has_request_body_docs: boolean; has_response_docs: boolean; has_error_docs: boolean; has_example: boolean; completeness: number }, i: number) => (
                      <tr key={i} className={e.completeness < 0.5 ? 'lc-modal-coverage-low' : ''}>
                        <td><code>{e.method} {e.endpoint}</code></td>
                        <td>{e.has_request_body_docs ? '✓' : '✗'}</td>
                        <td>{e.has_response_docs ? '✓' : '✗'}</td>
                        <td>{e.has_error_docs ? '✓' : '✗'}</td>
                        <td>{e.has_example ? '✓' : '✗'}</td>
                        <td>
                          <div className="lc-modal-coverage-bar">
                            <div className={`lc-modal-coverage-fill lc-modal-coverage-fill--${e.completeness >= 0.75 ? 'good' : e.completeness >= 0.5 ? 'partial' : 'low'}`} style={{ width: `${e.completeness * 100}%` }} />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {issues.length > 0 && (
            <div className="lc-modal-section">
              <button className="lc-modal-section-toggle lc-modal-issues-title" onClick={() => toggle('issues')}>
                {openSections.issues ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                <AlertTriangle size={15} />
                <span>{t('lifecycle.docIssues')}</span>
                <span className="lc-modal-count">{issues.length}</span>
              </button>
              {openSections.issues && (
                <div className="lc-modal-issues">
                  {issues.map((issue, i) => (
                    <div key={i} className={`lc-modal-issue lc-modal-issue--${issue.severity}`}>
                      <span className="lc-modal-issue-type">{issue.issue_type}</span>
                      <span>{issue.description}</span>
                      {issue.suggestion && <div className="lc-modal-issue-suggestion">→ {issue.suggestion}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </>
  )
}

type TabId = 'merged' | `doc-${number}`

export function ProductLifecycleModal({ productId, productName, canRun = false, onClose, onDeleted, onAnalyzed }: Props) {
  const { t } = useTranslation()
  const [data, setData] = useState<ProductLifecycle | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [launching, setLaunching] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showShare, setShowShare] = useState(false)
  const [activeTab, setActiveTab] = useState<TabId>('merged')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback((silent = false) => {
    if (!silent) { setLoading(true); setError(null) }
    getProductLifecycle(productId)
      .then(d => { setData(d); setError(null) })
      .catch(err => { if (!silent) { setData(null); setError(err?.message || 'Failed to load') } })
      .finally(() => { if (!silent) setLoading(false) })
  }, [productId])

  useEffect(() => { load() }, [load])

  const hasRunningDocs = (data?.document_lifecycles?.some(
    d => d.status === 'pending' || d.status === 'processing'
  ) || (data?.processing_documents ?? 0) > 0)

  useEffect(() => {
    if (hasRunningDocs) {
      pollRef.current = setInterval(() => load(true), POLL_INTERVAL)
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [hasRunningDocs, load])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const analysisRunning = hasRunningDocs || launching

  const handleRun = async () => {
    if (analysisRunning) return
    setLaunching(true)
    try {
      await analyzeProductLifecycle(productId)
      onAnalyzed?.()
      setTimeout(() => load(true), 2000)
    } catch {
      load(true)
    } finally { setLaunching(false) }
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await deleteProductLifecycle(productId)
      setData(null)
      onDeleted?.()
    } catch (err) {
      console.error('Failed to delete product lifecycle:', err)
    } finally {
      setDeleting(false)
      onClose()
    }
  }

  const m = data?.merged
  const hasResults = m && m.status === 'ready'
  const docLcs = data?.document_lifecycles ?? []
  const readyDocLcs = docLcs.filter(d => d.status === 'ready')
  const hasDocAnalyses = docLcs.length > 0
  const hasAnything = hasResults || hasDocAnalyses

  const readyDocs = readyDocLcs.length
  const errorDocs = docLcs.filter(d => d.status === 'error').length
  const runningDocs = docLcs.filter(d => d.status === 'pending' || d.status === 'processing').length

  const showTabs = hasResults && readyDocLcs.length > 1

  const totalUsage: AggregatedUsage = useMemo(() => {
    let pt = 0, ct = 0, ms = 0
    for (const dl of readyDocLcs) {
      pt += dl.prompt_tokens ?? 0
      ct += dl.completion_tokens ?? 0
      ms += dl.analysis_ms ?? 0
    }
    if (m) {
      pt += m.prompt_tokens ?? 0
      ct += m.completion_tokens ?? 0
      ms += m.analysis_ms ?? 0
    }
    return { prompt_tokens: pt, completion_tokens: ct, analysis_ms: ms }
  }, [readyDocLcs, m])

  const activeDocLc = activeTab !== 'merged'
    ? docLcs.find(d => `doc-${d.document_id}` === activeTab) ?? null
    : null

  const issues = data?.doc_issues ?? []
  const activeIssues = activeTab === 'merged'
    ? issues
    : issues.filter(i => activeDocLc && i.document_id === activeDocLc.document_id)

  return (
    <div className="confirm-overlay" onClick={onClose}>
      <div
        className={`md-preview-dialog${fullscreen ? ' md-preview-dialog--fullscreen' : ''}`}
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-labelledby="plc-modal-title"
      >
        <div className="md-preview-header">
          <div className="md-preview-title-row">
            <Activity size={18} />
            <h3 id="plc-modal-title" className="md-preview-title">
              {t('lifecycleModal.title')}: {productName}
            </h3>
          </div>
          <div className="md-preview-header-actions">
            {canRun && !loading && !error && (
              <>
                <button
                  className="lc-modal-run-btn"
                  onClick={handleRun}
                  disabled={analysisRunning}
                  title={analysisRunning ? t('lifecycleModal.alreadyRunning') :
                         hasResults ? t('lifecycle.rerun') : t('lifecycle.run')}
                >
                  {analysisRunning ? <Loader2 size={13} className="spin-icon" /> :
                   hasResults ? <RefreshCw size={13} /> : <Play size={13} />}
                  <span>
                    {analysisRunning ? t('lifecycleModal.running') :
                     hasResults ? t('lifecycle.rerun') : t('lifecycle.run')}
                  </span>
                </button>
                {hasAnything && (
                  <>
                    {hasResults && (
                      <button
                        className="lc-modal-share-btn"
                        onClick={() => setShowShare(true)}
                        title={t('share.shareLifecycle')}
                      >
                        <Share2 size={13} />
                      </button>
                    )}
                    <button
                      className="lc-modal-delete-btn"
                      onClick={() => setShowDeleteConfirm(true)}
                      disabled={deleting || analysisRunning}
                      title={t('lifecycleModal.delete')}
                    >
                      {deleting ? <Loader2 size={13} className="spin-icon" /> : <Trash2 size={13} />}
                    </button>
                  </>
                )}
              </>
            )}
            <button className="md-preview-close-btn" onClick={() => setFullscreen(f => !f)}>
              {fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
            <button className="md-preview-close-btn" onClick={onClose}>
              <X size={14} />
            </button>
          </div>
        </div>

        <div className="md-preview-body">
          {loading && (
            <div className="md-preview-placeholder">
              <Loader2 size={32} className="spin-icon" />
              <span>{t('lifecycleModal.loading')}</span>
            </div>
          )}
          {error && (
            <div className="md-preview-placeholder md-preview-placeholder--error">
              <AlertCircle size={32} />
              <span>{error}</span>
            </div>
          )}

          {!loading && !error && !hasAnything && !analysisRunning && (
            <div className="lc-modal-empty">
              <Activity size={40} className="lc-modal-empty-icon" />
              <p>{canRun ? t('products.lifecycle.notAnalyzed') : t('lifecycleModal.notAnalyzedNoAccess')}</p>
              {canRun && (
                <button className="lc-modal-run-btn lc-modal-run-btn--large" onClick={handleRun} disabled={analysisRunning}>
                  {launching ? <Loader2 size={14} className="spin-icon" /> : <Play size={14} />}
                  {t('lifecycle.run')}
                </button>
              )}
            </div>
          )}

          {!loading && !error && m?.status === 'error' && !analysisRunning && (
            <div className="lc-modal-error-block">
              <AlertCircle size={40} />
              <p className="lc-modal-error-block-title">{t('lifecycleModal.analysisFailed')}</p>
              {m.error_message && <p className="lc-modal-error-block-msg">{m.error_message}</p>}
              {canRun && (
                <button className="lc-modal-run-btn lc-modal-run-btn--large" onClick={handleRun} disabled={analysisRunning}>
                  <RefreshCw size={14} />
                  {t('lifecycle.rerun')}
                </button>
              )}
            </div>
          )}

          {!loading && !error && analysisRunning && !hasResults && (
            <div className="lc-modal-in-progress">
              <Loader2 size={40} className="spin-icon" />
              <p className="lc-modal-in-progress-title">{t('lifecycleModal.inProgress')}</p>
              <p className="lc-modal-in-progress-hint">{t('products.lifecycle.inProgressHint')}</p>
              {(docLcs.length > 0 || (data?.processing_documents ?? 0) > 0) && (
                <div className="plc-modal-doc-progress">
                  <span className="plc-doc-ready">{readyDocs} {t('lifecycle.status.ready').toLowerCase()}</span>
                  {(runningDocs + (data?.processing_documents ?? 0)) > 0 && (
                    <span className="plc-doc-running">
                      {runningDocs + (data?.processing_documents ?? 0)} {t('lifecycle.status.processing').toLowerCase()}
                    </span>
                  )}
                  {errorDocs > 0 && <span className="plc-doc-error">{errorDocs} {t('lifecycle.status.error').toLowerCase()}</span>}
                </div>
              )}
              <div className="lc-modal-progress-bar">
                <div className="lc-modal-progress-fill" />
              </div>
            </div>
          )}

          {!loading && !error && (hasResults || (hasDocAnalyses && !analysisRunning)) && (
            <div className="lc-modal-content">
              {docLcs.length > 0 && (
                <div className="plc-modal-doc-summary">
                  <span className="plc-doc-label">{t('products.lifecycle.documentsAnalyzed')}:</span>
                  <span className="plc-doc-ready">{readyDocs} ✓</span>
                  {errorDocs > 0 && <span className="plc-doc-error">{errorDocs} ✗</span>}
                  <span className="plc-doc-total">/ {docLcs.length}</span>
                </div>
              )}

              {showTabs && (
                <div className="plc-tabs" role="tablist">
                  <button
                    className={`plc-tab${activeTab === 'merged' ? ' plc-tab--active' : ''}`}
                    role="tab"
                    aria-selected={activeTab === 'merged'}
                    onClick={() => setActiveTab('merged')}
                  >
                    <Layers size={13} />
                    <span>{t('lifecycleModal.tabMerged', 'Merged')}</span>
                  </button>
                  {readyDocLcs.map(dl => (
                    <button
                      key={dl.document_id}
                      className={`plc-tab${activeTab === `doc-${dl.document_id}` ? ' plc-tab--active' : ''}`}
                      role="tab"
                      aria-selected={activeTab === `doc-${dl.document_id}`}
                      onClick={() => setActiveTab(`doc-${dl.document_id}`)}
                      title={dl.document_name || `Document ${dl.document_id}`}
                    >
                      <FileText size={13} />
                      <span className="plc-tab-label">{dl.document_name || `Doc ${dl.document_id}`}</span>
                    </button>
                  ))}
                </div>
              )}

              {showTabs && activeTab === 'merged' && m && (
                <LifecycleContent lc={m} productId={productId} issues={activeIssues} aggregatedUsage={totalUsage} />
              )}

              {showTabs && activeTab !== 'merged' && activeDocLc && (
                <LifecycleContent lc={activeDocLc} productId={productId} documentId={activeDocLc.document_id} issues={activeIssues} />
              )}

              {!showTabs && m && (
                <LifecycleContent lc={m} productId={productId} issues={issues} aggregatedUsage={totalUsage} />
              )}

              {!showTabs && !m && readyDocLcs.length === 1 && (
                <LifecycleContent lc={readyDocLcs[0]} productId={productId} documentId={readyDocLcs[0].document_id} issues={activeIssues} aggregatedUsage={totalUsage} />
              )}
            </div>
          )}
        </div>
      </div>

      {showDeleteConfirm && (
        <ConfirmDialog
          title={t('products.lifecycle.deleteTitle')}
          message={t('products.lifecycle.deleteMessage')}
          details={productName}
          confirmLabel={t('products.lifecycle.deleteConfirm')}
          cancelLabel={t('products.delete.cancel', 'Отмена')}
          variant="danger"
          onConfirm={() => { setShowDeleteConfirm(false); handleDelete() }}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      )}

      {showShare && (
        <ShareModal type="lifecycle" id={productId} onClose={() => setShowShare(false)} />
      )}
    </div>
  )
}
