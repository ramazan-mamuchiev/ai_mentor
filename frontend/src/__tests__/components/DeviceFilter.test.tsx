import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DeviceFilter } from '../../components/DeviceFilter'

describe('DeviceFilter', () => {
  it('renders All devices option and device list', () => {
    render(<DeviceFilter device="" onChange={() => {}} devices={['CamA', 'CamB']} />)
    expect(screen.getByText('All devices')).toBeInTheDocument()
    expect(screen.getByText('CamA')).toBeInTheDocument()
    expect(screen.getByText('CamB')).toBeInTheDocument()
  })

  it('calls onChange when selection changes', async () => {
    const onChange = vi.fn()
    render(<DeviceFilter device="" onChange={onChange} devices={['CamA', 'CamB']} />)

    await userEvent.selectOptions(screen.getByRole('combobox'), 'CamA')
    expect(onChange).toHaveBeenCalledWith('CamA')
  })

  it('shows selected device', () => {
    render(<DeviceFilter device="CamB" onChange={() => {}} devices={['CamA', 'CamB']} />)
    expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('CamB')
  })
})
