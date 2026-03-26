import { useCallback, useEffect, useRef, useState } from 'react'
import { Bug, Share2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ProductDebugContent } from './ProductDebugPanel'
import { DocumentDebugContent } from './DocumentDebugPanel'
import { ShareModal } from './ShareModal'

const MOBILE_BP = 768
const RATIO_KEY = 'lexiro-docs-panel-ratio'
const DEFAULT_RATIO = 0.35
const MIN_RATIO = 0.2
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

function useIsMobile() {
  const [mobile, setMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < MOBILE_BP,
  )
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${MOBILE_BP - 1}px)`)
    const handler = (e: MediaQueryListEvent) => setMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return mobile
}

interface ProductDebugProps {
  mode: 'product'
  manufacturerSlug: string
  productSlug: string
  productName: string
}

interface DocumentDebugProps {
  mode: 'document'
  documentId: number
  documentTitle: string
}

type Props = (ProductDebugProps | DocumentDebugProps) & {
  onClose: () => void
}

export function DocsRightPanel(props: Props) {
  const { t } = useTranslation()
  const isMobile = useIsMobile()
  const [ratio, setRatio] = useState(loadRatio)
  const [shareModal, setShareModal] = useState(false)
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
  const panelStyle = isMobile ? undefined : { width: widthPercent, minWidth: widthPercent }

  const title = props.mode === 'product'
    ? props.productName
    : props.documentTitle
  const subtitle = t('docDebug.title')

  return (
    <>
      {isMobile && (
        <div className="sources-panel-backdrop" onClick={props.onClose} />
      )}
      {!isMobile && (
        <div
          className="sources-panel-splitter"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        />
      )}
      <div ref={containerRef} className="sources-panel docs-right-panel" style={panelStyle}>
        <div className="sources-panel-header">
          <div className="sources-panel-header-content">
            <div className="sources-panel-header-icon">
              <Bug size={14} />
            </div>
            <div className="sources-panel-header-text">
              <span className="sources-panel-title">{subtitle}</span>
              <span className="sources-panel-ids">{title}</span>
            </div>
          </div>
          <div className="sources-panel-header-actions">
            <button
              className="sources-panel-share"
              onClick={() => setShareModal(true)}
              data-tooltip={t('share.shareDebug')}
            >
              <Share2 size={14} />
            </button>
            <button className="sources-panel-close" onClick={props.onClose}>
              <X size={14} />
            </button>
          </div>
        </div>
        <div className="sources-panel-body">
          {props.mode === 'product' ? (
            <ProductDebugContent
              manufacturerSlug={props.manufacturerSlug}
              productSlug={props.productSlug}
            />
          ) : (
            <DocumentDebugContent documentId={props.documentId} />
          )}
        </div>
        {shareModal && (
          <ShareModal
            type={props.mode === 'product' ? 'debug_product' : 'debug_document'}
            id={props.mode === 'product'
              ? `${props.manufacturerSlug}/${props.productSlug}`
              : props.documentId}
            onClose={() => setShareModal(false)}
          />
        )}
      </div>
    </>
  )
}
