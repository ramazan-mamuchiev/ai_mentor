import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import { Maximize2, X, ZoomIn, ZoomOut, Maximize } from 'lucide-react'
import svgPanZoom from 'svg-pan-zoom'
import mermaid from 'mermaid'

mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  flowchart: { curve: 'basis', htmlLabels: true },
})

function sanitizeMermaid(src: string): string {
  return src
    .replace(/(-->|===|~~~|-\.->?)\|([^|]+)\|/g, (_m, arrow, label) =>
      `${arrow}|${label.replace(/[(){}]/g, '')}|`)
    .replace(/\[([^\]]+)\]/g, (_m, label) =>
      `[${label.replace(/[(){}]/g, '')}]`)
}

interface Props {
  chart: string
  className?: string
}

let counter = 0

export function MermaidDiagram({ chart, className }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const overlayDiagramRef = useRef<HTMLDivElement>(null)
  const panZoomRef = useRef<ReturnType<typeof svgPanZoom> | null>(null)
  const [svg, setSvg] = useState<string>('')
  const [error, setError] = useState<string>('')
  const [fullscreen, setFullscreen] = useState(false)
  const safeChart = useMemo(() => sanitizeMermaid(chart), [chart])

  useEffect(() => {
    if (!safeChart.trim()) return
    const id = `mermaid-${++counter}`

    let cancelled = false
    mermaid.render(id, safeChart).then(
      ({ svg: rendered }) => { if (!cancelled) setSvg(rendered) },
      (err) => { if (!cancelled) setError(String(err)) },
    )
    return () => { cancelled = true }
  }, [safeChart])

  useEffect(() => {
    if (!fullscreen || !overlayDiagramRef.current) return

    const container = overlayDiagramRef.current
    const svgEl = container.querySelector('svg')
    if (!svgEl) return

    // Ensure viewBox exists so svg-pan-zoom can compute the initial fit.
    // Mermaid sometimes sets width/height in px but omits viewBox.
    if (!svgEl.getAttribute('viewBox')) {
      const w = svgEl.width.baseVal.value || svgEl.getBoundingClientRect().width
      const h = svgEl.height.baseVal.value || svgEl.getBoundingClientRect().height
      if (w && h) svgEl.setAttribute('viewBox', `0 0 ${w} ${h}`)
    }

    svgEl.removeAttribute('width')
    svgEl.removeAttribute('height')
    svgEl.removeAttribute('style')
    svgEl.style.width = '100%'
    svgEl.style.height = '100%'

    let instance: ReturnType<typeof svgPanZoom> | null = null
    let raf2 = 0
    // Double-rAF: first frame lets the overlay settle its layout,
    // second frame initialises pan-zoom with correct dimensions.
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => {
        instance = svgPanZoom(svgEl, {
          zoomEnabled: true,
          panEnabled: true,
          controlIconsEnabled: false,
          fit: false,
          center: false,
          minZoom: 0.1,
          maxZoom: 20,
          zoomScaleSensitivity: 0.3,
          dblClickZoomEnabled: true,
        })
        instance.resize()
        instance.fit()
        instance.center()
        panZoomRef.current = instance
      })
    })

    return () => {
      cancelAnimationFrame(raf1)
      cancelAnimationFrame(raf2)
      try { instance?.destroy() } catch { /* unmounted */ }
      panZoomRef.current = null
    }
  }, [fullscreen, svg])

  const handleEsc = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') setFullscreen(false)
  }, [])

  useEffect(() => {
    if (fullscreen) {
      window.addEventListener('keydown', handleEsc)
      return () => window.removeEventListener('keydown', handleEsc)
    }
  }, [fullscreen, handleEsc])

  const handleZoomIn = useCallback(() => panZoomRef.current?.zoomIn(), [])
  const handleZoomOut = useCallback(() => panZoomRef.current?.zoomOut(), [])
  const handleFit = useCallback(() => {
    panZoomRef.current?.fit()
    panZoomRef.current?.center()
  }, [])

  if (error) {
    return <pre className="lc-mermaid-error">{error}</pre>
  }

  if (!svg) {
    return <div className={`lc-mermaid-placeholder ${className ?? ''}`}>Loading diagram…</div>
  }

  return (
    <>
      <div className={`lc-mermaid-wrapper ${className ?? ''}`}>
        <button
          className="lc-mermaid-fullscreen-btn"
          onClick={() => setFullscreen(true)}
          title="Fullscreen"
        >
          <Maximize2 size={14} />
        </button>
        <div
          ref={containerRef}
          className="lc-mermaid"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>

      {fullscreen && (
        <div className="lc-mermaid-overlay" onClick={() => setFullscreen(false)}>
          <div className="lc-mermaid-overlay-content" onClick={e => e.stopPropagation()}>
            <div className="lc-mermaid-overlay-header">
              <div className="lc-mermaid-overlay-controls">
                <button onClick={handleZoomIn} title="Zoom in" className="lc-mermaid-ctrl-btn">
                  <ZoomIn size={16} />
                </button>
                <button onClick={handleZoomOut} title="Zoom out" className="lc-mermaid-ctrl-btn">
                  <ZoomOut size={16} />
                </button>
                <button onClick={handleFit} title="Fit to screen" className="lc-mermaid-ctrl-btn">
                  <Maximize size={16} />
                </button>
              </div>
              <button
                className="lc-mermaid-overlay-close"
                onClick={() => setFullscreen(false)}
              >
                <X size={18} />
              </button>
            </div>
            <div
              ref={overlayDiagramRef}
              className="lc-mermaid-overlay-diagram"
              dangerouslySetInnerHTML={{ __html: svg }}
            />
          </div>
        </div>
      )}
    </>
  )
}
