import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FileUpload } from '../../components/FileUpload'

vi.mock('tus-js-client', () => ({
  Upload: vi.fn().mockImplementation((_file, options) => ({
    start: vi.fn(() => {
      if (options.onProgress) options.onProgress(500, 1000)
    }),
    abort: vi.fn(),
    url: 'http://localhost/api/v1/uploads/test-id',
  })),
}))

describe('FileUpload', () => {
  const mockOnClose = vi.fn()
  const mockOnComplete = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the upload modal with dropzone', () => {
    render(<FileUpload onClose={mockOnClose} onComplete={mockOnComplete} />)
    expect(screen.getByText('Upload Documentation')).toBeInTheDocument()
    expect(screen.getByText(/Drag & drop/)).toBeInTheDocument()
  })

  it('closes when close button is clicked', async () => {
    render(<FileUpload onClose={mockOnClose} onComplete={mockOnComplete} />)
    const closeBtn = screen.getByTitle('Close')
    await userEvent.click(closeBtn)
    expect(mockOnClose).toHaveBeenCalledTimes(1)
  })

  it('shows form after file selection', async () => {
    render(<FileUpload onClose={mockOnClose} onComplete={mockOnComplete} />)

    const file = new File(['test content'], 'test.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    expect(input).toBeTruthy()

    await userEvent.upload(input, file)

    expect(screen.getByText('test.pdf')).toBeInTheDocument()
    expect(screen.getByText('Product name *')).toBeInTheDocument()
    expect(screen.getByText('Start Upload')).toBeInTheDocument()
  })

  it('disables start button when product name is empty', async () => {
    render(<FileUpload onClose={mockOnClose} onComplete={mockOnComplete} />)

    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(input, file)

    const startBtn = screen.getByText('Start Upload').closest('button')
    expect(startBtn).toBeDisabled()
  })

  it('enables start button when product name is filled', async () => {
    render(<FileUpload onClose={mockOnClose} onComplete={mockOnComplete} />)

    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.upload(input, file)

    const productInput = screen.getByPlaceholderText(/HikCentral Professional/)
    await userEvent.type(productInput, 'TestProduct')

    const startBtn = screen.getByText('Start Upload').closest('button')
    expect(startBtn).not.toBeDisabled()
  })

  it('shows supported file formats hint', () => {
    render(<FileUpload onClose={mockOnClose} onComplete={mockOnComplete} />)
    expect(screen.getByText(/Supports:/)).toBeInTheDocument()
    expect(screen.getByText(/PDF, Markdown/)).toBeInTheDocument()
  })
})
