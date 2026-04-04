import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  X, Loader2, AlertCircle, Activity, Maximize2, Minimize2,
  Play, RefreshCw, ChevronDown, ChevronUp, AlertTriangle, CheckCircle, XCircle, Trash2,
} from 'lucide-react'
import { getDocumentLifecycle, analyzeDocumentLifecycle, deleteDocumentLifecycle } from '../api/documents'
import type { DocumentLifecycle } from '../api/documents'
import { ConfirmDialog } from './ConfirmDialog'
import { MermaidDiagram } from './MermaidDiagram'

const POLL_INTERVAL = 3000

interface Props {
  documentId: number
  documentTitle: string
  canRun?: boolean
  onClose: () => void
  onDeleted?: () => void
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

function isInProgress(status?: string): boolean {
  return status === 'pending' || status === 'processing'
}

export function LifecycleModal({ documentId, documentTitle, canRun = false, onClose, onDeleted }: Props) {
  const { t } = useTranslation()
  const [lc, setLc] = useState<DocumentLifecycle | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [launching, setLaunching] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    prereqs: true, dataFlows: true, phases: true, dataModels: true, errors: true,
    accessPatterns: true, patterns: true, deps: true, skeleton: false,
    coverage: true, issues: true,
  })
  const toggle = (key: string) => setOpenSections(prev => ({ ...prev, [key]: !prev[key] }))
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback((silent = false) => {
    if (!silent) { setLoading(true); setError(null) }
    getDocumentLifecycle(documentId)
      .then(data => { setLc(data); setError(null) })
      .catch(err => { if (!silent) { setLc(null); setError(err?.message || 'Failed to load') } })
      .finally(() => { if (!silent) setLoading(false) })
  }, [documentId])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (isInProgress(lc?.status)) {
      pollRef.current = setInterval(() => load(true), POLL_INTERVAL)
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [lc?.status, load])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const analysisRunning = isInProgress(lc?.status) || launching
  const canLaunch = !analysisRunning && !loading

  const handleRun = async () => {
    if (!canLaunch) return
    setLaunching(true)
    try {
      await analyzeDocumentLifecycle(documentId)
      setTimeout(() => load(true), 1500)
    } catch { /* ignore */ }
    finally { setLaunching(false) }
  }

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await deleteDocumentLifecycle(documentId)
      setLc(null)
      onDeleted?.()
      onClose()
    } catch { /* ignore */ }
    finally { setDeleting(false) }
  }

  const hasData = lc && lc.status !== 'not_analyzed'
  const hasResults = hasData && lc?.status === 'ready'
  const phases = lc?.phases ?? []
  const patterns = lc?.unique_patterns ?? []
  const deps = lc?.dependency_chains ?? []
  const issues = lc?.doc_issues ?? []
  const dataModels = lc?.data_models ?? []
  const errorCatalog = lc?.error_catalog ?? []
  const prereqs = lc?.prerequisites ?? []
  const accessPatterns = lc?.data_access_patterns ?? []
  const coverage = lc?.endpoint_coverage ?? []
  const dataFlows = lc?.integration_data_flows ?? {}
  const flowComponents = dataFlows.components ?? []
  const flowEdges = dataFlows.flows ?? []
  const flowMermaid = dataFlows.diagram_mermaid ?? ''
  const avgCompleteness = coverage.length > 0
    ? Math.round(coverage.reduce((s, e) => s + (e.completeness ?? 0), 0) / coverage.length * 100)
    : null

  return (
    <div className="confirm-overlay" onClick={onClose}>
      <div
        className={`md-preview-dialog${fullscreen ? ' md-preview-dialog--fullscreen' : ''}`}
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-labelledby="lc-modal-title"
      >
        <div className="md-preview-header">
          <div className="md-preview-title-row">
            <Activity size={18} />
            <h3 id="lc-modal-title" className="md-preview-title">
              {t('lifecycleModal.title')}: {documentTitle}
            </h3>
          </div>
          <div className="md-preview-header-actions">
            {canRun && !loading && !error && (
              <>
                <button
                  className="lc-modal-run-btn"
                  onClick={handleRun}
                  disabled={!canLaunch}
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
                {hasResults && (
                  <button
                    className="lc-modal-delete-btn"
                    onClick={() => setShowDeleteConfirm(true)}
                    disabled={deleting || analysisRunning}
                    title={t('lifecycleModal.delete')}
                  >
                    {deleting ? <Loader2 size={13} className="spin-icon" /> : <Trash2 size={13} />}
                  </button>
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

          {!loading && !error && !hasData && !analysisRunning && (
            <div className="lc-modal-empty">
              <Activity size={40} className="lc-modal-empty-icon" />
              <p>{canRun ? t('lifecycleModal.notAnalyzed') : t('lifecycleModal.notAnalyzedNoAccess')}</p>
              {canRun && (
                <button className="lc-modal-run-btn lc-modal-run-btn--large" onClick={handleRun} disabled={!canLaunch}>
                  {launching ? <Loader2 size={14} className="spin-icon" /> : <Play size={14} />}
                  {t('lifecycle.run')}
                </button>
              )}
            </div>
          )}

          {!loading && !error && hasData && lc?.status === 'error' && !analysisRunning && (
            <div className="lc-modal-error-block">
              <AlertCircle size={40} />
              <p className="lc-modal-error-block-title">{t('lifecycleModal.analysisFailed')}</p>
              {lc?.error_message && <p className="lc-modal-error-block-msg">{lc.error_message}</p>}
              {canRun && (
                <button className="lc-modal-run-btn lc-modal-run-btn--large" onClick={handleRun} disabled={!canLaunch}>
                  <RefreshCw size={14} />
                  {t('lifecycle.rerun')}
                </button>
              )}
            </div>
          )}

          {!loading && !error && analysisRunning && (
            <div className="lc-modal-in-progress">
              <Loader2 size={40} className="spin-icon" />
              <p className="lc-modal-in-progress-title">{t('lifecycleModal.inProgress')}</p>
              <p className="lc-modal-in-progress-hint">{t('lifecycleModal.inProgressHint')}</p>
              <div className="lc-modal-progress-bar">
                <div className="lc-modal-progress-fill" />
              </div>
            </div>
          )}

          {!loading && !error && hasResults && lc && (
            <div className="lc-modal-content">
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
                    Doc quality: {avgCompleteness}%
                  </span>
                )}
                {lc.model && <span className="lc-modal-model">{lc.model}</span>}
                {lc.analysis_ms != null && <span className="lc-modal-time">{(lc.analysis_ms / 1000).toFixed(1)}s</span>}
                {lc.prompt_tokens != null && (
                  <span className="lc-modal-tokens">{lc.prompt_tokens.toLocaleString()} + {(lc.completion_tokens ?? 0).toLocaleString()} tokens</span>
                )}
                {lc.validation_retries != null && lc.validation_retries > 0 && (
                  <span className="lc-modal-retries">{lc.validation_retries} {t('lifecycleModal.retries')}</span>
                )}
              </div>

              {lc.error_message && (
                <div className="lc-modal-error-msg">
                  <AlertCircle size={14} /> {lc.error_message}
                </div>
              )}

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
                    <span>Prerequisites</span>
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
                      {[...phases].sort((a, b) => a.step_order - b.step_order).map((p, i) => (
                        <div key={i} className={`lc-modal-phase lc-modal-phase--${p.phase_name}`}>
                          <div className="lc-modal-phase-head">
                            <span className="lc-modal-phase-order">{p.step_order}</span>
                            <span className="lc-modal-phase-name">{p.phase_name}</span>
                            <span className="lc-modal-phase-action">{p.action}</span>
                            {p.is_required && <span className="lc-modal-phase-req">REQ</span>}
                          </div>
                          {p.api_call && (
                            <code className="lc-modal-phase-api">
                              {p.http_method ? `${p.http_method} ` : ''}{p.api_call}
                              {p.content_type ? ` (${p.content_type})` : ''}
                            </code>
                          )}
                          {p.notes && <div className="lc-modal-phase-notes">{p.notes}</div>}
                          <div className="lc-modal-phase-io">
                            {p.inputs?.length > 0 && <span className="lc-modal-io-in">← {p.inputs.join(', ')}</span>}
                            {p.outputs?.length > 0 && <span className="lc-modal-io-out">→ {p.outputs.join(', ')}</span>}
                          </div>
                          {p.request_example && (
                            <details className="lc-modal-phase-example">
                              <summary>Request body</summary>
                              <pre>{p.request_example}</pre>
                            </details>
                          )}
                          {p.response_example && (
                            <details className="lc-modal-phase-example">
                              <summary>Response</summary>
                              <pre>{p.response_example}</pre>
                            </details>
                          )}
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
                    <span>Data Models</span>
                    <span className="lc-modal-count">{dataModels.length}</span>
                  </button>
                  {openSections.dataModels && (
                    <div className="lc-modal-models">
                      {dataModels.map((m, i) => (
                        <details key={i} className="lc-modal-model-card">
                          <summary>
                            <strong>{m.model_name}</strong>
                            <span className={`lc-modal-direction lc-modal-direction--${m.direction}`}>{m.direction}</span>
                            {m.content_type && <span className="lc-modal-ct">{m.content_type}</span>}
                            <span className="lc-modal-count">{m.fields?.length ?? 0} fields</span>
                          </summary>
                          {m.used_in?.length > 0 && <div className="lc-modal-model-used">Used by: {m.used_in.join(', ')}</div>}
                          <table className="lc-modal-fields-table">
                            <thead><tr><th>Field</th><th>Type</th><th>Req</th><th>Description</th></tr></thead>
                            <tbody>
                              {(m.fields || []).map((f, j) => (
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
                    <span>Error Handling</span>
                    <span className="lc-modal-count">{errorCatalog.length}</span>
                  </button>
                  {openSections.errors && (
                    <table className="lc-modal-errors-table">
                      <thead><tr><th>Status</th><th>Code</th><th>Meaning</th><th>Recovery</th></tr></thead>
                      <tbody>
                        {errorCatalog.map((e, i) => (
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
                    <span>Data Access Patterns</span>
                    <span className="lc-modal-count">{accessPatterns.length}</span>
                  </button>
                  {openSections.accessPatterns && (
                    <div className="lc-modal-patterns">
                      {accessPatterns.map((p, i) => (
                        <div key={i} className="lc-modal-pattern">
                          <strong className="lc-modal-pattern-type">{p.pattern_type}</strong>
                          <code>{p.endpoint}</code>
                          <span>{p.mechanism}</span>
                          {p.code_hint && <pre className="lc-modal-pattern-code">{p.code_hint}</pre>}
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
                      {patterns.map((p, i) => (
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
                      {deps.map((d, i) => (
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
                    <pre className="lc-modal-skeleton">{lc.code_skeleton}</pre>
                  )}
                </div>
              )}

              {coverage.length > 0 && (
                <div className="lc-modal-section">
                  <button className="lc-modal-section-toggle" onClick={() => toggle('coverage')}>
                    {openSections.coverage ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    <span>Endpoint Coverage</span>
                    <span className="lc-modal-count">{coverage.length}</span>
                  </button>
                  {openSections.coverage && (
                    <table className="lc-modal-coverage-table">
                      <thead><tr><th>Endpoint</th><th>Req</th><th>Resp</th><th>Err</th><th>Ex</th><th>Score</th></tr></thead>
                      <tbody>
                        {coverage.map((e, i) => (
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
            </div>
          )}
        </div>
      </div>

      {showDeleteConfirm && (
        <ConfirmDialog
          title={t('docs.lifecycle.deleteTitle')}
          message={t('docs.lifecycle.deleteMessage')}
          details={documentTitle}
          confirmLabel={t('docs.lifecycle.deleteConfirm')}
          cancelLabel={t('docs.delete.cancel', 'Отмена')}
          variant="danger"
          onConfirm={() => { setShowDeleteConfirm(false); handleDelete() }}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      )}

    </div>
  )
}
