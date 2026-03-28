import { apiFetch } from './client'

export interface AdminLanguage {
  id: number
  code: string
  name_native: string
  is_default: boolean
  is_active: boolean
  is_system: boolean
  sort_order: number
  total_keys: number
  created_at: string | null
}

export async function adminListLanguages(): Promise<AdminLanguage[]> {
  return apiFetch<AdminLanguage[]>('/admin/i18n/languages')
}

export async function adminCreateLanguage(data: { code: string; name_native: string; sort_order?: number }): Promise<{ id: number; code: string }> {
  return apiFetch('/admin/i18n/languages', { method: 'POST', body: JSON.stringify(data) })
}

export async function adminPatchLanguage(id: number, data: Partial<{ name_native: string; is_active: boolean; is_default: boolean; sort_order: number }>): Promise<void> {
  return apiFetch(`/admin/i18n/languages/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export async function adminDeleteLanguage(id: number): Promise<void> {
  return apiFetch(`/admin/i18n/languages/${id}`, { method: 'DELETE' })
}

export interface TranslationItem {
  id: number
  key: string
  value: string
  is_system: boolean
  updated_at: string | null
}

export interface TranslationListResponse {
  items: TranslationItem[]
  total: number
  page: number
  page_size: number
}

export async function adminListTranslations(languageId: number, ns: string = 'ui', page: number = 1, pageSize: number = 100, search?: string): Promise<TranslationListResponse> {
  const params = new URLSearchParams({ ns, page: String(page), page_size: String(pageSize) })
  if (search) params.set('search', search)
  return apiFetch(`/admin/i18n/translations/${languageId}?${params}`)
}

export async function adminUpsertTranslation(languageId: number, data: { namespace: string; key: string; value: string }): Promise<void> {
  return apiFetch(`/admin/i18n/translations/${languageId}`, { method: 'PUT', body: JSON.stringify(data) })
}

export async function adminBulkUpsertTranslations(languageId: number, items: Array<{ namespace: string; key: string; value: string }>): Promise<void> {
  return apiFetch(`/admin/i18n/translations/${languageId}/bulk`, { method: 'POST', body: JSON.stringify({ items }) })
}

export async function adminTriggerTranslate(languageId: number): Promise<{ task_id: string; status: string }> {
  return apiFetch(`/admin/i18n/languages/${languageId}/translate`, { method: 'POST' })
}

export async function adminGetTranslateProgress(languageId: number): Promise<{ total: number; done: number; errors: number; status: string }> {
  return apiFetch(`/admin/i18n/languages/${languageId}/translate/progress`)
}

export async function adminExportTranslations(languageId: number, ns: string = 'ui'): Promise<Record<string, string>> {
  return apiFetch(`/admin/i18n/translations/${languageId}/export?ns=${ns}`)
}
