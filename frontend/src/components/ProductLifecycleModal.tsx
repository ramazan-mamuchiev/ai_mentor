import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  X, Loader2, AlertCircle, Activity, Maximize2, Minimize2, Download,
  Play, RefreshCw, ChevronDown, ChevronUp, AlertTriangle, CheckCircle, XCircle, Trash2,
} from 'lucide-react'
import {
  getProductLifecycle, analyzeProductLifecycle, deleteProductLifecycle,
} from '../api/products'
import type { ProductLifecycle } from '../api/products'

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

export function ProductLifecycleModal({ productId, productName, canRun = false, onClose, onDeleted, onAnalyzed }: Props) {
  const { t } = useTranslation()
  const [data, setData] = useState<ProductLifecycle | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [launching, setLaunching] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [phasesOpen, setPhasesOpen] = useState(true)
  const [skeletonOpen, setSkeletonOpen] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback((silent = false) => {
    if (!silent) { setLoading(true); setError(null) }
    getProductLifecycle(productId)
      .then(d => { setData(d); setError(null) })
      .catch(err => { if (!silent) { setData(null); setError(err?.message || 'Failed to load') } })
      .finally(() => { if (!silent) setLoading(false) })
  }, [productId])

  useEffect(() => { load() }, [load])

  const hasRunningDocs = data?.document_lifecycles?.some(
    d => d.status === 'pending' || d.status === 'processing'
  ) ?? false

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
    } catch { /* ignore */ }
    finally { setLaunching(false) }
  }

  const handleDelete = async () => {
    if (!confirm(t('products.lifecycle.confirmDelete'))) return
    setDeleting(true)
    try {
      await deleteProductLifecycle(productId)
      setData(null)
      onDeleted?.()
      onClose()
    } catch { /* ignore */ }
    finally { setDeleting(false) }
  }

  const handleDownload = () => {
    if (!data?.merged) return
    const payload = {
      product: productName,
      ...data.merged,
      document_lifecycles: data.document_lifecycles,
      doc_issues: data.doc_issues,
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const safeName = productName.replace(/[^a-zA-Z0-9_\-а-яА-ЯёЁ ]/g, '').replace(/\s+/g, '_')
    a.download = `lifecycle_product_${safeName}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const m = data?.merged
  const hasResults = m && m.status === 'ready'
  const hasDocAnalyses = (data?.document_lifecycles?.length ?? 0) > 0
  const hasAnything = hasResults || hasDocAnalyses

  const phases = m?.phases ?? []
  const patterns = m?.unique_patterns ?? []
  const deps = m?.dependency_chains ?? []
  const issues = data?.doc_issues ?? []
  const dataModels = m?.data_models ?? []
  const errorCatalog = m?.error_catalog ?? []
  const prereqs = m?.prerequisites ?? []
  const accessPatterns = m?.data_access_patterns ?? []
  const coverage = m?.endpoint_coverage ?? []
  const avgCompleteness = coverage.length > 0
    ? Math.round(coverage.reduce((s: number, e: { completeness?: number }) => s + (e.completeness ?? 0), 0) / coverage.length * 100)
    : null

  const docLcs = data?.document_lifecycles ?? []
  const readyDocs = docLcs.filter(d => d.status === 'ready').length
  const errorDocs = docLcs.filter(d => d.status === 'error').length
  const runningDocs = docLcs.filter(d => d.status === 'pending' || d.status === 'processing').length

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
                        className="lc-modal-download-btn"
                        onClick={handleDownload}
                        title={t('lifecycleModal.download')}
                      >
                        <Download size={13} />
                      </button>
                    )}
                    <button
                      className="lc-modal-delete-btn"
                      onClick={handleDelete}
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

          {!loading && !error && analysisRunning && !hasResults && (
            <div className="lc-modal-in-progress">
              <Loader2 size={40} className="spin-icon" />
              <p className="lc-modal-in-progress-title">{t('lifecycleModal.inProgress')}</p>
              <p className="lc-modal-in-progress-hint">{t('products.lifecycle.inProgressHint')}</p>
              {docLcs.length > 0 && (
                <div className="plc-modal-doc-progress">
                  <span className="plc-doc-ready">{readyDocs} {t('lifecycle.status.ready').toLowerCase()}</span>
                  {runningDocs > 0 && <span className="plc-doc-running">{runningDocs} {t('lifecycle.status.processing').toLowerCase()}</span>}
                  {errorDocs > 0 && <span className="plc-doc-error">{errorDocs} {t('lifecycle.status.error').toLowerCase()}</span>}
                  <span className="plc-doc-total">/ {docLcs.length}</span>
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

              {m && (
                <div className="lc-modal-meta">
                  <StatusBadge status={m.status} />
                  {avgCompleteness !== null && (
                    <span className={`lc-modal-quality lc-modal-quality--${avgCompleteness >= 80 ? 'good' : avgCompleteness >= 50 ? 'partial' : 'low'}`}>
                      Doc quality: {avgCompleteness}%
                    </span>
                  )}
                  {m.model && <span className="lc-modal-model">{m.model}</span>}
                  {m.analysis_ms != null && <span className="lc-modal-time">{(m.analysis_ms / 1000).toFixed(1)}s</span>}
                  {m.prompt_tokens != null && (
                    <span className="lc-modal-tokens">{m.prompt_tokens.toLocaleString()} + {(m.completion_tokens ?? 0).toLocaleString()} tokens</span>
                  )}
                  {m.validation_retries != null && m.validation_retries > 0 && (
                    <span className="lc-modal-retries">{m.validation_retries} {t('lifecycleModal.retries')}</span>
                  )}
                </div>
              )}

              {prereqs.length > 0 && (
                <div className="lc-modal-section">
                  <div className="lc-modal-section-title">Prerequisites <span className="lc-modal-count">{prereqs.length}</span></div>
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
                </div>
              )}

              {phases.length > 0 && (
                <div className="lc-modal-section">
                  <button className="lc-modal-section-toggle" onClick={() => setPhasesOpen(v => !v)}>
                    {phasesOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    <span>{t('lifecycle.phases')}</span>
                    <span className="lc-modal-count">{phases.length}</span>
                  </button>
                  {phasesOpen && (
                    <div className="lc-modal-phases">
                      {[...phases].sort((a: { step_order: number }, b: { step_order: number }) => a.step_order - b.step_order).map((p, i) => (
                        <div key={i} className={`lc-modal-phase lc-modal-phase--${p.phase_name}`}>
                          <div className="lc-modal-phase-head">
                            <span className="lc-modal-phase-order">{p.step_order}</span>
                            <span className="lc-modal-phase-name">{p.phase_name}</span>
                            <span className="lc-modal-phase-action">{p.action}</span>
                            {p.is_required && <span className="lc-modal-phase-req">REQ</span>}
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
                  <div className="lc-modal-section-title">Data Models <span className="lc-modal-count">{dataModels.length}</span></div>
                  <div className="lc-modal-models">
                    {dataModels.map((md, i) => (
                      <details key={i} className="lc-modal-model-card">
                        <summary>
                          <strong>{md.model_name}</strong>
                          <span className={`lc-modal-direction lc-modal-direction--${md.direction}`}>{md.direction}</span>
                          {md.content_type && <span className="lc-modal-ct">{md.content_type}</span>}
                          <span className="lc-modal-count">{md.fields?.length ?? 0} fields</span>
                        </summary>
                        {(md.used_in?.length ?? 0) > 0 && <div className="lc-modal-model-used">Used by: {md.used_in!.join(', ')}</div>}
                        <table className="lc-modal-fields-table">
                          <thead><tr><th>Field</th><th>Type</th><th>Req</th><th>Description</th></tr></thead>
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
                </div>
              )}

              {errorCatalog.length > 0 && (
                <div className="lc-modal-section">
                  <div className="lc-modal-section-title">Error Handling <span className="lc-modal-count">{errorCatalog.length}</span></div>
                  <table className="lc-modal-errors-table">
                    <thead><tr><th>Status</th><th>Code</th><th>Meaning</th><th>Recovery</th></tr></thead>
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
                </div>
              )}

              {accessPatterns.length > 0 && (
                <div className="lc-modal-section">
                  <div className="lc-modal-section-title">Data Access Patterns <span className="lc-modal-count">{accessPatterns.length}</span></div>
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
                </div>
              )}

              {patterns.length > 0 && (
                <div className="lc-modal-section">
                  <div className="lc-modal-section-title">
                    {t('lifecycle.patterns')} <span className="lc-modal-count">{patterns.length}</span>
                  </div>
                  <div className="lc-modal-patterns">
                    {patterns.map((p: { pattern: string; description: string; code_hint?: string }, i: number) => (
                      <div key={i} className="lc-modal-pattern">
                        <strong>{p.pattern}</strong>
                        <span>{p.description}</span>
                        {p.code_hint && <code className="lc-modal-code-hint">{p.code_hint}</code>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {deps.length > 0 && (
                <div className="lc-modal-section">
                  <div className="lc-modal-section-title">
                    {t('lifecycle.dependencies')} <span className="lc-modal-count">{deps.length}</span>
                  </div>
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
                </div>
              )}

              {m?.code_skeleton && (
                <div className="lc-modal-section">
                  <button className="lc-modal-section-toggle" onClick={() => setSkeletonOpen(v => !v)}>
                    {skeletonOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    <span>{t('lifecycle.codeSkeleton')}</span>
                  </button>
                  {skeletonOpen && (
                    <pre className="lc-modal-skeleton">{m.code_skeleton}</pre>
                  )}
                </div>
              )}

              {coverage.length > 0 && (
                <div className="lc-modal-section">
                  <div className="lc-modal-section-title">Endpoint Coverage <span className="lc-modal-count">{coverage.length}</span></div>
                  <table className="lc-modal-coverage-table">
                    <thead><tr><th>Endpoint</th><th>Req</th><th>Resp</th><th>Err</th><th>Ex</th><th>Score</th></tr></thead>
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
                </div>
              )}

              {issues.length > 0 && (
                <div className="lc-modal-section">
                  <div className="lc-modal-section-title lc-modal-issues-title">
                    <AlertTriangle size={15} />
                    {t('lifecycle.docIssues')} <span className="lc-modal-count">{issues.length}</span>
                  </div>
                  <div className="lc-modal-issues">
                    {issues.map((issue, i) => (
                      <div key={i} className={`lc-modal-issue lc-modal-issue--${issue.severity}`}>
                        <span className="lc-modal-issue-type">{issue.issue_type}</span>
                        <span>{issue.description}</span>
                        {issue.suggestion && <div className="lc-modal-issue-suggestion">→ {issue.suggestion}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
