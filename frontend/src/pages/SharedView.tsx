import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ExternalLink, Loader2 } from 'lucide-react'
import { getSharedContent } from '../api/share'
import type { SharedContentResponse, SharedDebugContentResponse, DebugInfo, DocumentDebugInfo, DocumentUsageStats, ProductDebugInfo, ProductUsageStats } from '../types'
import { MarkdownRenderer } from '../components/MarkdownRenderer'
import { DebugPanelContent } from '../components/RightPanel'
import { DocumentDebugContent } from '../components/DocumentDebugPanel'
import { ProductDebugContent } from '../components/ProductDebugPanel'

type SharedData = SharedContentResponse | SharedDebugContentResponse

function isDebugResponse(data: SharedData): data is SharedDebugContentResponse {
  return data.share_type.startsWith('debug_')
}

export function SharedView() {
  const { token } = useParams<{ token: string }>()
  const { t } = useTranslation()
  const [data, setData] = useState<SharedData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    const load = async () => {
      try {
        setLoading(true)
        const result = await getSharedContent(token)
        if (!cancelled) setData(result)
      } catch (e) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : String(e)
          if (msg.includes('410')) {
            setError('inactive')
          } else if (msg.includes('404')) {
            setError('notFound')
          } else {
            setError('notFound')
          }
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [token])

  if (loading) {
    return (
      <div className="shared-view">
        <div className="shared-view-loading">
          <Loader2 size={24} className="share-spinner" />
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="shared-view">
        <div className="shared-view-header">
          <Link to="/" className="shared-view-logo">
            <img src="/logo-on-light.svg" alt="Lexiro" className="logo-light" />
            <img src="/logo-on-dark.svg" alt="Lexiro" className="logo-dark" />
          </Link>
        </div>
        <div className="shared-view-error">
          <h2>{error === 'inactive' ? t('share.inactive') : t('share.notFound')}</h2>
          <Link to="/app" className="shared-view-cta">
            {t('share.tryIt')}
          </Link>
        </div>
      </div>
    )
  }

  if (isDebugResponse(data)) {
    return <SharedDebugView data={data} />
  }

  return (
    <div className="shared-view">
      <div className="shared-view-header">
        <Link to="/" className="shared-view-logo">
          <img src="/logo-on-light.svg" alt="Lexiro" className="logo-light" />
          <img src="/logo-on-dark.svg" alt="Lexiro" className="logo-dark" />
        </Link>
        <div className="shared-view-meta">
          {data.product_filter && (
            <span className="shared-view-product">{data.product_filter}</span>
          )}
          <h1 className="shared-view-title">{data.title}</h1>
        </div>
        <Link to="/app" className="shared-view-cta">
          <ExternalLink size={14} />
          {t('share.tryIt')}
        </Link>
      </div>

      <div className="shared-view-messages">
        {data.messages.map((msg, idx) => (
          <div key={idx} className={`shared-message ${msg.role}`}>
            <div className="shared-message-body">
              {msg.role === 'user' ? (
                <div className="shared-message-content">{msg.content}</div>
              ) : (
                <div className="shared-message-content">
                  <MarkdownRenderer content={msg.content} />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="shared-view-footer">
        <span>{t('share.poweredBy')}</span>
      </div>
    </div>
  )
}


function SharedDebugView({ data }: { data: SharedDebugContentResponse }) {
  const { t } = useTranslation()

  let content: React.ReactNode = null

  if (data.share_type === 'debug_chat') {
    const debugInfo = data.data as unknown as DebugInfo
    content = <DebugPanelContent debug={debugInfo} />
  } else if (data.share_type === 'debug_document') {
    const docData = data.data as { debug?: DocumentDebugInfo; usage?: DocumentUsageStats | null }
    content = docData.debug
      ? <DocumentDebugContent initialDebug={docData.debug as DocumentDebugInfo} initialUsage={docData.usage as DocumentUsageStats | null} />
      : <div className="shared-view-error">{t('share.notFound')}</div>
  } else if (data.share_type === 'debug_product') {
    const prodData = data.data as { debug?: ProductDebugInfo; usage?: ProductUsageStats | null }
    content = prodData.debug
      ? <ProductDebugContent initialDebug={prodData.debug as ProductDebugInfo} initialUsage={prodData.usage as ProductUsageStats | null} />
      : <div className="shared-view-error">{t('share.notFound')}</div>
  }

  return (
    <div className="shared-view shared-view--debug">
      <div className="shared-view-header">
        <Link to="/" className="shared-view-logo">
          <img src="/logo-on-light.svg" alt="Lexiro" className="logo-light" />
          <img src="/logo-on-dark.svg" alt="Lexiro" className="logo-dark" />
        </Link>
        <div className="shared-view-meta">
          <h1 className="shared-view-title">{data.title}</h1>
          {data.expires_at && (
            <span className="shared-view-expires">
              {t('share.expiresAt', { date: new Date(data.expires_at).toLocaleDateString() })}
            </span>
          )}
        </div>
        <Link to="/app" className="shared-view-cta">
          <ExternalLink size={14} />
          {t('share.tryIt')}
        </Link>
      </div>

      <div className="shared-view-debug-content">
        {content}
      </div>

      <div className="shared-view-footer">
        <span>{t('share.poweredBy')}</span>
      </div>
    </div>
  )
}
