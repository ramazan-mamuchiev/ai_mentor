import { apiFetch } from './client'
import type { ProductListItem, ProductDetail, ProductDebugInfo, ProductSearchKeysResponse, ProductUsageStats, SuggestionChip } from '../types'

export async function listProducts(): Promise<ProductListItem[]> {
  return apiFetch<ProductListItem[]>('/products')
}

export async function getProduct(productId: number): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${productId}`)
}

export async function getProductBySlug(slug: string): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/by-slug/${encodeURIComponent(slug)}`)
}

export async function updateProduct(
  productId: number,
  data: { name?: string; manufacturer?: string; category?: string; version?: string; firmware_version_id?: number | null },
): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${productId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export interface DeleteProductResult {
  product_id: number
  task_id: string
  total_documents: number
}

export async function deleteProduct(productId: number): Promise<DeleteProductResult> {
  return apiFetch<DeleteProductResult>(`/products/${productId}`, { method: 'DELETE' })
}

export async function reingestProduct(productId: number): Promise<{ product_id: number; status: string; documents_queued: number }> {
  return apiFetch(`/products/${productId}/reingest`, { method: 'POST' })
}

export async function syncProduct(productId: number): Promise<{ product_id: number; status: string; documents_queued: number; placeholders_queued: number }> {
  return apiFetch(`/products/${productId}/sync`, { method: 'POST' })
}

export async function cancelProductIngestion(productId: number): Promise<void> {
  return apiFetch<void>(`/products/${productId}/cancel-ingestion`, { method: 'POST' })
}

export async function getProductDebug(productId: number): Promise<ProductDebugInfo> {
  return apiFetch<ProductDebugInfo>(`/products/${productId}/debug`)
}

export async function getProductUsageStats(productId: number): Promise<ProductUsageStats> {
  return apiFetch<ProductUsageStats>(`/products/${productId}/usage-stats`)
}

export async function getProductSearchKeys(productId: number): Promise<ProductSearchKeysResponse> {
  return apiFetch<ProductSearchKeysResponse>(`/products/${productId}/search-keys`)
}

export async function getSuggestions(): Promise<SuggestionChip[]> {
  return apiFetch<SuggestionChip[]>('/products/suggestions')
}

export interface ProductSuggestion {
  id: number
  name: string
  manufacturer: string
  firmware_versions: Array<{ id: number; version: string }>
}

export async function suggestProducts(q: string = '', limit: number = 20): Promise<ProductSuggestion[]> {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  params.set('limit', String(limit))
  return apiFetch<ProductSuggestion[]>(`/products/suggest?${params}`)
}
