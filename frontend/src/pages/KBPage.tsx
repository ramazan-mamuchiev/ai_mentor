import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BookOpen, Database, Search, FileText, Code, Settings, HelpCircle, MessageSquare, Server, Shield, Lock } from 'lucide-react'

interface Article {
  slug: string
  icon: string
  category?: string
  tags: string[]
  createdAt: string
  title: Record<string, string>
  description: Record<string, string>
  languages: string[]
}

const ICON_MAP: Record<string, typeof Database> = {
  Database, FileText, Code, Settings, HelpCircle, BookOpen, MessageSquare, Server, Shield, Lock,
}

const CATEGORIES = [
  { id: 'architecture', icon: Code, color: 'var(--accent)' },
  { id: 'ops', icon: Shield, color: 'var(--warning)' },
  { id: 'security', icon: Lock, color: 'var(--error)' },
] as const

export function KBPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [articles, setArticles] = useState<Article[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const lang = i18n.language?.startsWith('ru') ? 'ru' : 'en'

  useEffect(() => {
    fetch('/articles/registry.json', { cache: 'no-cache' })
      .then(r => r.json())
      .then((data: Article[]) => {
        setArticles(data)
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

  const grouped = CATEGORIES.map(cat => ({
    ...cat,
    articles: filtered.filter(a => a.category === cat.id),
  })).filter(g => g.articles.length > 0)

  const ungrouped = filtered.filter(a => !a.category || !CATEGORIES.some(c => c.id === a.category))

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
        <div className="kb-sections">
          {grouped.map(group => {
            const CatIcon = group.icon
            return (
              <section key={group.id} className="kb-category">
                <div className="kb-category-header">
                  <div className="kb-category-icon" style={{ color: group.color }}>
                    <CatIcon size={20} />
                  </div>
                  <div>
                    <h2 className="kb-category-title">{t(`kb.cat.${group.id}`)}</h2>
                    <p className="kb-category-desc">{t(`kb.cat.${group.id}Desc`)}</p>
                  </div>
                </div>
                <div className="kb-grid">
                  {group.articles.map(article => (
                    <ArticleCard key={article.slug} article={article} lang={lang} navigate={navigate} />
                  ))}
                </div>
              </section>
            )
          })}
          {ungrouped.length > 0 && (
            <div className="kb-grid">
              {ungrouped.map(article => (
                <ArticleCard key={article.slug} article={article} lang={lang} navigate={navigate} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ArticleCard({ article, lang, navigate }: { article: Article; lang: string; navigate: ReturnType<typeof useNavigate> }) {
  const Icon = ICON_MAP[article.icon] || FileText
  return (
    <button
      className="kb-card"
      onClick={() => navigate(`/kb/${article.slug}`)}
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
}
