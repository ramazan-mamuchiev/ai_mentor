import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight, X } from 'lucide-react'
import './FilterSidebar.css'

export interface FacetValue {
  value: string
  label: string
  count: number
}

interface FacetSectionProps {
  title: string
  values: FacetValue[]
  selected: string[]
  onChange: (selected: string[]) => void
  maxVisible?: number
}

function FacetSection({ title, values, selected, onChange, maxVisible = 8 }: FacetSectionProps) {
  const [expanded, setExpanded] = useState(true)
  const [showAll, setShowAll] = useState(false)
  const { t } = useTranslation()

  const visible = showAll ? values : values.slice(0, maxVisible)
  const hasMore = values.length > maxVisible

  const toggle = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter(v => v !== value))
    } else {
      onChange([...selected, value])
    }
  }

  return (
    <div className="facet-section">
      <button className="facet-header" onClick={() => setExpanded(!expanded)}>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span>{title}</span>
        {selected.length > 0 && <span className="facet-count-badge">{selected.length}</span>}
      </button>
      {expanded && (
        <div className="facet-list">
          {visible.map(item => (
            <label key={item.value} className="facet-item">
              <input
                type="checkbox"
                checked={selected.includes(item.value)}
                onChange={() => toggle(item.value)}
              />
              <span className="facet-label">{item.label || item.value}</span>
              <span className="facet-count">{item.count}</span>
            </label>
          ))}
          {hasMore && (
            <button className="facet-show-more" onClick={() => setShowAll(!showAll)}>
              {showAll ? t('filters.showLess') : t('filters.showMore', { count: values.length - maxVisible })}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

interface ActiveFiltersProps {
  filters: Array<{ facet: string; value: string; label: string }>
  onRemove: (facet: string, value: string) => void
  onClearAll: () => void
}

export function ActiveFilters({ filters, onRemove, onClearAll }: ActiveFiltersProps) {
  const { t } = useTranslation()
  if (filters.length === 0) return null

  return (
    <div className="active-filters">
      {filters.map(f => (
        <span key={`${f.facet}-${f.value}`} className="active-filter-chip">
          {f.label}
          <button onClick={() => onRemove(f.facet, f.value)}><X size={12} /></button>
        </span>
      ))}
      <button className="active-filters-clear" onClick={onClearAll}>
        {t('filters.clearAll')}
      </button>
    </div>
  )
}

interface FilterSidebarProps {
  categories: FacetValue[]
  tags: FacetValue[]
  manufacturers: FacetValue[]
  selectedCategories: string[]
  selectedTags: string[]
  selectedManufacturers: string[]
  onCategoriesChange: (v: string[]) => void
  onTagsChange: (v: string[]) => void
  onManufacturersChange: (v: string[]) => void
}

export function FilterSidebar({
  categories, tags, manufacturers,
  selectedCategories, selectedTags, selectedManufacturers,
  onCategoriesChange, onTagsChange, onManufacturersChange,
}: FilterSidebarProps) {
  const { t } = useTranslation()

  return (
    <aside className="filter-sidebar">
      <div className="filter-sidebar-header">
        <h3>{t('filters.title')}</h3>
      </div>

      {categories.length > 0 && (
        <FacetSection
          title={t('filters.categories')}
          values={categories}
          selected={selectedCategories}
          onChange={onCategoriesChange}
        />
      )}

      {manufacturers.length > 0 && (
        <FacetSection
          title={t('filters.manufacturers')}
          values={manufacturers}
          selected={selectedManufacturers}
          onChange={onManufacturersChange}
          maxVisible={10}
        />
      )}

      {tags.length > 0 && (
        <FacetSection
          title={t('filters.tags')}
          values={tags}
          selected={selectedTags}
          onChange={onTagsChange}
          maxVisible={10}
        />
      )}
    </aside>
  )
}
