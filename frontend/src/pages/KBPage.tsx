import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { BookOpen, Database, Search, FileText, Code, Settings, HelpCircle, MessageSquare, Server, Shield, Lock, ChevronDown, X } from 'lucide-react'

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
  const [activeTag, setActiveTag] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
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

  const allTags = [...new Set(articles.flatMap(a => a.tags))].sort()

  const filtered = articles.filter(a => {
    if (activeTag && !a.tags.includes(activeTag)) return false
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

  const toggleCollapse = (id: string) =>
    setCollapsed(prev => ({ ...prev, [id]: !prev[id] }))

  const handleTagClick = (tag: string) => {
    setActiveTag(prev => (prev === tag ? null : tag))
    setSearch('')
  }

  return (
    <div className="kb-page">
      <div className="kb-header">
        <div className="kb-header-text">
          <h1><BookOpen size={24} /> {t('kb.title')}</h1>
          <p>{t('kb.description')}</p>
        </div>
      </div>

      <div className="kb-toolbar">
        <div className="kb-search">
          <Search size={16} />
          <input
            type="text"
            placeholder={t('kb.search')}
            value={search}
            onChange={e => { setSearch(e.target.value); setActiveTag(null) }}
          />
          {(search || activeTag) && (
            <button className="kb-search-clear" onClick={() => { setSearch(''); setActiveTag(null) }}>
              <X size={14} />
            </button>
          )}
        </div>
        {allTags.length > 0 && (
          <div className="kb-tags-bar">
            {allTags.map(tag => (
              <button
                key={tag}
                className={`kb-tag-chip${activeTag === tag ? ' active' : ''}`}
                onClick={() => handleTagClick(tag)}
              >
                {tag}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <div className="kb-loading">{t('kb.loading')}</div>
      ) : filtered.length === 0 ? (
        <div className="kb-empty">{search || activeTag ? t('kb.noResults') : t('kb.empty')}</div>
      ) : (
        <div className="kb-sections">
          {grouped.map(group => {
            const CatIcon = group.icon
            const isCollapsed = collapsed[group.id] ?? false
            return (
              <section key={group.id} className="kb-cat">
                <button className="kb-cat-header" onClick={() => toggleCollapse(group.id)}>
                  <div className="kb-cat-icon" style={{ color: group.color }}>
                    <CatIcon size={18} />
                  </div>
                  <h2 className="kb-cat-title">{t(`kb.cat.${group.id}`)}</h2>
                  <span className="kb-cat-count">{group.articles.length}</span>
                  <ChevronDown size={16} className={`kb-cat-chevron${isCollapsed ? '' : ' open'}`} />
                </button>
                {!isCollapsed && (
                  <div className="kb-cat-list">
                    {group.articles.map(article => (
                      <ArticleRow key={article.slug} article={article} lang={lang} navigate={navigate} />
                    ))}
                  </div>
                )}
              </section>
            )
          })}
          {ungrouped.length > 0 && (
            <div className="kb-cat-list">
              {ungrouped.map(article => (
                <ArticleRow key={article.slug} article={article} lang={lang} navigate={navigate} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ArticleRow({ article, lang, navigate }: { article: Article; lang: string; navigate: ReturnType<typeof useNavigate> }) {
  const Icon = ICON_MAP[article.icon] || FileText
  const desc = article.description[lang] || article.description.en || ''
  return (
    <button
      className="kb-row"
      onClick={() => navigate(`/kb/${article.slug}`)}
      title={desc}
    >
      <Icon size={16} className="kb-row-icon" />
      <span className="kb-row-title">{article.title[lang] || article.title.en}</span>
      <span className="kb-row-date">{article.createdAt}</span>
    </button>
  )
}
