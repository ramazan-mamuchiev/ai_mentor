import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listProducts,
  getProduct,
  updateProduct,
  deleteProduct,
  getProductDebug,
  suggestProducts,
  listProductCategories,
  listProductTags,
} from '../../api/products'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('listProducts', () => {
  it('calls correct API endpoint', async () => {
    const products = [
      { id: 1, name: 'Camera', total_documents: 3, formats: [] },
    ]

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(products),
    }))

    const result = await listProducts()
    expect(result).toEqual(products)
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/products',
      expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })
})

describe('getProduct', () => {
  it('calls correct API endpoint', async () => {
    const product = { id: 1, name: 'Camera', firmware_versions: ['1.0'] }

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(product),
    }))

    const result = await getProduct('acme', 'camera-one')
    expect(result).toEqual(product)
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/products/acme/camera-one',
      expect.anything(),
    )
  })

  it('throws on 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: () => Promise.resolve('Not found'),
    }))

    await expect(getProduct('x', 'y')).rejects.toThrow('API error 404')
  })
})

describe('updateProduct', () => {
  it('sends PATCH with body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: 1, name: 'Updated' }),
    }))

    await updateProduct('acme', 'camera-one', { name: 'Updated' })
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/products/acme/camera-one',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ name: 'Updated' }),
      }),
    )
  })
})

describe('deleteProduct', () => {
  it('sends DELETE request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    }))

    await deleteProduct('acme', 'camera-one')
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/products/acme/camera-one',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})

describe('getProductDebug', () => {
  it('calls correct API endpoint', async () => {
    const debugData = {
      product_id: 1,
      product_name: 'Camera',
      total_documents: 3,
      total_chunks: 50,
    }

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(debugData),
    }))

    const result = await getProductDebug('acme', 'camera-one')
    expect(result).toEqual(debugData)
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/products/acme/camera-one/debug',
      expect.anything(),
    )
  })
})

describe('suggestProducts', () => {
  it('calls suggest endpoint with query and limit', async () => {
    const suggestions = [{ id: 1, name: 'Cam', manufacturer: 'Acme', slug: 'cam', manufacturer_slug: 'acme', category_slug: null, firmware_versions: [] }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(suggestions),
    }))

    const result = await suggestProducts('cam', 10)
    expect(result).toEqual(suggestions)
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/products/suggest?q=cam&limit=10',
      expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })
})

describe('listProductCategories', () => {
  it('calls categories endpoint', async () => {
    const categories = [{ id: 1, slug: 'cams', icon: 'box', count: 2 }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(categories),
    }))

    const result = await listProductCategories()
    expect(result).toEqual(categories)
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/products/categories',
      expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })
})

describe('listProductTags', () => {
  it('calls tags endpoint', async () => {
    const tags = [{ id: 1, slug: 'ip', count: 5 }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(tags),
    }))

    const result = await listProductTags()
    expect(result).toEqual(tags)
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/products/tags',
      expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })
})
