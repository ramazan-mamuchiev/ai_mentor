import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeToggle } from '../../components/ThemeToggle'

describe('ThemeToggle', () => {
  it('renders Sun icon when theme is dark', () => {
    render(<ThemeToggle theme="dark" onToggle={() => {}} />)
    expect(screen.getByTitle('Toggle theme')).toBeInTheDocument()
  })

  it('renders Moon icon when theme is light', () => {
    render(<ThemeToggle theme="light" onToggle={() => {}} />)
    expect(screen.getByTitle('Toggle theme')).toBeInTheDocument()
  })

  it('calls onToggle when clicked', async () => {
    const onToggle = vi.fn()
    render(<ThemeToggle theme="light" onToggle={onToggle} />)

    await userEvent.click(screen.getByTitle('Toggle theme'))
    expect(onToggle).toHaveBeenCalledOnce()
  })
})
