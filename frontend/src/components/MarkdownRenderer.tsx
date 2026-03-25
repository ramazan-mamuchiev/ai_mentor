import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CodeBlock } from './CodeBlock'
import { fixBrokenTables } from '../utils/fixBrokenTables'
import type { SourceInfo } from '../types'

interface Props {
  content: string
  isStreaming?: boolean
  sources?: SourceInfo[]
}

/**
 * Remove all citation links from markdown so the chat text stays clean.
 * Handles formats: [N](ipcodex:doc:ID), [N](ID), [N](url), [N], and
 * comma-separated groups like [1, 3, 8].
 */
function stripCitations(md: string, sources?: SourceInfo[]): string {
  if (!sources?.length) return md
  let result = md
  result = result.replace(/\[[\d,\s]+\]\([^)]*\)/g, '')
  result = result.replace(/\[[\d,\s]+\](?!\()/g, '')
  result = result.replace(/ {2,}/g, ' ')
  result = result.replace(/ ([.,;:!?])/g, '$1')
  return result
}

export function MarkdownRenderer({ content, isStreaming, sources }: Props) {
  const processed = useMemo(
    () => stripCitations(fixBrokenTables(content), sources),
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
