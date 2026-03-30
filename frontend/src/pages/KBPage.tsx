import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BookOpen, Database, Search, FileText, Code, Settings, HelpCircle, MessageSquare, Server } from 'lucide-react'

interface Article {
  slug: string
  icon: string
  tags: string[]
  createdAt: string
  title: Record<string, string>
  description: Record<string, string>
  languages: string[]
}

const ICON_MAP: Record<string, typeof Database> = {
  Database,
  FileText,
  Code,
  Settings,
  HelpCircle,
  BookOpen,
  MessageSquare,
  Server,
}

export function KBPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [articles, setArticles] = useState<Article[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const lang = i18n.language?.startsWith('ru') ? 'ru' : 'en'

  useEffect(() => {
    fetch('/articles/registry.json')
      .then(r => r.json())
      .then((data: Article[]) => {
        setArticles(data.sort((a, b) => b.createdAt.localeCompare(a.createdAt)))
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const filtered = articles.filter(a => {
    if (!search) return true
    const q = search.toLowerCase()
    const title = (a.title[lang] || a.title.en || '').toLowerCase()
    const desc = (a.description[lang] || a.description.en || '').toLowerCase()
    const tags = a.tags.join(' ').toLowerCase()
    return title.includes(q) || desc.includes(q) || tags.includes(q)
  })

  return (
    <div className="kb-page">
      <div className="kb-header">
        <div className="kb-header-text">
          <h1><BookOpen size={24} /> {t('kb.title')}</h1>
          <p>{t('kb.description')}</p>
        </div>
        {articles.length > 1 && (
          <div className="kb-search">
            <Search size={16} />
            <input
              type="text"
              placeholder={t('kb.search')}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        )}
      </div>

      {loading ? (
        <div className="kb-loading">{t('kb.loading')}</div>
      ) : filtered.length === 0 ? (
        <div className="kb-empty">{search ? t('kb.noResults') : t('kb.empty')}</div>
      ) : (
        <div className="kb-grid">
          {filtered.map(article => {
            const Icon = ICON_MAP[article.icon] || FileText
            return (
              <button
                key={article.slug}
                className="kb-card"
                onClick={() => navigate(`/app/kb/${article.slug}`)}
              >
                <div className="kb-card-icon"><Icon size={24} /></div>
                <div className="kb-card-body">
                  <h3>{article.title[lang] || article.title.en}</h3>
                  <p>{article.description[lang] || article.description.en}</p>
                  <div className="kb-card-meta">
                    <span className="kb-card-date">{article.createdAt}</span>
                    <div className="kb-card-tags">
                      {article.tags.map(tag => (
                        <span key={tag} className="kb-tag">{tag}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
