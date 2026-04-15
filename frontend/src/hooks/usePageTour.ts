import { useEffect } from 'react'
import type { DriveStep } from 'driver.js'
import { useHelpTour } from '../tour/HelpTourContext'

export function usePageTour(pageKey: string, steps: DriveStep[]) {
  const { registerTour, unregisterTour } = useHelpTour()

  useEffect(() => {
    if (!steps.length) return
    registerTour(pageKey, steps)
    return () => unregisterTour(pageKey)
  }, [pageKey, steps, registerTour, unregisterTour])
}
