import type { ReactNode } from 'react'
import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CodeBlock } from './CodeBlock'
import { fixBrokenTables } from '../utils/fixBrokenTables'
import type { SourceInfo } from '../types'

const DOC_LINK_RE = /ipcodex:doc:(\d+)/

interface Props {
  content: string
  isStreaming?: boolean
  sources?: SourceInfo[]
  onDocumentPreview?: (docId: number, title: string) => void
}

/**
 * Normalize citation links that LLM may produce in various forms:
 * - [N](ipcodex:doc:ID) — already correct
 * - [N](ID) — numeric-only href
 * - [N](any-url) — LLM sometimes wraps index in a random URL
 * - [N] — bare bracket reference without href
 * Uses the sources array to build a sourceIndex→documentId map.
 */
function normalizeCitations(md: string, sources?: SourceInfo[]): string {
  if (!sources?.length) return md

  const indexToDocId = new Map<number, number>()
  sources.forEach((s, i) => {
    if (s.document_id) indexToDocId.set(i + 1, s.document_id)
  })

  const maxIdx = sources.length

  let result = md.replace(
    /\[(\d+)\]\(ipcodex:doc:(\d+)\)/g,
    (_full, n, id) => `[${n}](ipcodex:doc:${id})`,
  )

  result = result.replace(
    /\[(\d+)\]\((\d+)\)/g,
    (_full, n, rawId) => {
      const num = parseInt(n, 10)
      const docId = indexToDocId.get(num) ?? parseInt(rawId, 10)
      return `[${n}](ipcodex:doc:${docId})`
    },
  )

  result = result.replace(
    /\[(\d+)\]\((?!ipcodex:doc:)[^)]+\)/g,
    (_full, n) => {
      const num = parseInt(n, 10)
      if (num >= 1 && num <= maxIdx) {
        const docId = indexToDocId.get(num)
        if (docId) return `[${n}](ipcodex:doc:${docId})`
      }
      return _full
    },
  )

  result = result.replace(
    /\[(\d+)\](?!\()/g,
    (_full, n) => {
      const num = parseInt(n, 10)
      if (num >= 1 && num <= maxIdx) {
        const docId = indexToDocId.get(num)
        if (docId) return `[${n}](ipcodex:doc:${docId})`
      }
      return _full
    },
  )

  return result
}

export function MarkdownRenderer({ content, isStreaming, sources, onDocumentPreview }: Props) {
  const processed = useMemo(
    () => normalizeCitations(fixBrokenTables(content), sources),
    [content, sources],
  )

  return (
    <div className={isStreaming ? 'streaming-content' : undefined}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '')
            const isInline = !match && !className

            if (isInline) {
              return (
                <code
                  style={{
                    background: 'rgba(0,0,0,0.1)',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    fontSize: '0.9em',
                    fontFamily: 'var(--font-mono)',
                  }}
                  {...props}
                >
                  {children}
                </code>
              )
            }

            return (
              <CodeBlock language={match?.[1] || ''}>
                {String(children).replace(/\n$/, '')}
              </CodeBlock>
            )
          },
          a({ href, children, ...props }) {
            const docMatch = href ? DOC_LINK_RE.exec(href) : null
            if (docMatch && onDocumentPreview) {
              const docId = parseInt(docMatch[1], 10)
              const label = extractText(children)
              return (
                <span
                  className="doc-ref-badge"
                  role="button"
                  tabIndex={0}
                  onClick={() => onDocumentPreview(docId, label)}
                  onKeyDown={e => { if (e.key === 'Enter') onDocumentPreview(docId, label) }}
                >
                  {label}
                </span>
              )
            }
            return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>
          },
        }}
      >
        {processed}
      </ReactMarkdown>
      {isStreaming && <span className="streaming-cursor" />}
    </div>
  )
}

function extractText(node: ReactNode): string {
  if (typeof node === 'string') return node
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (node && typeof node === 'object' && 'props' in node) {
    return extractText((node as { props: { children?: ReactNode } }).props.children)
  }
  return ''
}
