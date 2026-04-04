import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2, Activity } from 'lucide-react'
import { getProductBySlug } from '../api/products'
import { DocumentsPage } from './DocumentsPage'
import { ProductLifecycleModal } from '../components/ProductLifecycleModal'
import { usePermission } from '../auth/usePermission'
import type { ProductDetail } from '../types'
import type { ProductContext } from '../components/FileUpload'

interface ProductDetailPageProps {
  onUploadClick?: (ctx?: ProductContext) => void
  onUrlImportClick?: (ctx?: ProductContext) => void
}

export function ProductDetailPage({ onUploadClick, onUrlImportClick }: ProductDetailPageProps) {
  const { t } = useTranslation()
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const canLifecycle = usePermission('lifecycle.run')
  const [product, setProduct] = useState<ProductDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [showLifecycle, setShowLifecycle] = useState(false)

  useEffect(() => {
    if (!slug) return
    setLoading(true)
    getProductBySlug(slug)
      .then(setProduct)
      .catch(() => navigate('/app/products'))
      .finally(() => setLoading(false))
  }, [slug, navigate])

  const productCtx = useMemo<ProductContext | undefined>(() =>
    product ? {
      name: product.name,
      manufacturer: product.manufacturer || undefined,
      version: product.firmware_versions[0] || undefined,
    } : undefined,
    [product?.name, product?.manufacturer, product?.firmware_versions],
  )

  const handleUploadClick = useCallback(() => {
    onUploadClick?.(productCtx)
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
      <div className="product-detail-title-row">
        <h1 className="product-detail-title">
          {product.name}
          {product.manufacturer && <span className="product-manufacturer"> — {product.manufacturer}</span>}
        </h1>
        <button
          className="product-lifecycle-btn"
          onClick={() => setShowLifecycle(true)}
          title={t('lifecycleModal.title')}
        >
          <Activity size={14} />
          API Lifecycle
        </button>
      </div>
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
    <>
      <DocumentsPage
        onUploadClick={onUploadClick ? handleUploadClick : undefined}
        onUrlImportClick={onUrlImportClick ? handleUrlImportClick : undefined}
        productId={product.id}
        headerSlot={productHeader}
      />
      {showLifecycle && (
        <ProductLifecycleModal
          productId={product.id}
          productName={product.name}
          canRun={canLifecycle}
          onClose={() => setShowLifecycle(false)}
        />
      )}
    </>
  )
}
