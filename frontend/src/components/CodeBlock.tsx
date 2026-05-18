import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Check, Copy, Download } from 'lucide-react'
import { useTranslation } from 'react-i18next'

const LANG_EXTENSIONS: Record<string, string> = {
  python: '.py',
  javascript: '.js',
  typescript: '.ts',
  jsx: '.jsx',
  tsx: '.tsx',
  protobuf: '.proto',
  proto: '.proto',
  json: '.json',
  yaml: '.yaml',
  yml: '.yaml',
  xml: '.xml',
  sql: '.sql',
  bash: '.sh',
  shell: '.sh',
  sh: '.sh',
  powershell: '.ps1',
  go: '.go',
  rust: '.rs',
  cpp: '.cpp',
  c: '.c',
  java: '.java',
  kotlin: '.kt',
  swift: '.swift',
  csharp: '.cs',
  html: '.html',
  css: '.css',
  scss: '.scss',
  markdown: '.md',
  dockerfile: 'Dockerfile',
  docker: 'Dockerfile',
  toml: '.toml',
  ini: '.ini',
  graphql: '.graphql',
  ruby: '.rb',
  php: '.php',
  lua: '.lua',
  r: '.R',
  perl: '.pl',
}

function shortHash(text: string): string {
  let h = 0
  for (let i = 0; i < text.length; i++) {
    h = ((h << 5) - h + text.charCodeAt(i)) | 0
  }
  return Math.abs(h).toString(16).padStart(6, '0').slice(0, 6)
}

function getFilename(language: string, code: string, filename?: string): string {
  if (filename) return filename
  const lang = language.toLowerCase() || 'text'
  const ext = LANG_EXTENSIONS[lang]
  if (ext && !ext.startsWith('.')) return ext
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
  const hash = shortHash(code)
  return `ai_mentor_${lang}_${date}_${hash}${ext || '.txt'}`
}

interface Props {
  language: string
  filename?: string
  children: string
}

export function CodeBlock({ language, filename, children }: Props) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(children)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    const blob = new Blob([children], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = getFilename(language, children, filename)
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const displayLabel = filename || language || 'text'

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span>{displayLabel}</span>
        <div className="code-block-actions">
          <button className="code-action-btn" onClick={handleCopy} title={t('code.copy')}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? t('code.copied') : t('code.copy')}
          </button>
          <button className="code-action-btn" onClick={handleDownload} title={t('code.download')}>
            <Download size={14} />
            {t('code.download')}
          </button>
        </div>
      </div>
      <SyntaxHighlighter
        language={language || 'text'}
        style={oneDark}
        customStyle={{ margin: 0, fontSize: '13px', padding: '12px 16px' }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  )
}
