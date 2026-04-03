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

interface SearchMatch {
  node: Text
  startOffset: number
  length: number
}

function findTextRanges(container: HTMLElement, query: string): SearchMatch[] {
  if (!query.trim()) return []
  const matches: SearchMatch[] = []
  const lowerQuery = query.toLowerCase()
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
  let textNode: Text | null
  while ((textNode = walker.nextNode() as Text | null)) {
    const text = textNode.nodeValue || ''
    const lowerText = text.toLowerCase()
    let idx = lowerText.indexOf(lowerQuery)
    while (idx !== -1) {
      matches.push({ node: textNode, startOffset: idx, length: query.length })
      idx = lowerText.indexOf(lowerQuery, idx + query.length)
    }
  }
  return matches
}

const HIGHLIGHT_NAME = 'md-search-results'
const HIGHLIGHT_ACTIVE_NAME = 'md-search-active'

function applyHighlights(matches: SearchMatch[], activeIndex: number) {
  const CSS = window.CSS as typeof window.CSS & {
    highlights?: Map<string, Highlight>
  }
  if (!CSS.highlights) return

  if (matches.length === 0) {
    CSS.highlights.delete(HIGHLIGHT_NAME)
    CSS.highlights.delete(HIGHLIGHT_ACTIVE_NAME)
    return
  }

  const allRanges: Range[] = []
  for (const m of matches) {
    const range = new Range()
    range.setStart(m.node, m.startOffset)
    range.setEnd(m.node, m.startOffset + m.length)
    allRanges.push(range)
  }

  CSS.highlights.set(HIGHLIGHT_NAME, new Highlight(...allRanges))

  if (activeIndex >= 0 && activeIndex < allRanges.length) {
    CSS.highlights.set(HIGHLIGHT_ACTIVE_NAME, new Highlight(allRanges[activeIndex]))
  } else {
    CSS.highlights.delete(HIGHLIGHT_ACTIVE_NAME)
  }
}

function clearAllHighlights() {
  const CSS = window.CSS as typeof window.CSS & {
    highlights?: Map<string, Highlight>
  }
  if (!CSS.highlights) return
  CSS.highlights.delete(HIGHLIGHT_NAME)
  CSS.highlights.delete(HIGHLIGHT_ACTIVE_NAME)
}

function scrollToRange(range: Range, scrollable: HTMLElement) {
  const rect = range.getBoundingClientRect()
  const containerRect = scrollable.getBoundingClientRect()
  const offset = rect.top - containerRect.top + scrollable.scrollTop - containerRect.height / 2
  scrollable.scrollTo({ top: Math.max(0, offset), behavior: 'smooth' })
}

export function MarkdownPreviewModal({ documentId, documentTitle, onClose }: Props) {
  const { t } = useTranslation()
  const [data, setData] = useState<DocumentMarkdownPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [largeFileConfirmed, setLargeFileConfirmed] = useState(false)

  const [searchQuery, setSearchQuery] = useState('')
  const [matchInfo, setMatchInfo] = useState({ total: 0, current: 0 })
  const contentRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const matchesRef = useRef<SearchMatch[]>([])
  const currentIdxRef = useRef(0)

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
    return () => clearAllHighlights()
  }, [])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (searchQuery) {
          setSearchQuery('')
          clearAllHighlights()
          matchesRef.current = []
          currentIdxRef.current = 0
          setMatchInfo({ total: 0, current: 0 })
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

  useEffect(() => {
    if (!contentRef.current) return
    const container = contentRef.current
    const timer = setTimeout(() => {
      const matches = findTextRanges(container, searchQuery)
      matchesRef.current = matches
      const idx = matches.length > 0 ? 1 : 0
      currentIdxRef.current = idx
      applyHighlights(matches, idx - 1)
      setMatchInfo({ total: matches.length, current: idx })
      if (matches.length > 0 && bodyRef.current) {
        const range = new Range()
        range.setStart(matches[0].node, matches[0].startOffset)
        range.setEnd(matches[0].node, matches[0].startOffset + matches[0].length)
        scrollToRange(range, bodyRef.current)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const navigateMatch = useCallback((direction: 'next' | 'prev') => {
    const matches = matchesRef.current
    if (matches.length === 0) return
    const cur = currentIdxRef.current
    let next: number
    if (direction === 'next') {
      next = cur >= matches.length ? 1 : cur + 1
    } else {
      next = cur <= 1 ? matches.length : cur - 1
    }
    currentIdxRef.current = next
    applyHighlights(matches, next - 1)
    setMatchInfo({ total: matches.length, current: next })
    if (bodyRef.current) {
      const m = matches[next - 1]
      const range = new Range()
      range.setStart(m.node, m.startOffset)
      range.setEnd(m.node, m.startOffset + m.length)
      scrollToRange(range, bodyRef.current)
    }
  }, [])

  const clearSearch = useCallback(() => {
    setSearchQuery('')
    clearAllHighlights()
    matchesRef.current = []
    currentIdxRef.current = 0
    setMatchInfo({ total: 0, current: 0 })
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
                {matchInfo.total > 0 ? `${matchInfo.current} / ${matchInfo.total}` : t('docs.preview.noResults')}
              </span>
            )}
            <button className="md-search-nav-btn" onClick={() => navigateMatch('prev')} disabled={matchInfo.total === 0}>
              <ChevronUp size={14} />
            </button>
            <button className="md-search-nav-btn" onClick={() => navigateMatch('next')} disabled={matchInfo.total === 0}>
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
