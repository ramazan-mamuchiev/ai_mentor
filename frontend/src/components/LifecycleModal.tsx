import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  X, Loader2, AlertCircle, Activity, Maximize2, Minimize2,
  Play, RefreshCw, ChevronDown, ChevronUp, AlertTriangle, CheckCircle, XCircle,
} from 'lucide-react'
import { getDocumentLifecycle, analyzeDocumentLifecycle } from '../api/documents'
import type { DocumentLifecycle } from '../api/documents'

const POLL_INTERVAL = 3000

interface Props {
  documentId: number
  documentTitle: string
  canRun?: boolean
  onClose: () => void
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

export function LifecycleModal({ documentId, documentTitle, canRun = false, onClose }: Props) {
  const { t } = useTranslation()
  const [lc, setLc] = useState<DocumentLifecycle | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [launching, setLaunching] = useState(false)
  const [phasesOpen, setPhasesOpen] = useState(true)
  const [skeletonOpen, setSkeletonOpen] = useState(false)
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

  const hasData = lc && lc.status !== 'not_analyzed'
  const hasResults = hasData && !isInProgress(lc?.status)
  const phases = lc?.phases ?? []
  const patterns = lc?.unique_patterns ?? []
  const deps = lc?.dependency_chains ?? []
  const issues = lc?.doc_issues ?? []

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

              {phases.length > 0 && (
                <div className="lc-modal-section">
                  <button className="lc-modal-section-toggle" onClick={() => setPhasesOpen(v => !v)}>
                    {phasesOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    <span>{t('lifecycle.phases')}</span>
                    <span className="lc-modal-count">{phases.length}</span>
                  </button>
                  {phasesOpen && (
                    <div className="lc-modal-phases">
                      {[...phases].sort((a, b) => a.step_order - b.step_order).map((p, i) => (
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
                            {p.inputs.length > 0 && <span className="lc-modal-io-in">← {p.inputs.join(', ')}</span>}
                            {p.outputs.length > 0 && <span className="lc-modal-io-out">→ {p.outputs.join(', ')}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {patterns.length > 0 && (
                <div className="lc-modal-section">
                  <div className="lc-modal-section-title">
                    {t('lifecycle.patterns')} <span className="lc-modal-count">{patterns.length}</span>
                  </div>
                  <div className="lc-modal-patterns">
                    {patterns.map((p, i) => (
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
                    {deps.map((d, i) => (
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

              {lc.code_skeleton && (
                <div className="lc-modal-section">
                  <button className="lc-modal-section-toggle" onClick={() => setSkeletonOpen(v => !v)}>
                    {skeletonOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    <span>{t('lifecycle.codeSkeleton')}</span>
                  </button>
                  {skeletonOpen && (
                    <pre className="lc-modal-skeleton">{lc.code_skeleton}</pre>
                  )}
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
