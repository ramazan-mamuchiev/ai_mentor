import { Filter } from 'lucide-react'

interface Props {
  product: string
  onChange: (product: string) => void
  products: string[]
}

export function DeviceFilter({ product, onChange, products }: Props) {
  return (
    <div className="device-filter">
      <Filter size={14} />
      <select value={product} onChange={e => onChange(e.target.value)}>
        <option value="">All products</option>
        {products.map(d => (
          <option key={d} value={d}>{d}</option>
        ))}
      </select>
    </div>
  )
}
