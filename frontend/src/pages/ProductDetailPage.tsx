import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { getProduct } from '../api/products'
import { listDocuments } from '../api/documents'
import { DocumentsPage } from './DocumentsPage'
import type { ProductDetail } from '../types'

export function ProductDetailPage({ onUploadClick }: { onUploadClick: () => void }) {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [product, setProduct] = useState<ProductDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    getProduct(Number(id))
      .then(setProduct)
      .catch(() => navigate('/app/products'))
      .finally(() => setLoading(false))
  }, [id, navigate])

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

  return (
    <div className="docs-page">
      <div className="product-detail-header">
        <button className="product-back-btn" onClick={() => navigate('/app/products')}>
          <ArrowLeft size={18} />
          {t('products.title')}
        </button>
        <h1 className="docs-page-title" style={{ marginTop: 8 }}>
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
      <DocumentsPage onUploadClick={onUploadClick} productId={Number(id)} />
    </div>
  )
}
