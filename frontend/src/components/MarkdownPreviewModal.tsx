import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Download, Loader2, AlertCircle, FileText, Maximize2, Minimize2, AlertTriangle, Search, ChevronUp, ChevronDown } from 'lucide-react'
import { MarkdownRenderer } from './MarkdownRenderer'
import { previewMarkdown } from '../api/documents'
import type { DocumentMarkdownPreview } from '../types'

interface Props {
  documentId: number
  documentTitle: string
  onClose: () => void
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${sizes[i]}`
}

const LARGE_FILE_THRESHOLD = 200 * 1024

const SOURCE_LABELS: Record<string, string> = {
  s3_converted: 'S3 (converted)',
  s3_original: 'S3 (original)',
  chunks_reconstructed: 'Reconstructed from chunks',
}

function highlightMatches(container: HTMLElement, query: string): HTMLElement[] {
  clearHighlights(container)
  if (!query.trim()) return []

  const marks: HTMLElement[] = []
  const lowerQuery = query.toLowerCase()
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
  const textNodes: Text[] = []
  let node: Text | null
  while ((node = walker.nextNode() as Text | null)) textNodes.push(node)

  for (const textNode of textNodes) {
    const text = textNode.nodeValue || ''
    const lowerText = text.toLowerCase()
    let idx = lowerText.indexOf(lowerQuery)
    if (idx === -1) continue

    const fragment = document.createDocumentFragment()
    let lastIdx = 0
    while (idx !== -1) {
      if (idx > lastIdx) {
        fragment.appendChild(document.createTextNode(text.slice(lastIdx, idx)))
      }
      const mark = document.createElement('mark')
      mark.className = 'md-search-highlight'
      mark.textContent = text.slice(idx, idx + query.length)
      fragment.appendChild(mark)
      marks.push(mark)
      lastIdx = idx + query.length
      idx = lowerText.indexOf(lowerQuery, lastIdx)
    }
    if (lastIdx < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(lastIdx)))
    }
    textNode.parentNode?.replaceChild(fragment, textNode)
  }
  return marks
}

function clearHighlights(container: HTMLElement) {
  const marks = container.querySelectorAll('mark.md-search-highlight')
  marks.forEach(mark => {
    const parent = mark.parentNode
    if (!parent) return
    parent.replaceChild(document.createTextNode(mark.textContent || ''), mark)
    parent.normalize()
  })
}

export function MarkdownPreviewModal({ documentId, documentTitle, onClose }: Props) {
  const { t } = useTranslation()
  const [data, setData] = useState<DocumentMarkdownPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [largeFileConfirmed, setLargeFileConfirmed] = useState(false)

  const [searchQuery, setSearchQuery] = useState('')
  const [matchCount, setMatchCount] = useState(0)
  const [currentMatch, setCurrentMatch] = useState(0)
  const contentRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const marksRef = useRef<HTMLElement[]>([])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    previewMarkdown(documentId)
      .then(result => {
        if (!cancelled) {
          setData(result)
          setLoading(false)
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err?.message || 'Failed to load preview')
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [documentId])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (searchQuery) {
          setSearchQuery('')
          if (contentRef.current) clearHighlights(contentRef.current)
          marksRef.current = []
          setMatchCount(0)
          setCurrentMatch(0)
        } else {
          onClose()
        }
        return
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault()
        searchInputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose, searchQuery])

  const scrollToMark = useCallback((mark: HTMLElement) => {
    const scrollable = bodyRef.current
    if (!scrollable) return
    const containerRect = scrollable.getBoundingClientRect()
    const markRect = mark.getBoundingClientRect()
    const targetTop = markRect.top - containerRect.top + scrollable.scrollTop - containerRect.height / 2
    scrollable.scrollTo({ top: targetTop, behavior: 'smooth' })
  }, [])

  useEffect(() => {
    if (!contentRef.current) return
    const container = contentRef.current
    const timer = setTimeout(() => {
      const marks = highlightMatches(container, searchQuery)
      marksRef.current = marks
      setMatchCount(marks.length)
      setCurrentMatch(marks.length > 0 ? 1 : 0)
      if (marks.length > 0) {
        marks[0].classList.add('md-search-highlight--active')
        scrollToMark(marks[0])
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery, scrollToMark])

  const navigateMatch = useCallback((direction: 'next' | 'prev') => {
    const marks = marksRef.current
    if (marks.length === 0) return
    const prev = currentMatch - 1
    if (prev >= 0 && prev < marks.length) {
      marks[prev].classList.remove('md-search-highlight--active')
    }
    let next: number
    if (direction === 'next') {
      next = currentMatch >= marks.length ? 1 : currentMatch + 1
    } else {
      next = currentMatch <= 1 ? marks.length : currentMatch - 1
    }
    setCurrentMatch(next)
    marks[next - 1].classList.add('md-search-highlight--active')
    scrollToMark(marks[next - 1])
  }, [currentMatch, scrollToMark])

  const clearSearch = useCallback(() => {
    setSearchQuery('')
    if (contentRef.current) clearHighlights(contentRef.current)
    marksRef.current = []
    setMatchCount(0)
    setCurrentMatch(0)
  }, [])

  const handleDownload = useCallback(() => {
    if (!data) return
    const blob = new Blob([data.markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${data.title || `document-${documentId}`}.md`
    a.click()
    URL.revokeObjectURL(url)
  }, [data, documentId])

  const showSpinner = loading
  const isLargeFile = data != null && data.size_bytes > LARGE_FILE_THRESHOLD && !largeFileConfirmed

  return (
    <div className="confirm-overlay" onClick={onClose}>
      <div
        className={`md-preview-dialog${fullscreen ? ' md-preview-dialog--fullscreen' : ''}`}
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-labelledby="md-preview-title"
      >
        <div className="md-preview-header">
          <div className="md-preview-title-row">
            <FileText size={18} />
            <h3 id="md-preview-title" className="md-preview-title">
              {t('docs.preview.title')}: {documentTitle}
            </h3>
          </div>
          <div className="md-preview-header-actions">
            {data && (
              <>
                <span className="md-preview-meta">
                  {formatBytes(data.size_bytes)} &middot; {SOURCE_LABELS[data.source] || data.source}
                </span>
                <button className="md-preview-download-btn" onClick={handleDownload}>
                  <Download size={16} />
                </button>
              </>
            )}
            <button
              className="md-preview-close-btn"
              onClick={() => setFullscreen(f => !f)}
            >
              {fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
            <button className="md-preview-close-btn" onClick={onClose}>
              <X size={14} />
            </button>
          </div>
        </div>

        <div className="md-search-bar">
          <div className="md-search-bar-inner">
            <Search size={14} className="md-search-bar-icon" />
            <input
              ref={searchInputRef}
              type="text"
              className="md-search-input"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  navigateMatch(e.shiftKey ? 'prev' : 'next')
                }
                if (e.key === 'Escape') {
                  e.preventDefault()
                  clearSearch()
                  searchInputRef.current?.blur()
                }
              }}
              placeholder={t('docs.preview.searchPlaceholder')}
              autoComplete="off"
              data-form-type="other"
            />
            {searchQuery && (
              <span className="md-search-count">
                {matchCount > 0 ? `${currentMatch} / ${matchCount}` : t('docs.preview.noResults')}
              </span>
            )}
            <button className="md-search-nav-btn" onClick={() => navigateMatch('prev')} disabled={matchCount === 0}>
              <ChevronUp size={14} />
            </button>
            <button className="md-search-nav-btn" onClick={() => navigateMatch('next')} disabled={matchCount === 0}>
              <ChevronDown size={14} />
            </button>
            {searchQuery && (
              <button className="md-search-nav-btn" onClick={clearSearch}>
                <X size={14} />
              </button>
            )}
          </div>
        </div>

        <div className="md-preview-body" ref={bodyRef}>
          {showSpinner && (
            <div className="md-preview-placeholder">
              <Loader2 size={32} className="spin-icon" />
              <span>{t('docs.preview.loading')}</span>
            </div>
          )}
          {error && (
            <div className="md-preview-placeholder md-preview-placeholder--error">
              <AlertCircle size={32} />
              <span>{error}</span>
            </div>
          )}
          {isLargeFile && (
            <div className="md-preview-placeholder md-preview-large-warning">
              <AlertTriangle size={32} />
              <span>{t('docs.preview.largeFile', { size: formatBytes(data!.size_bytes) })}</span>
              <div className="md-preview-large-actions">
                <button className="md-preview-large-btn md-preview-large-btn--primary" onClick={handleDownload}>
                  <Download size={16} />
                  {t('docs.preview.download')}
                </button>
                <button className="md-preview-large-btn" onClick={() => setLargeFileConfirmed(true)}>
                  {t('docs.preview.openAnyway')}
                </button>
              </div>
            </div>
          )}
          {data && !showSpinner && !isLargeFile && (
            <div className="md-preview-content" ref={contentRef}>
              <MarkdownRenderer content={data.markdown} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
