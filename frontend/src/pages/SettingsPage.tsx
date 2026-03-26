import { useCallback, useEffect, useState } from 'react'
import { Copy, Key, Plus, Trash2, Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getApiKeys, createApiKey, deleteApiKey, type ApiKeyItem, type ApiKeyCreated } from '../auth/api'
import { useAuth } from '../auth/AuthContext'

export function SettingsPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [keys, setKeys] = useState<ApiKeyItem[]>([])
  const [loading, setLoading] = useState(true)
  const [newKey, setNewKey] = useState<ApiKeyCreated | null>(null)
  const [keyName, setKeyName] = useState('')
  const [creating, setCreating] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await getApiKeys()
      setKeys(data)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const handleCreate = async () => {
    setCreating(true)
    try {
      const created = await createApiKey(keyName || 'Default')
      setNewKey(created)
      setKeyName('')
      await load()
    } catch { /* ignore */ }
    setCreating(false)
  }

  const handleDelete = async (id: string) => {
    await deleteApiKey(id)
    await load()
  }

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopied(id)
    setTimeout(() => setCopied(null), 2000)
  }

  const mcpConfig = newKey ? JSON.stringify({
    mcpServers: {
      lexiro: {
        url: `${window.location.origin}/mcp`,
        headers: {
          Authorization: `Bearer ${newKey.key}`,
        },
      },
    },
  }, null, 2) : null

  return (
    <div className="settings-page">
      <h1 className="settings-title">{t('settings.title')}</h1>

      <section className="settings-section">
        <h2 className="settings-section-title">
          <Key size={20} /> {t('auth.apiKeys')}
        </h2>
        <p className="settings-hint">{t('settings.apiKeysHint')}</p>

        <div className="api-key-create">
          <input
            value={keyName}
            onChange={e => setKeyName(e.target.value)}
            placeholder={t('settings.keyNamePlaceholder')}
            className="auth-input"
          />
          <button onClick={handleCreate} disabled={creating} className="btn-primary">
            <Plus size={16} />
            {t('settings.createKey')}
          </button>
        </div>

        {newKey && (
          <div className="api-key-new">
            <p className="api-key-warning">{t('settings.keyShownOnce')}</p>
            <div className="api-key-value">
              <code>{newKey.key}</code>
              <button
                onClick={() => handleCopy(newKey.key, 'new-key')}
                className="btn-icon"
                data-tooltip={t('chat.copy')}
              >
                {copied === 'new-key' ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>

            <h4>{t('settings.mcpConfig')}</h4>
            <div className="api-key-value mcp-config">
              <pre>{mcpConfig}</pre>
              <button
                onClick={() => handleCopy(mcpConfig!, 'mcp-config')}
                className="btn-icon"
                data-tooltip={t('chat.copy')}
              >
                {copied === 'mcp-config' ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <p className="settings-loading">{t('settings.loading')}</p>
        ) : keys.length === 0 ? (
          <p className="settings-empty">{t('settings.noKeys')}</p>
        ) : (
          <table className="api-keys-table">
            <thead>
              <tr>
                <th>{t('settings.keyName')}</th>
                <th>{t('settings.keyPrefix')}</th>
                <th>{t('settings.keyCreated')}</th>
                <th>{t('settings.keyLastUsed')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {keys.map(k => (
                <tr key={k.id}>
                  <td>{k.name || '—'}</td>
                  <td><code>{k.key_prefix}</code></td>
                  <td>{new Date(k.created_at).toLocaleDateString()}</td>
                  <td>{k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : '—'}</td>
                  <td>
                    <button onClick={() => handleDelete(k.id)} className="btn-icon btn-danger" data-tooltip={t('settings.deleteKey')}>
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
