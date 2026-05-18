import { useCallback, useEffect, useState } from 'react'

type Theme = 'light' | 'dark'

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem('ai-mentor-theme')
    if (stored === 'light' || stored === 'dark') return stored
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('ai-mentor-theme', theme)
    const favicon = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
    if (favicon) favicon.href = theme === 'dark' ? '/logo-on-dark.svg' : '/logo-on-light.svg'
  }, [theme])

  const toggle = useCallback(() => {
    setTheme(prev => (prev === 'dark' ? 'light' : 'dark'))
  }, [])

  return { theme, toggle }
}
