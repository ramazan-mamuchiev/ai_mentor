import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'
import { driver, type DriveStep, type Driver } from 'driver.js'
import { useTranslation } from 'react-i18next'

interface HelpTourContextValue {
  registerTour: (pageKey: string, steps: DriveStep[]) => void
  unregisterTour: (pageKey: string) => void
  startTour: () => void
  hasTour: boolean
}

const HelpTourContext = createContext<HelpTourContextValue>({
  registerTour: () => {},
  unregisterTour: () => {},
  startTour: () => {},
  hasTour: false,
})

export function useHelpTour() {
  return useContext(HelpTourContext)
}

const HELP_SEEN_PREFIX = 'lexiro-help-seen-'

export function resetAllHelpTours() {
  const keys = Object.keys(localStorage).filter(k => k.startsWith(HELP_SEEN_PREFIX))
  keys.forEach(k => localStorage.removeItem(k))
}

export function HelpTourProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const toursRef = useRef<Map<string, DriveStep[]>>(new Map())
  const activePageRef = useRef<string | null>(null)
  const driverRef = useRef<Driver | null>(null)
  const [hasTour, setHasTour] = useState(false)

  const createDriver = useCallback((steps: DriveStep[]) => {
    return driver({
      steps,
      showProgress: true,
      animate: true,
      overlayColor: 'rgba(0, 0, 0, 0.6)',
      stagePadding: 8,
      stageRadius: 10,
      popoverClass: 'lexiro-tour-popover',
      nextBtnText: t('help.next'),
      prevBtnText: t('help.prev'),
      doneBtnText: t('help.done'),
      progressText: '{{current}} / {{total}}',
      onDestroyStarted: () => {
        if (driverRef.current) {
          driverRef.current.destroy()
          driverRef.current = null
        }
        if (activePageRef.current) {
          markSeen(activePageRef.current)
        }
      },
    })
  }, [t])

  const markSeen = (pageKey: string) => {
    try {
      localStorage.setItem(HELP_SEEN_PREFIX + pageKey, '1')
    } catch { /* ignore */ }
  }

  const isSeen = (pageKey: string): boolean => {
    try {
      return localStorage.getItem(HELP_SEEN_PREFIX + pageKey) === '1'
    } catch {
      return false
    }
  }

  const registerTour = useCallback((pageKey: string, steps: DriveStep[]) => {
    toursRef.current.set(pageKey, steps)
    activePageRef.current = pageKey
    setHasTour(true)

    if (!isSeen(pageKey)) {
      setTimeout(() => {
        if (activePageRef.current === pageKey && toursRef.current.has(pageKey)) {
          const d = createDriver(steps)
          driverRef.current = d
          d.drive()
        }
      }, 600)
    }
  }, [createDriver])

  const unregisterTour = useCallback((pageKey: string) => {
    toursRef.current.delete(pageKey)
    if (activePageRef.current === pageKey) {
      activePageRef.current = null
      setHasTour(false)
      if (driverRef.current) {
        driverRef.current.destroy()
        driverRef.current = null
      }
    }
  }, [])

  const startTour = useCallback(() => {
    if (!activePageRef.current) return
    const steps = toursRef.current.get(activePageRef.current)
    if (!steps?.length) return

    if (driverRef.current) {
      driverRef.current.destroy()
      driverRef.current = null
    }

    const d = createDriver(steps)
    driverRef.current = d
    d.drive()
  }, [createDriver])

  return (
    <HelpTourContext.Provider value={{ registerTour, unregisterTour, startTour, hasTour }}>
      {children}
    </HelpTourContext.Provider>
  )
}
