import { useCallback, useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { SourceInfo } from '../types'
import { SourceCard } from './SourceCard'
import { MarkdownPreviewModal } from './MarkdownPreviewModal'

const RATIO_KEY = 'ipcodex-sources-panel-ratio'
const DEFAULT_RATIO = 0.3
const MIN_RATIO = 0.15
const MAX_RATIO = 0.55

function loadRatio(): number {
  try {
    const v = localStorage.getItem(RATIO_KEY)
    if (v) {
      const n = parseFloat(v)
      if (!isNaN(n) && n >= MIN_RATIO && n <= MAX_RATIO) return n
    }
  } catch { /* ignore */ }
  return DEFAULT_RATIO
}

interface Props {
  sources: SourceInfo[]
  onClose: () => void
}

export function SourcesPanel({ sources, onClose }: Props) {
  const { t } = useTranslation()
  const [previewTarget, setPreviewTarget] = useState<{ id: number; title: string } | null>(null)
  const [ratio, setRatio] = useState(loadRatio)
  const dragging = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    try { localStorage.setItem(RATIO_KEY, ratio.toFixed(4)) } catch { /* ignore */ }
  }, [ratio])

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    dragging.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }, [])

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return
    const parent = containerRef.current?.parentElement
    if (!parent) return
    const rect = parent.getBoundingClientRect()
    const newRatio = 1 - (e.clientX - rect.left) / rect.width
    setRatio(Math.max(MIN_RATIO, Math.min(MAX_RATIO, newRatio)))
  }, [])

  const onPointerUp = useCallback(() => {
    if (!dragging.current) return
    dragging.current = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }, [])

  const widthPercent = `${(ratio * 100).toFixed(2)}%`

  return (
    <>
      <div
        className="sources-panel-splitter"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      />
      <div
        ref={containerRef}
        className="sources-panel"
        style={{ width: widthPercent, minWidth: widthPercent }}
      >
        <div className="sources-panel-header">
          <span className="sources-panel-title">
            {t('chat.sourcesPanel.title', { count: sources.length })}
          </span>
          <button className="sources-panel-close" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="sources-panel-body">
          {sources.map((s, i) => (
            <SourceCard
              key={i}
              source={s}
              onPreview={(id, title) => setPreviewTarget({ id, title })}
            />
          ))}
        </div>
        {previewTarget && (
          <MarkdownPreviewModal
            documentId={previewTarget.id}
            documentTitle={previewTarget.title}
            onClose={() => setPreviewTarget(null)}
          />
        )}
      </div>
    </>
  )
}
