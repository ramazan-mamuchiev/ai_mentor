import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'

const INTERVAL_MS = 8000
const FADE_MS = 400

export function useRotatingSlogan() {
  const { t } = useTranslation()
  const count = parseInt(t('slogans.count'), 10) || 1
  const [index, setIndex] = useState(() => Math.floor(Math.random() * count))
  const [visible, setVisible] = useState(true)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const rotate = useCallback(() => {
    setVisible(false)
    setTimeout(() => {
      setIndex(prev => (prev + 1) % count)
      setVisible(true)
    }, FADE_MS)
  }, [count])

  useEffect(() => {
    if (count <= 1) return
    timerRef.current = setInterval(rotate, INTERVAL_MS)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [rotate, count])

  return {
    line1: t(`slogans.${index}.line1`),
    line2: t(`slogans.${index}.line2`),
    accent: t(`slogans.${index}.accent`),
    visible,
  }
}
