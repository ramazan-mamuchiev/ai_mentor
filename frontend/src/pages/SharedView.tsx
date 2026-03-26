import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ExternalLink, Loader2 } from 'lucide-react'
import { getSharedContent } from '../api/share'
import type { SharedContentResponse } from '../types'
import { MarkdownRenderer } from '../components/MarkdownRenderer'

export function SharedView() {
  const { token } = useParams<{ token: string }>()
  const { t } = useTranslation()
  const [data, setData] = useState<SharedContentResponse | null>(null)
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
