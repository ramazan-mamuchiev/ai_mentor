import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DeviceFilter } from '../../components/DeviceFilter'

describe('DeviceFilter', () => {
  it('renders All products option and product list', () => {
    render(<DeviceFilter product="" onChange={() => {}} products={['CamA', 'CamB']} />)
    expect(screen.getByText('All products')).toBeInTheDocument()
    expect(screen.getByText('CamA')).toBeInTheDocument()
    expect(screen.getByText('CamB')).toBeInTheDocument()
  })

  it('calls onChange when selection changes', async () => {
    const onChange = vi.fn()
    render(<DeviceFilter product="" onChange={onChange} products={['CamA', 'CamB']} />)

    await userEvent.selectOptions(screen.getByRole('combobox'), 'CamA')
    expect(onChange).toHaveBeenCalledWith('CamA')
  })

  it('shows selected product', () => {
    render(<DeviceFilter product="CamB" onChange={() => {}} products={['CamA', 'CamB']} />)
    expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('CamB')
  })
})
