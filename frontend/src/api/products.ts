import { apiFetch } from './client'
import type { ProductListItem, ProductDetail, ProductDebugInfo, ProductUsageStats, SuggestionChip } from '../types'

export async function listProducts(): Promise<ProductListItem[]> {
  return apiFetch<ProductListItem[]>('/products')
}

export async function getProduct(manufacturerSlug: string, productSlug: string): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${manufacturerSlug}/${productSlug}`)
}

export async function updateProduct(
  manufacturerSlug: string,
  productSlug: string,
  data: { name?: string; manufacturer?: string; model?: string; category?: string; category_id?: number | null; tag_ids?: number[] },
): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${manufacturerSlug}/${productSlug}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteProduct(manufacturerSlug: string, productSlug: string): Promise<void> {
  return apiFetch<void>(`/products/${manufacturerSlug}/${productSlug}`, { method: 'DELETE' })
}

export async function reingestProduct(manufacturerSlug: string, productSlug: string): Promise<{ product_id: number; status: string; documents_queued: number }> {
  return apiFetch(`/products/${manufacturerSlug}/${productSlug}/reingest`, { method: 'POST' })
}

export async function cancelProductIngestion(manufacturerSlug: string, productSlug: string): Promise<void> {
  return apiFetch<void>(`/products/${manufacturerSlug}/${productSlug}/cancel-ingestion`, { method: 'POST' })
}

export async function getProductDebug(manufacturerSlug: string, productSlug: string): Promise<ProductDebugInfo> {
  return apiFetch<ProductDebugInfo>(`/products/${manufacturerSlug}/${productSlug}/debug`)
}

export async function getProductUsageStats(manufacturerSlug: string, productSlug: string): Promise<ProductUsageStats> {
  return apiFetch<ProductUsageStats>(`/products/${manufacturerSlug}/${productSlug}/usage-stats`)
}

export async function getSuggestions(): Promise<SuggestionChip[]> {
  return apiFetch<SuggestionChip[]>('/products/suggestions')
}

export interface ProductSuggestion {
  id: number
  name: string
  manufacturer: string
  slug: string
  manufacturer_slug: string
  category_slug: string | null
  firmware_versions: Array<{ id: number; version: string }>
}

export interface ProductCategoryPublic {
  id: number
  slug: string
  count: number
}

export interface ProductTagPublic {
  id: number
  slug: string
  count: number
}

export async function suggestProducts(q: string = '', limit: number = 20): Promise<ProductSuggestion[]> {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  params.set('limit', String(limit))
  return apiFetch<ProductSuggestion[]>(`/products/suggest?${params}`)
}

export async function listProductCategories(): Promise<ProductCategoryPublic[]> {
  return apiFetch<ProductCategoryPublic[]>('/products/categories')
}

export async function listProductTags(): Promise<ProductTagPublic[]> {
  return apiFetch<ProductTagPublic[]>('/products/tags')
}
