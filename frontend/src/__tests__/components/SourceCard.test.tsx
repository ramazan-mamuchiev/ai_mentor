import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SourceCard } from '../../components/SourceCard'
import type { SourceInfo } from '../../types'

const source: SourceInfo = {
  doc_title: 'HikCentral API Guide',
  heading_path: 'Authentication > HMAC',
  similarity: 0.923,
  content_preview: 'Use HMAC-SHA256 to sign your API requests with a secret key.',
  product_name: 'HikCentral',
  firmware_version: '2.6',
}

describe('SourceCard', () => {
  it('renders doc title and heading path', () => {
    render(<SourceCard source={source} />)
    expect(screen.getByText('HikCentral API Guide')).toBeInTheDocument()
    expect(screen.getByText('Authentication > HMAC')).toBeInTheDocument()
  })

  it('displays similarity as percentage', () => {
    render(<SourceCard source={source} />)
    expect(screen.getByText(/92\.3% match/)).toBeInTheDocument()
  })

  it('shows product name in score section', () => {
    render(<SourceCard source={source} />)
    const scoreEl = document.querySelector('.source-card-score')
    expect(scoreEl?.textContent).toContain('HikCentral')
  })

  it('omits product name when empty', () => {
    const noProduct = { ...source, product_name: '' }
    render(<SourceCard source={noProduct} />)
    const scoreEl = document.querySelector('.source-card-score')
    expect(scoreEl?.textContent).not.toContain('·')
  })

  it('does not show content_preview by default', () => {
    render(<SourceCard source={source} />)
    expect(screen.queryByText(/HMAC-SHA256 to sign/)).not.toBeInTheDocument()
  })

  it('expands to show content_preview on header click', async () => {
    render(<SourceCard source={source} />)
    const header = document.querySelector('.source-card-header')!
    await userEvent.click(header)
    expect(screen.getByText(/HMAC-SHA256 to sign/)).toBeInTheDocument()
    expect(document.querySelector('.source-card')!.classList.contains('expanded')).toBe(true)
  })

  it('collapses on second header click', async () => {
    render(<SourceCard source={source} />)
    const header = document.querySelector('.source-card-header')!
    await userEvent.click(header)
    expect(screen.getByText(/HMAC-SHA256 to sign/)).toBeInTheDocument()
    await userEvent.click(header)
    expect(screen.queryByText(/HMAC-SHA256 to sign/)).not.toBeInTheDocument()
    expect(document.querySelector('.source-card')!.classList.contains('expanded')).toBe(false)
  })

  it('allows text selection in preview', async () => {
    render(<SourceCard source={source} />)
    const header = document.querySelector('.source-card-header')!
    await userEvent.click(header)
    const preview = document.querySelector('.source-card-preview')!
    expect(getComputedStyle(preview).userSelect).not.toBe('none')
  })
})
