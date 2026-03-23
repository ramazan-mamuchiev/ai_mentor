import { apiFetch } from './client'
import type { ProductListItem, ProductDetail, ProductDebugInfo } from '../types'

export async function listProducts(): Promise<ProductListItem[]> {
  return apiFetch<ProductListItem[]>('/products')
}

export async function getProduct(id: number): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${id}`)
}

export async function updateProduct(
  id: number,
  data: { name?: string; manufacturer?: string; model?: string; category?: string },
): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteProduct(id: number): Promise<void> {
  return apiFetch<void>(`/products/${id}`, { method: 'DELETE' })
}

export async function getProductDebug(id: number): Promise<ProductDebugInfo> {
  return apiFetch<ProductDebugInfo>(`/products/${id}/debug`)
}
