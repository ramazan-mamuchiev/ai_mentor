import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Copy, Link2, Loader2, X, EyeOff } from 'lucide-react'
import {
  shareSession,
  shareMessage,
  shareDebugMessage,
  shareDebugDocument,
  shareDebugProduct,
  deleteSharedLink,
} from '../api/share'
import type { SharedLinkResponse } from '../types'

export type ShareType = 'session' | 'message' | 'debug_chat' | 'debug_document' | 'debug_product'

interface Props {
  type: ShareType
  id: number | string
  onClose: () => void
}

async function createShareLink(type: ShareType, id: number | string): Promise<SharedLinkResponse> {
  switch (type) {
    case 'session':
      return shareSession(id as string)
    case 'message':
      return shareMessage(id as number)
    case 'debug_chat':
      return shareDebugMessage(id as number)
    case 'debug_document':
      return shareDebugDocument(id as number)
    case 'debug_product': {
      const [mfr, slug] = (id as string).split('/')
      return shareDebugProduct(mfr, slug)
    }
  }
}

function getModalTitle(type: ShareType, t: (key: string) => string): string {
  switch (type) {
    case 'session': return t('share.shareChat')
    case 'message': return t('share.shareAnswer')
    default: return t('share.shareDebug')
  }
}

export function ShareModal({ type, id, onClose }: Props) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [link, setLink] = useState<SharedLinkResponse | null>(null)
  const [copied, setCopied] = useState(false)
  const [deactivating, setDeactivating] = useState(false)

  useEffect(() => {
    let cancelled = false
    const create = async () => {
      try {
        setLoading(true)
        setError(null)
        const result = await createShareLink(type, id)
        if (!cancelled) setLink(result)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    create()
    return () => { cancelled = true }
  }, [type, id])

  const handleCopy = useCallback(async () => {
    if (!link) return
    try {
      await navigator.clipboard.writeText(link.url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = link.url
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }, [link])

  const handleDeactivate = useCallback(async () => {
    if (!link) return
    try {
      setDeactivating(true)
      await deleteSharedLink(link.token)
      setLink(prev => prev ? { ...prev, is_active: false } : null)
    } catch {
      // ignore
    } finally {
      setDeactivating(false)
    }
  }, [link])

  const handleOverlayClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }, [onClose])

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEsc)
    return () => document.removeEventListener('keydown', handleEsc)
  }, [onClose])

  const isDebug = type.startsWith('debug_')

  return (
    <div className="share-overlay" onClick={handleOverlayClick}>
      <div className="share-modal">
        <div className="share-modal-header">
          <h3>
            <Link2 size={16} />
            {getModalTitle(type, t)}
          </h3>
          <button className="share-modal-close" onClick={onClose} aria-label={t('share.close')}>
            <X size={18} />
          </button>
        </div>

        <div className="share-modal-body">
          {loading && (
            <div className="share-loading">
              <Loader2 size={20} className="share-spinner" />
              <span>{t('share.creating')}</span>
            </div>
          )}

          {error && (
            <div className="share-error">
              <span>{t('share.error')}</span>
              <p>{error}</p>
            </div>
          )}

          {link && !loading && (
            <>
              {link.is_active ? (
                <>
                  <p className="share-success-text">{t('share.linkCreated')}</p>
                  {isDebug && link.expires_at && (
                    <p className="share-expires-text">
                      {t('share.expiresAt', { date: new Date(link.expires_at).toLocaleDateString() })}
                    </p>
                  )}
                  <div className="share-link-field">
                    <input
                      type="text"
                      readOnly
                      value={link.url}
                      className="share-link-input"
                      onFocus={e => e.target.select()}
                    />
                    <button
                      className="share-copy-btn"
                      onClick={handleCopy}
                      data-tooltip={copied ? t('share.linkCopied') : t('share.copyLink')}
                    >
                      {copied ? <Check size={16} /> : <Copy size={16} />}
                      <span>{copied ? t('share.linkCopied') : t('share.copyLink')}</span>
                    </button>
                  </div>
                  <div className="share-actions">
                    <button
                      className="share-deactivate-btn"
                      onClick={handleDeactivate}
                      disabled={deactivating}
                    >
                      <EyeOff size={14} />
                      <span>{t('share.deactivate')}</span>
                    </button>
                  </div>
                </>
              ) : (
                <p className="share-deactivated-text">{t('share.deactivated')}</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
