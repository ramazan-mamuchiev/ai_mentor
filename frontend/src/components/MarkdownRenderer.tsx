import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CodeBlock } from './CodeBlock'
import { fixBrokenTables } from '../utils/fixBrokenTables'

const DOC_LINK_RE = /^ipcodex:doc:(\d+)$/

interface Props {
  content: string
  isStreaming?: boolean
  onDocumentPreview?: (docId: number, title: string) => void
}

export function MarkdownRenderer({ content, isStreaming, onDocumentPreview }: Props) {
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
        {fixBrokenTables(content)}
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
