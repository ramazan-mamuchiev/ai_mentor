import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTheme } from '../../hooks/useTheme'

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('useTheme', () => {
  it('initializes from localStorage', () => {
    localStorage.setItem('ai-mentor-theme', 'dark')
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
  })

  it('falls back to prefers-color-scheme when no stored value', () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true })

    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
  })

  it('defaults to light when prefers-color-scheme is light', () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: false })

    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')
  })

  it('toggle switches dark to light', () => {
    localStorage.setItem('ai-mentor-theme', 'dark')
    const { result } = renderHook(() => useTheme())

    act(() => result.current.toggle())
    expect(result.current.theme).toBe('light')
  })

  it('toggle switches light to dark', () => {
    localStorage.setItem('ai-mentor-theme', 'light')
    const { result } = renderHook(() => useTheme())

    act(() => result.current.toggle())
    expect(result.current.theme).toBe('dark')
  })

  it('syncs theme to document and localStorage', () => {
    localStorage.setItem('ai-mentor-theme', 'light')
    renderHook(() => useTheme())

    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem('ai-mentor-theme')).toBe('light')
  })
})
