import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Save, Eye, RotateCcw, Trash2 } from 'lucide-react'
import {
  getPrompt, patchPrompt, deletePrompt, previewPrompt, seedPrompts,
  type PromptTemplateDetail, type PromptPreview,
} from '../../api/admin'

export function PromptEditorPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [prompt, setPrompt] = useState<PromptTemplateDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const [body, setBody] = useState('')
  const [classifierHint, setClassifierHint] = useState('')
  const [maxTokens, setMaxTokens] = useState('')
  const [ragTopK, setRagTopK] = useState('')
  const [preview, setPreview] = useState<PromptPreview | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const p = await getPrompt(Number(id))
      setPrompt(p)
      setBody(p.body)
      setClassifierHint(p.classifier_hint)
      setMaxTokens(p.max_response_tokens != null ? String(p.max_response_tokens) : '')
      setRagTopK(p.rag_top_k != null ? String(p.rag_top_k) : '')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const handleSave = async () => {
    if (!id) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const updated = await patchPrompt(Number(id), {
        body,
        classifier_hint: classifierHint,
        max_response_tokens: maxTokens ? Number(maxTokens) : null,
        rag_top_k: ragTopK ? Number(ragTopK) : null,
      })
      setPrompt(updated)
      setSuccess('Saved')
      setTimeout(() => setSuccess(''), 2000)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handlePreview = async () => {
    if (!id) return
    try {
      const p = await previewPrompt(Number(id))
      setPreview(p)
    } catch (e: any) {
      setError(e.message)
    }
  }

  const handleResetToDefault = async () => {
    if (!confirm('Reset this prompt to the file-based default? Your customizations will be lost.')) return
    try {
      await seedPrompts()
      await load()
      setSuccess('Reset to default')
      setTimeout(() => setSuccess(''), 2000)
    } catch (e: any) {
      setError(e.message)
    }
  }

  const handleDelete = async () => {
    if (!id || !prompt) return
    if (!confirm(`Delete this prompt override for "${prompt.query_type}"?`)) return
    try {
      await deletePrompt(Number(id))
      navigate('/app/admin/prompts')
    } catch (e: any) {
      setError(e.message)
    }
  }

  if (loading) return <div className="admin-loading">Loading...</div>
  if (!prompt) return <div className="admin-error">Prompt not found</div>

  const isOverride = prompt.role_id !== null

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <button className="btn" onClick={() => navigate('/app/admin/prompts')}>
          <ArrowLeft size={14} /> Back
        </button>
        <h1>
          <code>{prompt.query_type}</code>
          {isOverride && <span className="admin-badge"> role: {prompt.role_slug}</span>}
          {prompt.is_system && <span className="admin-badge admin-badge--info"> system</span>}
        </h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={handlePreview}>
            <Eye size={14} /> Preview
          </button>
          {prompt.is_system && prompt.is_customized && (
            <button className="btn" onClick={handleResetToDefault}>
              <RotateCcw size={14} /> Reset
            </button>
          )}
          {!prompt.is_system && (
            <button className="btn btn-danger" onClick={handleDelete}>
              <Trash2 size={14} /> Delete
            </button>
          )}
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            <Save size={14} /> {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      {error && <div className="admin-error">{error}</div>}
      {success && <div className="admin-success">{success}</div>}

      <div className="admin-card">
        <h3>Prompt Body</h3>
        <textarea
          className="admin-prompt-editor"
          value={body}
          onChange={e => setBody(e.target.value)}
          rows={20}
          spellCheck={false}
        />
      </div>

      <div className="admin-card">
        <h3>Settings</h3>
        <div className="admin-form-row">
          <label>Classifier Hint</label>
          <input
            value={classifierHint}
            onChange={e => setClassifierHint(e.target.value)}
            placeholder="e.g. general question about a product"
          />
          <small>Used by the LLM classifier to determine query type</small>
        </div>
        <div className="admin-form-row">
          <label>Max Response Tokens</label>
          <input
            type="number"
            value={maxTokens}
            onChange={e => setMaxTokens(e.target.value)}
            placeholder="inherit from base"
          />
        </div>
        <div className="admin-form-row">
          <label>RAG Top K</label>
          <input
            type="number"
            value={ragTopK}
            onChange={e => setRagTopK(e.target.value)}
            placeholder="inherit from base"
          />
        </div>
      </div>

      {preview && (
        <div className="admin-card">
          <h3>Resolved Preview</h3>
          <div className="admin-form-row">
            <label>Classifier Hint</label>
            <div>{preview.resolved_classifier_hint || '—'}</div>
          </div>
          <div className="admin-form-row">
            <label>Max Tokens: {preview.resolved_max_response_tokens ?? 'default'}</label>
            <label>RAG Top K: {preview.resolved_rag_top_k ?? 'default'}</label>
          </div>
          <h4>Resolved Body</h4>
          <pre className="admin-json-preview">{preview.resolved_body}</pre>
        </div>
      )}
    </div>
  )
}
