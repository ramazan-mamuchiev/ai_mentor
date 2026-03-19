import { Filter } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface Props {
  product: string
  onChange: (product: string) => void
  products: string[]
}

export function DeviceFilter({ product, onChange, products }: Props) {
  const { t } = useTranslation()
  return (
    <div className="device-filter">
      <Filter size={14} />
      <select value={product} onChange={e => onChange(e.target.value)}>
        <option value="">{t('filter.all')}</option>
        {products.map(d => (
          <option key={d} value={d}>{d}</option>
        ))}
      </select>
    </div>
  )
}
