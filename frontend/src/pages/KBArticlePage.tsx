import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Maximize2, Minimize2 } from 'lucide-react'

interface RegistryEntry {
  slug: string
  title: Record<string, string>
  languages: string[]
}

interface ArticleData {
  css: string
  content: string
}

export function KBArticlePage() {
  const { slug } = useParams<{ slug: string }>()
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const contentRef = useRef<HTMLDivElement>(null)
  const styleRef = useRef<HTMLStyleElement | null>(null)
  const [meta, setMeta] = useState<RegistryEntry | null>(null)
  const [article, setArticle] = useState<ArticleData | null>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const [loading, setLoading] = useState(true)
  const lang = i18n.language?.startsWith('ru') ? 'ru' : 'en'

  useEffect(() => {
    fetch('/articles/registry.json')
      .then(r => r.json())
      .then((data: RegistryEntry[]) => {
        setMeta(data.find(a => a.slug === slug) || null)
      })
      .catch(() => setMeta(null))
  }, [slug])

  const articleLang = meta?.languages?.includes(lang) ? lang : 'en'

  const fetchArticle = useCallback(() => {
    if (!slug) return
    setLoading(true)
    fetch(`/articles/${slug}/${articleLang}.json`)
      .then(r => r.json())
      .then((data: ArticleData) => {
        setArticle(data)
        setLoading(false)
      })
      .catch(() => {
        setArticle(null)
        setLoading(false)
      })
  }, [slug, articleLang])

  useEffect(() => {
    fetchArticle()
  }, [fetchArticle])

  useEffect(() => {
    if (!article?.css) return

    if (!styleRef.current) {
      styleRef.current = document.createElement('style')
      styleRef.current.setAttribute('data-kb-article', slug || '')
      document.head.appendChild(styleRef.current)
    }
    styleRef.current.textContent = article.css

    return () => {
      if (styleRef.current) {
        document.head.removeChild(styleRef.current)
        styleRef.current = null
      }
    }
  }, [article?.css, slug])

  useEffect(() => {
    const el = contentRef.current
    if (!el) return

    const handler = (e: MouseEvent) => {
      const link = (e.target as HTMLElement).closest('a[href^="/kb/"]') as HTMLAnchorElement | null
      if (link) {
        e.preventDefault()
        e.stopPropagation()
        navigate(link.getAttribute('href')!)
        return
      }

      const stage = (e.target as HTMLElement).closest('.stage') as HTMLElement | null
      if (!stage) return
      const details = stage.querySelector('.stage-details') as HTMLElement | null
      if (!details) return

      if (stage.classList.contains('open')) {
        details.style.maxHeight = details.scrollHeight + 'px'
        requestAnimationFrame(() => {
          details.style.maxHeight = '0'
        })
        stage.classList.remove('open')
      } else {
        stage.classList.add('open')
        details.style.maxHeight = details.scrollHeight + 'px'
        const onEnd = () => {
          details.style.maxHeight = 'none'
          details.removeEventListener('transitionend', onEnd)
        }
        details.addEventListener('transitionend', onEnd)
      }
    }
    el.addEventListener('click', handler)
    return () => el.removeEventListener('click', handler)
  }, [article?.content])

  useEffect(() => {
    const el = contentRef.current
    if (!el) return
    el.scrollTop = 0

    const stages = el.querySelectorAll<HTMLElement>('.stage')
    stages.forEach((s, i) => {
      s.style.opacity = '0'
      s.style.transform = 'translateY(20px)'
      setTimeout(() => {
        s.style.transition = 'all 0.5s ease'
        s.style.opacity = '1'
        s.style.transform = 'translateY(0)'
      }, 100 + i * 80)
    })
  }, [article?.content])

  if (loading && !article) {
    return <div className="kb-viewer-loading">{t('kb.loading')}</div>
  }

  if (!meta) {
    return (
      <div className="kb-viewer-error">
        <p>{t('kb.notFound')}</p>
        <button className="btn" onClick={() => navigate('/kb')}>
          <ArrowLeft size={16} /> {t('kb.backToCatalog')}
        </button>
      </div>
    )
  }

  return (
    <div className={`kb-viewer${fullscreen ? ' kb-viewer--fullscreen' : ''}`}>
      <div className="kb-viewer-toolbar">
        <button className="btn" onClick={() => navigate('/kb')}>
          <ArrowLeft size={16} /> {t('kb.backToCatalog')}
        </button>
        <h2>{meta.title[lang] || meta.title.en}</h2>
        <div className="kb-viewer-actions">
          <button
            className="btn"
            onClick={() => setFullscreen(f => !f)}
            title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>
      </div>
      <div
        ref={contentRef}
        className="kb-viewer-content"
        dangerouslySetInnerHTML={{ __html: article?.content || '' }}
      />
    </div>
  )
}
