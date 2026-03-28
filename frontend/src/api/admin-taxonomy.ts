import { apiFetch } from './client'

export interface CategoryItem {
  id: number
  slug: string
  icon: string
  sort_order: number
  is_system: boolean
  product_count: number
  labels: Record<string, string>
}

export interface TagItem {
  id: number
  slug: string
  is_system: boolean
  product_count: number
  labels: Record<string, string>
}

export interface KeywordItem {
  id: number
  product_id: number
  keyword: string
  is_system: boolean
}

export async function adminListCategories(): Promise<CategoryItem[]> {
  return apiFetch<CategoryItem[]>('/admin/taxonomy/categories')
}

export async function adminCreateCategory(data: { slug: string; icon?: string; sort_order?: number; labels?: Record<string, string> }): Promise<{ id: number; slug: string }> {
  return apiFetch('/admin/taxonomy/categories', { method: 'POST', body: JSON.stringify(data) })
}

export async function adminPatchCategory(id: number, data: { icon?: string; sort_order?: number; labels?: Record<string, string> }): Promise<void> {
  return apiFetch(`/admin/taxonomy/categories/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export async function adminDeleteCategory(id: number): Promise<void> {
  return apiFetch(`/admin/taxonomy/categories/${id}`, { method: 'DELETE' })
}

export async function adminReorderCategories(items: Array<{ id: number; sort_order: number }>): Promise<void> {
  return apiFetch('/admin/taxonomy/categories/reorder', { method: 'POST', body: JSON.stringify({ items }) })
}

export async function adminListTags(): Promise<TagItem[]> {
  return apiFetch<TagItem[]>('/admin/taxonomy/tags')
}

export async function adminCreateTag(data: { slug: string; labels?: Record<string, string> }): Promise<{ id: number; slug: string }> {
  return apiFetch('/admin/taxonomy/tags', { method: 'POST', body: JSON.stringify(data) })
}

export async function adminPatchTag(id: number, data: { labels?: Record<string, string> }): Promise<void> {
  return apiFetch(`/admin/taxonomy/tags/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export async function adminDeleteTag(id: number): Promise<void> {
  return apiFetch(`/admin/taxonomy/tags/${id}`, { method: 'DELETE' })
}

export async function adminListKeywords(productId?: number): Promise<KeywordItem[]> {
  const params = productId ? `?product_id=${productId}` : ''
  return apiFetch<KeywordItem[]>(`/admin/taxonomy/keywords${params}`)
}

export async function adminCreateKeyword(data: { product_id: number; keyword: string }): Promise<{ id: number }> {
  return apiFetch('/admin/taxonomy/keywords', { method: 'POST', body: JSON.stringify(data) })
}

export async function adminDeleteKeyword(id: number): Promise<void> {
  return apiFetch(`/admin/taxonomy/keywords/${id}`, { method: 'DELETE' })
}
