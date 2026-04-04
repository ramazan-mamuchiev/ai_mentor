import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ExternalLink, Loader2, FileText, Layers } from 'lucide-react'
import { getSharedContent } from '../api/share'
import type { SharedContentResponse, SharedDebugContentResponse, SharedLifecycleContentResponse, DebugInfo, DocumentDebugInfo, DocumentUsageStats, ProductDebugInfo, ProductUsageStats } from '../types'
import type { LifecyclePayload, DocumentLifecycle } from '../api/products'
import { MarkdownRenderer } from '../components/MarkdownRenderer'
import { DebugPanelContent } from '../components/RightPanel'
import { DocumentDebugContent } from '../components/DocumentDebugPanel'
import { ProductDebugContent } from '../components/ProductDebugPanel'
import { LifecycleContent } from '../components/ProductLifecycleModal'

type SharedData = SharedContentResponse | SharedDebugContentResponse | SharedLifecycleContentResponse

function isDebugResponse(data: SharedData): data is SharedDebugContentResponse {
  return data.share_type.startsWith('debug_')
}

function isLifecycleResponse(data: SharedData): data is SharedLifecycleContentResponse {
  return data.share_type === 'lifecycle'
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

  if (isLifecycleResponse(data)) {
    return <SharedLifecycleView data={data} />
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


function SharedLifecycleView({ data }: { data: SharedLifecycleContentResponse }) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<string>('merged')

  const merged = data.merged as LifecyclePayload | null
  const docLcs = (data.document_lifecycles ?? []) as unknown as DocumentLifecycle[]
  const readyDocLcs = docLcs.filter(d => d.status === 'ready')
  const issues = (data.doc_issues ?? []) as Array<{ document_id: number; issue_type: string; severity: string; description: string; affected_entity?: string; suggestion?: string }>
  const showTabs = merged && readyDocLcs.length > 0

  const activeDocLc = activeTab !== 'merged'
    ? docLcs.find(d => `doc-${d.document_id}` === activeTab) ?? null
    : null
  const activeIssues = activeTab === 'merged'
    ? issues
    : issues.filter(i => activeDocLc && i.document_id === activeDocLc.document_id)

  return (
    <div className="shared-view shared-view--lifecycle">
      <div className="shared-view-header">
        <Link to="/" className="shared-view-logo">
          <img src="/logo-on-light.svg" alt="Lexiro" className="logo-light" />
          <img src="/logo-on-dark.svg" alt="Lexiro" className="logo-dark" />
        </Link>
        <div className="shared-view-meta">
          <h1 className="shared-view-title">{data.title}</h1>
          <span className="shared-view-product">{data.product_name}</span>
        </div>
        <Link to="/app" className="shared-view-cta">
          <ExternalLink size={14} />
          {t('share.tryIt')}
        </Link>
      </div>

      <div className="shared-view-lifecycle-content">
        {showTabs && (
          <div className="plc-tabs" role="tablist">
            <button
              className={`plc-tab${activeTab === 'merged' ? ' plc-tab--active' : ''}`}
              role="tab"
              aria-selected={activeTab === 'merged'}
              onClick={() => setActiveTab('merged')}
            >
              <Layers size={13} />
              <span>{t('lifecycleModal.tabMerged', 'Merged')}</span>
            </button>
            {readyDocLcs.map(dl => (
              <button
                key={dl.document_id}
                className={`plc-tab${activeTab === `doc-${dl.document_id}` ? ' plc-tab--active' : ''}`}
                role="tab"
                aria-selected={activeTab === `doc-${dl.document_id}`}
                onClick={() => setActiveTab(`doc-${dl.document_id}`)}
                title={dl.document_name || `Document ${dl.document_id}`}
              >
                <FileText size={13} />
                <span className="plc-tab-label">{dl.document_name || `Doc ${dl.document_id}`}</span>
              </button>
            ))}
          </div>
        )}

        {showTabs && activeTab === 'merged' && merged && (
          <LifecycleContent lc={merged} issues={activeIssues} />
        )}
        {showTabs && activeTab !== 'merged' && activeDocLc && (
          <LifecycleContent lc={activeDocLc} issues={activeIssues} />
        )}
        {!showTabs && merged && (
          <LifecycleContent lc={merged} issues={issues} />
        )}
        {!showTabs && !merged && readyDocLcs.length === 1 && (
          <LifecycleContent lc={readyDocLcs[0]} issues={activeIssues} />
        )}
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
