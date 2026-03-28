import { apiFetch } from './client'
import type { ProductListItem, ProductDetail, ProductDebugInfo, ProductUsageStats, SuggestionChip } from '../types'

export async function listProducts(): Promise<ProductListItem[]> {
  return apiFetch<ProductListItem[]>('/products')
}

export async function getProduct(productId: number): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${productId}`)
}

export async function updateProduct(
  productId: number,
  data: { name?: string; manufacturer?: string; model?: string; category?: string },
): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${productId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteProduct(productId: number): Promise<void> {
  return apiFetch<void>(`/products/${productId}`, { method: 'DELETE' })
}

export async function reingestProduct(productId: number): Promise<{ product_id: number; status: string; documents_queued: number }> {
  return apiFetch(`/products/${productId}/reingest`, { method: 'POST' })
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
