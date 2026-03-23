import { apiFetch } from './client'
import type { ProductListItem, ProductDetail, ProductDebugInfo } from '../types'

export async function listProducts(): Promise<ProductListItem[]> {
  return apiFetch<ProductListItem[]>('/products')
}

export async function getProduct(manufacturerSlug: string, productSlug: string): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${manufacturerSlug}/${productSlug}`)
}

export async function updateProduct(
  manufacturerSlug: string,
  productSlug: string,
  data: { name?: string; manufacturer?: string; model?: string; category?: string },
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

export async function getProductDebug(manufacturerSlug: string, productSlug: string): Promise<ProductDebugInfo> {
  return apiFetch<ProductDebugInfo>(`/products/${manufacturerSlug}/${productSlug}/debug`)
}
