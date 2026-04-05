import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Link2, Search, X, Copy, Check, ExternalLink, Trash2, RefreshCw,
} from 'lucide-react'
import {
  listSharedLinksAdmin, deactivateSharedLinkAdmin,
  type AdminSharedLinkItem, type TenantSearchResult,
} from '../../api/admin'
import { TenantFilterCombo } from '../../components/TenantFilterCombo'

const SHARE_TYPES = [
  { value: '', label: 'All' },
  { value: 'session', label: 'Chat' },
  { value: 'message', label: 'Answer' },
  { value: 'debug_chat', label: 'Debug (chat)' },
  { value: 'debug_document', label: 'Debug (doc)' },
  { value: 'debug_product', label: 'Debug (product)' },
  { value: 'document_preview', label: 'Document' },
  { value: 'lifecycle', label: 'Lifecycle' },
] as const

const STATUS_OPTIONS = [
  { value: '', labelKey: 'admin.sharedLinks.statusAll' },
  { value: 'true', labelKey: 'admin.sharedLinks.statusActive' },
  { value: 'false', labelKey: 'admin.sharedLinks.statusInactive' },
] as const

export function SharedLinksPage() {
  const { t } = useTranslation()
  const [items, setItems] = useState<AdminSharedLinkItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const pageSize = 50
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [shareType, setShareType] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [tenantFilter, setTenantFilter] = useState<TenantSearchResult | null>(null)
  const [copiedToken, setCopiedToken] = useState<string | null>(null)
  const [revokeToken, setRevokeToken] = useState<string | null>(null)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 400)
    return () => clearTimeout(timer)
  }, [search])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listSharedLinksAdmin({
        page,
        page_size: pageSize,
        tenant_id: tenantFilter?.id || undefined,
        share_type: shareType || undefined,
        is_active: statusFilter === '' ? undefined : statusFilter === 'true',
        search: debouncedSearch || undefined,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch { /* ignore */ }
    setLoading(false)
  }, [page, pageSize, tenantFilter, shareType, statusFilter, debouncedSearch])

  useEffect(() => { load() }, [load])
  useEffect(() => { setPage(1) }, [tenantFilter, shareType, statusFilter, debouncedSearch])

  const handleRevoke = async (token: string) => {
    try {
      await deactivateSharedLinkAdmin(token)
      setItems(prev => prev.map(i => i.token === token ? { ...i, is_active: false } : i))
    } catch { /* ignore */ }
    setRevokeToken(null)
  }

  const handleCopy = (url: string, token: string) => {
    navigator.clipboard.writeText(url)
    setCopiedToken(token)
    setTimeout(() => setCopiedToken(null), 2000)
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="logs-page">
      <div className="admin-page-header">
        <h1><Link2 size={20} /> {t('admin.sharedLinks.title')}</h1>
        <p>{t('admin.sharedLinks.subtitle')}</p>
      </div>

      <div className="logs-toolbar">
        <div className="logs-toolbar__row">
          <select
            className="logs-select"
            value={shareType}
            onChange={e => setShareType(e.target.value)}
          >
            {SHARE_TYPES.map(st => (
              <option key={st.value} value={st.value}>
                {st.value ? st.label : t('admin.sharedLinks.allTypes')}
              </option>
            ))}
          </select>

          <select
            className="logs-select"
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
          >
            {STATUS_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{t(opt.labelKey)}</option>
            ))}
          </select>

          <TenantFilterCombo value={tenantFilter} onChange={setTenantFilter} />

          <div className="logs-search-wrap">
            <Search size={14} className="logs-search-wrap__icon" />
            <input
              className="logs-search"
              placeholder={t('admin.sharedLinks.searchPlaceholder')}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button
                className="logs-search-wrap__clear"
                onClick={() => setSearch('')}
                aria-label={t('admin.logs.clear')}
              >
                <X size={14} />
              </button>
            )}
          </div>

          <button className="logs-icon-btn" onClick={load}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
        </div>

        <div className="logs-toolbar__row">
          <span className="logs-count">
            {t('admin.sharedLinks.count', { count: total })}
          </span>
        </div>
      </div>

      {loading ? (
        <div className="admin-loading">{t('admin.common.loading')}</div>
      ) : items.length === 0 ? (
        <div className="admin-empty">{t('admin.sharedLinks.noLinks')}</div>
      ) : (
        <>
          <div className="admin-table-wrap">
            <table className="admin-table shared-links-admin-table">
              <thead>
                <tr>
                  <th>{t('admin.sharedLinks.colTitle')}</th>
                  <th>{t('admin.sharedLinks.colType')}</th>
                  <th>{t('admin.sharedLinks.colTenant')}</th>
                  <th className="hide-mobile">{t('admin.sharedLinks.colViews')}</th>
                  <th className="hide-mobile">{t('admin.sharedLinks.colStatus')}</th>
                  <th className="hide-mobile">{t('admin.sharedLinks.colCreated')}</th>
                  <th>{t('admin.common.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map(link => (
                  <tr key={link.token} className={!link.is_active ? 'row-revoked' : ''}>
                    <td className="shared-link-title-cell">
                      <span className="shared-link-title-text">{link.title || '—'}</span>
                    </td>
                    <td>
                      <span className={`shared-link-type-badge shared-link-type--${link.share_type}`}>
                        {SHARE_TYPES.find(st => st.value === link.share_type)?.label || link.share_type}
                      </span>
                    </td>
                    <td className="shared-link-tenant-cell">
                      <span>{link.tenant_email || '—'}</span>
                    </td>
                    <td className="hide-mobile">{link.view_count}</td>
                    <td className="hide-mobile">
                      {link.is_active ? (
                        <span className="status-badge status-badge--active">{t('admin.sharedLinks.active')}</span>
                      ) : (
                        <span className="status-badge status-badge--inactive">{t('admin.sharedLinks.inactive')}</span>
                      )}
                    </td>
                    <td className="hide-mobile">{new Date(link.created_at).toLocaleDateString()}</td>
                    <td className="shared-link-actions">
                      <button
                        className="btn-icon"
                        onClick={() => handleCopy(link.url, link.token)}
                        title={t('share.copyLink')}
                      >
                        {copiedToken === link.token ? <Check size={14} /> : <Copy size={14} />}
                      </button>
                      <a
                        className="btn-icon"
                        href={link.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={t('settings.sharedLinkOpen')}
                      >
                        <ExternalLink size={14} />
                      </a>
                      {link.is_active && (
                        <button
                          className="btn-icon btn-danger"
                          onClick={() => setRevokeToken(link.token)}
                          title={t('share.deactivate')}
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="admin-pagination">
              <button
                className="btn-secondary"
                disabled={page <= 1}
                onClick={() => setPage(p => p - 1)}
              >
                {t('admin.common.prev')}
              </button>
              <span className="admin-pagination__info">
                {t('admin.common.page', { page, total: totalPages })}
              </span>
              <button
                className="btn-secondary"
                disabled={page >= totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                {t('admin.common.next')}
              </button>
            </div>
          )}
        </>
      )}

      {revokeToken && (
        <div className="api-key-modal-overlay" onClick={() => setRevokeToken(null)}>
          <div className="api-key-modal api-key-modal--small" onClick={e => e.stopPropagation()}>
            <div className="api-key-modal-header">
              <h3>{t('settings.revokeSharedLinkTitle')}</h3>
              <button onClick={() => setRevokeToken(null)} className="btn-icon"><X size={18} /></button>
            </div>
            <p className="confirm-delete-text">{t('settings.revokeSharedLinkConfirm')}</p>
            <div className="api-key-modal-footer">
              <button onClick={() => setRevokeToken(null)} className="btn-secondary">{t('settings.cancel')}</button>
              <button onClick={() => handleRevoke(revokeToken)} className="btn-danger-solid">
                <Trash2 size={16} />
                {t('share.deactivate')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
