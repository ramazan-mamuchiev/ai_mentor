import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Layout } from '../../components/Layout'

const defaultProps: {
  sessions: any[]
  activeSessionId: number | null
  theme: 'light' | 'dark'
  onSelectSession: ReturnType<typeof vi.fn>
  onNewSession: ReturnType<typeof vi.fn>
  onDeleteSession: ReturnType<typeof vi.fn>
  onToggleTheme: ReturnType<typeof vi.fn>
} = {
  sessions: [],
  activeSessionId: null,
  theme: 'light',
  onSelectSession: vi.fn(),
  onNewSession: vi.fn(),
  onDeleteSession: vi.fn(),
  onToggleTheme: vi.fn(),
}

function renderLayout(overrides: Partial<typeof defaultProps> = {}, children?: React.ReactNode) {
  return render(
    <Layout {...defaultProps} {...overrides}>
      {children ?? <div>Main content</div>}
    </Layout>,
  )
}

beforeEach(() => {
  localStorage.clear()
})

describe('Layout', () => {
  it('renders sidebar with IPCodex title', () => {
    renderLayout()
    expect(screen.getByText('IPCodex')).toBeInTheDocument()
  })

  it('renders children in main area', () => {
    renderLayout({ theme: 'dark' }, <div>Test content here</div>)
    expect(screen.getByText('Test content here')).toBeInTheDocument()
  })

  it('renders theme toggle in sidebar', () => {
    renderLayout()
    expect(screen.getByTitle('Toggle theme')).toBeInTheDocument()
  })
})

describe('Layout splitter', () => {
  it('renders a splitter element', () => {
    renderLayout()
    expect(document.querySelector('.splitter')).toBeInTheDocument()
  })

  it('uses default sidebar width of 280px', () => {
    renderLayout()
    const sidebar = document.querySelector('.sidebar') as HTMLElement
    expect(sidebar.style.width).toBe('280px')
  })

  it('restores sidebar width from localStorage', () => {
    localStorage.setItem('ipcodex-sidebar-width', '350')
    renderLayout()
    const sidebar = document.querySelector('.sidebar') as HTMLElement
    expect(sidebar.style.width).toBe('350px')
  })

  it('ignores invalid localStorage values and falls back to default', () => {
    localStorage.setItem('ipcodex-sidebar-width', 'garbage')
    renderLayout()
    const sidebar = document.querySelector('.sidebar') as HTMLElement
    expect(sidebar.style.width).toBe('280px')
  })

  it('clamps localStorage value within min/max bounds', () => {
    localStorage.setItem('ipcodex-sidebar-width', '50')
    renderLayout()
    const sidebar = document.querySelector('.sidebar') as HTMLElement
    expect(sidebar.style.width).toBe('280px')
  })

  it('resizes sidebar on pointer drag', () => {
    renderLayout()
    const splitter = document.querySelector('.splitter') as HTMLElement
    const sidebar = document.querySelector('.sidebar') as HTMLElement

    fireEvent.pointerDown(splitter, { clientX: 280, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientX: 380 })
    fireEvent.pointerUp(splitter)

    expect(sidebar.style.width).toBe('380px')
  })

  it('clamps resize to minimum width', () => {
    renderLayout()
    const splitter = document.querySelector('.splitter') as HTMLElement
    const sidebar = document.querySelector('.sidebar') as HTMLElement

    fireEvent.pointerDown(splitter, { clientX: 280, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientX: 50 })
    fireEvent.pointerUp(splitter)

    expect(sidebar.style.width).toBe('180px')
  })

  it('clamps resize to maximum width', () => {
    renderLayout()
    const splitter = document.querySelector('.splitter') as HTMLElement
    const sidebar = document.querySelector('.sidebar') as HTMLElement

    fireEvent.pointerDown(splitter, { clientX: 280, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientX: 1000 })
    fireEvent.pointerUp(splitter)

    expect(sidebar.style.width).toBe('600px')
  })

  it('persists width to localStorage after drag', () => {
    renderLayout()
    const splitter = document.querySelector('.splitter') as HTMLElement

    fireEvent.pointerDown(splitter, { clientX: 280, pointerId: 1 })
    fireEvent.pointerMove(splitter, { clientX: 400 })
    fireEvent.pointerUp(splitter)

    expect(localStorage.getItem('ipcodex-sidebar-width')).toBe('400')
  })

  it('does not resize when pointer moves without prior pointerDown', () => {
    renderLayout()
    const splitter = document.querySelector('.splitter') as HTMLElement
    const sidebar = document.querySelector('.sidebar') as HTMLElement

    fireEvent.pointerMove(splitter, { clientX: 500 })

    expect(sidebar.style.width).toBe('280px')
  })
})
