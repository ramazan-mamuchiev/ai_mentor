import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Plus, Shield, Trash2, Lock } from 'lucide-react'
import { listRoles, createRole, deleteRole, type RoleListItem } from '../../api/admin'

export function RolesPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [roles, setRoles] = useState<RoleListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newSlug, setNewSlug] = useState('')
  const [newName, setNewName] = useState('')
  const [newPriority, setNewPriority] = useState(0)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setRoles(await listRoles())
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleCreate = async () => {
    try {
      const role = await createRole({ slug: newSlug, name: newName, priority: newPriority })
      setShowCreate(false)
      setNewSlug('')
      setNewName('')
      setNewPriority(0)
      navigate(`/app/admin/roles/${role.id}`)
    } catch (e: any) {
      setError(e.message)
    }
  }

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(t('admin.roles.confirmDelete', { name }))) return
    try {
      await deleteRole(id)
      load()
    } catch (e: any) {
      setError(e.message)
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-page-header">
        <h1><Shield size={20} /> {t('admin.roles.title')}</h1>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <Plus size={14} /> {t('admin.roles.newRole')}
        </button>
      </div>

      {error && <div className="admin-error">{error}</div>}

      {showCreate && (
        <div className="admin-card" style={{ marginBottom: 16 }}>
          <h3>{t('admin.roles.createRole')}</h3>
          <div className="admin-form-row">
            <label>{t('admin.roles.slug')}</label>
            <input value={newSlug} onChange={e => setNewSlug(e.target.value)} placeholder={t('admin.roles.slugPlaceholder')} />
          </div>
          <div className="admin-form-row">
            <label>{t('admin.roles.name')}</label>
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder={t('admin.roles.namePlaceholder')} />
          </div>
          <div className="admin-form-row">
            <label>{t('admin.roles.priority')}</label>
            <input type="number" value={newPriority} onChange={e => setNewPriority(Number(e.target.value))} />
          </div>
          <div className="admin-form-actions">
            <button className="btn btn-primary" onClick={handleCreate} disabled={!newSlug || !newName}>{t('admin.common.create')}</button>
            <button className="btn" onClick={() => setShowCreate(false)}>{t('admin.common.cancel')}</button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="admin-loading">{t('admin.common.loading')}</div>
      ) : (
        <table className="admin-table">
          <thead>
            <tr>
              <th>{t('admin.roles.slug')}</th>
              <th>{t('admin.roles.name')}</th>
              <th>{t('admin.roles.priority')}</th>
              <th>{t('admin.roles.tenants')}</th>
              <th>{t('admin.roles.system')}</th>
              <th>{t('admin.common.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {roles.map(role => (
              <tr key={role.id} className="admin-table-row-clickable" onClick={() => navigate(`/app/admin/roles/${role.id}`)}>
                <td><code>{role.slug}</code></td>
                <td>{role.name}</td>
                <td>{role.priority}</td>
                <td>{role.tenants_count}</td>
                <td>{role.is_system ? <Lock size={14} /> : '—'}</td>
                <td onClick={e => e.stopPropagation()}>
                  {!role.is_system && (
                    <button className="btn btn-danger btn-sm" onClick={() => handleDelete(role.id, role.name)}>
                      <Trash2 size={14} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
