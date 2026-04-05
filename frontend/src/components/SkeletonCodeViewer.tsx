import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check, Download, Loader2 } from 'lucide-react'
import {
  convertSkeletonLanguage,
  SKELETON_LANGUAGES,
  type SkeletonLanguage,
} from '../api/products'

const LS_KEY = 'lexiro-skeleton-lang'

function getDefaultLang(available: Set<string>): SkeletonLanguage {
  try {
    const saved = localStorage.getItem(LS_KEY) as SkeletonLanguage | null
    if (saved && available.has(saved)) return saved
  } catch { /* SSR / private mode */ }
  return available.has('curl') ? 'curl' : 'python'
}

interface Props {
  productId?: number
  documentId?: number
  pythonSkeleton: string
  /** Pre-cached translations from share snapshot — no API calls when provided */
  staticTranslations?: Partial<Record<string, string>>
}

export function SkeletonCodeViewer({ productId, documentId, pythonSkeleton, staticTranslations }: Props) {
  const { t } = useTranslation()
  const readOnly = !productId

  const initialCache: Partial<Record<SkeletonLanguage, string>> = {
    python: pythonSkeleton,
    ...staticTranslations as Partial<Record<SkeletonLanguage, string>>,
  }
  const availableSet = new Set(Object.keys(initialCache).filter(k => initialCache[k as SkeletonLanguage]))
  if (!readOnly) SKELETON_LANGUAGES.forEach(l => availableSet.add(l.id))

  const [activeLang, setActiveLang] = useState<SkeletonLanguage>(() => getDefaultLang(availableSet))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const cache = useRef<Partial<Record<SkeletonLanguage, string>>>({
    python: pythonSkeleton,
    ...staticTranslations as Partial<Record<SkeletonLanguage, string>>,
  })

  useEffect(() => {
    cache.current.python = pythonSkeleton
    if (staticTranslations) {
      for (const [k, v] of Object.entries(staticTranslations)) {
        if (v) cache.current[k as SkeletonLanguage] = v
      }
    }
  }, [pythonSkeleton, staticTranslations])

  const displayedCode = cache.current[activeLang] ?? ''
  const syntaxLang = SKELETON_LANGUAGES.find(l => l.id === activeLang)?.syntaxId ?? 'text'

  const availableLangs = readOnly
    ? SKELETON_LANGUAGES.filter(l => l.id === 'python' || cache.current[l.id])
    : SKELETON_LANGUAGES

  const handleLangChange = useCallback(async (lang: SkeletonLanguage) => {
    setActiveLang(lang)
    setError(null)
    try { localStorage.setItem(LS_KEY, lang) } catch { /* ignore */ }
    if (cache.current[lang]) return

    if (readOnly || !productId) return

    setLoading(true)
    try {
      const result = await convertSkeletonLanguage(productId, lang, documentId)
      cache.current[lang] = result.code
    } catch (e: any) {
      setError(e.message ?? t('lifecycle.skeletonConvertError', 'Conversion failed'))
    } finally {
      setLoading(false)
    }
  }, [productId, documentId, readOnly, t])

  const handleCopy = useCallback(async () => {
    if (!displayedCode) return
    await navigator.clipboard.writeText(displayedCode)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [displayedCode])

  const handleDownload = useCallback(() => {
    if (!displayedCode) return
    const ext: Record<SkeletonLanguage, string> = {
      python: '.py', csharp: '.cs', cpp: '.cpp', go: '.go',
      curl: '.sh', java: '.java', javascript: '.js',
    }
    const blob = new Blob([displayedCode], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `api_skeleton${ext[activeLang] ?? '.txt'}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [displayedCode, activeLang])

  return (
    <div className="skeleton-viewer">
      <div className="skeleton-viewer-toolbar">
        <div className="skeleton-lang-tabs">
          {availableLangs.map(lang => (
            <button
              key={lang.id}
              className={`skeleton-lang-tab${activeLang === lang.id ? ' skeleton-lang-tab--active' : ''}`}
              onClick={() => handleLangChange(lang.id)}
              disabled={loading}
            >
              {lang.label}
            </button>
          ))}
        </div>
        <div className="skeleton-viewer-actions">
          <button className="skeleton-action-btn" onClick={handleCopy} title={t('code.copy')}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          <button className="skeleton-action-btn" onClick={handleDownload} title={t('code.download')}>
            <Download size={14} />
          </button>
        </div>
      </div>

      {loading && (
        <div className="skeleton-viewer-loading">
          <Loader2 size={18} className="spin-icon" />
          <span>{t('lifecycle.skeletonConverting', 'Converting…')}</span>
        </div>
      )}

      {error && !loading && (
        <div className="skeleton-viewer-error">{error}</div>
      )}

      {!loading && !error && displayedCode && (
        <SyntaxHighlighter
          language={syntaxLang}
          style={oneDark}
          customStyle={{ margin: 0, fontSize: '11px', lineHeight: '1.5', padding: '12px 16px', borderRadius: '0 0 6px 6px', maxHeight: 400, overflow: 'auto' }}
        >
          {displayedCode}
        </SyntaxHighlighter>
      )}

      {!loading && !error && !displayedCode && (
        <div className="skeleton-viewer-empty">{t('lifecycle.skeletonEmpty', 'No code available')}</div>
      )}
    </div>
  )
}
