import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CodeBlock } from './CodeBlock'
import { fixBrokenTables } from '../utils/fixBrokenTables'

function stripCitations(md: string): string {
  let result = md
  result = result.replace(/\[[\d,\s]+\]\([^)]*\)/g, '')
  result = result.replace(/\[[\d,\s]+\](?!\()/g, '')
  result = result.replace(/ {2,}/g, ' ')
  result = result.replace(/ ([.,;:!?])/g, '$1')
  return result
}

const BARE_URL_RE = /(?<![(\[/])\b((?:https?:\/\/)?(?:[\w-]+\.)+[a-z]{2,}(?:\/[^\s)]*)?)/gi
const HAS_PROTOCOL_RE = /^https?:\/\//i
const CODE_FENCE_RE = /```[\s\S]*?```|`[^`]+`/g

function linkifyBareUrls(md: string): string {
  const codeSpans: string[] = []
  const placeholder = '\x00CODE\x00'
  let cleaned = md.replace(CODE_FENCE_RE, (m) => {
    codeSpans.push(m)
    return placeholder
  })

  cleaned = cleaned.replace(BARE_URL_RE, (match, _url, offset) => {
    const before = cleaned.slice(Math.max(0, offset - 2), offset)
    if (/[(\[]$/.test(before)) return match
    if (before.endsWith('](')) return match

    const tld = match.match(/\.([a-z]{2,})/i)?.[1]?.toLowerCase()
    if (!tld) return match
    const knownTlds = ['com', 'org', 'net', 'io', 'dev', 'ru', 'co', 'ai', 'me', 'info', 'biz', 'gov', 'edu']
    if (!knownTlds.includes(tld)) return match

    const href = HAS_PROTOCOL_RE.test(match) ? match : `https://${match}`
    return `[${match}](${href})`
  })

  let idx = 0
  cleaned = cleaned.replace(new RegExp(placeholder.replace(/\x00/g, '\\x00'), 'g'), () => codeSpans[idx++] || '')
  return cleaned
}

interface Props {
  content: string
  isStreaming?: boolean
}

export function MarkdownRenderer({ content, isStreaming }: Props) {
  const processed = useMemo(() => linkifyBareUrls(stripCitations(fixBrokenTables(content))), [content])

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

            let language = match?.[1] || ''
            let filename: string | undefined

            const metaMatch = /language-(\w+):(.+)/.exec(className || '')
            if (metaMatch) {
              language = metaMatch[1]
              filename = metaMatch[2]
            }

            return (
              <CodeBlock language={language} filename={filename}>
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
