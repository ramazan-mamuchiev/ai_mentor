import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import en from './locales/en.json'
import ru from './locales/ru.json'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { ui: en },
      ru: { ui: ru },
    },
    fallbackLng: 'en',
    defaultNS: 'ui',
    ns: ['ui'],
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'lexiro-lang',
      caches: ['localStorage'],
    },
    saveMissing: false,
    missingKeyHandler: (_lngs: readonly string[], ns: string, key: string) => {
      if (import.meta.env.DEV) {
        console.warn(`[i18n] Missing key: ${ns}:${key}`)
      }
    },
    react: {
      useSuspense: true,
    },
  })

export default i18n
