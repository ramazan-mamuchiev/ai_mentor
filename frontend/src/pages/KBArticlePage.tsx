import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, ExternalLink, Maximize2, Minimize2 } from 'lucide-react'
import { useTheme } from '../hooks/useTheme'

interface Article {
  slug: string
  title: Record<string, string>
  languages: string[]
}

export function KBArticlePage() {
  const { slug } = useParams<{ slug: string }>()
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { theme } = useTheme()
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [article, setArticle] = useState<Article | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [loading, setLoading] = useState(true)
  const lang = i18n.language?.startsWith('ru') ? 'ru' : 'en'

  useEffect(() => {
    fetch('/articles/registry.json')
      .then(r => r.json())
      .then((data: Article[]) => {
        const found = data.find(a => a.slug === slug)
        setArticle(found || null)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [slug])

  const articleLang = article?.languages?.includes(lang) ? lang : 'en'
  const iframeSrc = slug ? `/articles/${slug}/${articleLang}.html?theme=${theme}` : ''

  const sendTheme = useCallback(() => {
    iframeRef.current?.contentWindow?.postMessage(
      { type: 'lexiro-theme', theme },
      window.location.origin,
    )
  }, [theme])

  useEffect(() => {
    sendTheme()
  }, [sendTheme])

  if (loading) {
    return <div className="kb-viewer-loading">{t('kb.loading')}</div>
  }

  if (!article) {
    return (
      <div className="kb-viewer-error">
        <p>{t('kb.notFound')}</p>
        <button className="btn" onClick={() => navigate('/app/kb')}>
          <ArrowLeft size={16} /> {t('kb.backToCatalog')}
        </button>
      </div>
    )
  }

  return (
    <div className={`kb-viewer${fullscreen ? ' kb-viewer--fullscreen' : ''}`}>
      <div className="kb-viewer-toolbar">
        <button className="btn" onClick={() => navigate('/app/kb')}>
          <ArrowLeft size={16} /> {t('kb.backToCatalog')}
        </button>
        <h2>{article.title[lang] || article.title.en}</h2>
        <div className="kb-viewer-actions">
          <button className="btn" onClick={() => setFullscreen(f => !f)} title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
            {fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
          <a className="btn" href={iframeSrc} target="_blank" rel="noopener noreferrer" title={t('kb.openInNewTab')}>
            <ExternalLink size={16} />
          </a>
        </div>
      </div>
      <iframe
        ref={iframeRef}
        className="kb-viewer-frame"
        src={iframeSrc}
        onLoad={sendTheme}
        title={article.title[lang] || article.title.en}
      />
    </div>
  )
}
