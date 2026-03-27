import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { getProduct } from '../api/products'
import { DocumentsPage } from './DocumentsPage'
import type { ProductDetail } from '../types'
import type { ProductContext } from '../components/FileUpload'

interface ProductDetailPageProps {
  onUploadClick: (ctx?: ProductContext) => void
  onUrlImportClick?: (ctx?: ProductContext) => void
}

export function ProductDetailPage({ onUploadClick, onUrlImportClick }: ProductDetailPageProps) {
  const { t } = useTranslation()
  const { manufacturer, product: productSlug } = useParams<{ manufacturer: string; product: string }>()
  const navigate = useNavigate()
  const [product, setProduct] = useState<ProductDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!manufacturer || !productSlug) return
    setLoading(true)
    getProduct(manufacturer, productSlug)
      .then(setProduct)
      .catch(() => navigate('/app/products'))
      .finally(() => setLoading(false))
  }, [manufacturer, productSlug, navigate])

  const productCtx = useMemo<ProductContext | undefined>(() =>
    product ? {
      name: product.name,
      manufacturer: product.manufacturer || undefined,
      version: product.firmware_versions[0] || undefined,
    } : undefined,
    [product?.name, product?.manufacturer, product?.firmware_versions],
  )

  const handleUploadClick = useCallback(() => {
    onUploadClick(productCtx)
  }, [onUploadClick, productCtx])

  const handleUrlImportClick = useCallback(() => {
    onUrlImportClick?.(productCtx)
  }, [onUrlImportClick, productCtx])

  if (loading) {
    return (
      <div className="docs-page">
        <div className="docs-empty">
          <Loader2 size={32} className="spin-icon docs-empty-icon" />
        </div>
      </div>
    )
  }

  if (!product) return null

  const productHeader = (
    <div className="product-detail-header">
      <button className="product-back-btn" onClick={() => navigate('/app/products')}>
        <ArrowLeft size={18} />
        {t('products.title')}
      </button>
      <h1 className="product-detail-title">
        {product.name}
        {product.manufacturer && <span className="product-manufacturer"> — {product.manufacturer}</span>}
      </h1>
      {product.firmware_versions.length > 0 && (
        <div className="product-versions">
          {product.firmware_versions.map(v => (
            <span key={v} className="docs-format-badge">{v}</span>
          ))}
        </div>
      )}
    </div>
  )

  return (
    <DocumentsPage
      onUploadClick={handleUploadClick}
      onUrlImportClick={handleUrlImportClick}
      productId={product.id}
      headerSlot={productHeader}
    />
  )
}
