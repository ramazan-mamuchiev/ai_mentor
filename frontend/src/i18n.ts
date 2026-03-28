import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import HttpBackend from 'i18next-http-backend'
import en from './locales/en.json'
import ru from './locales/ru.json'

i18n
  .use(HttpBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { ui: en },
      ru: { ui: ru },
    },
    partialBundledLanguages: true,
    fallbackLng: 'en',
    defaultNS: 'ui',
    ns: ['ui', 'taxonomy'],
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'lexiro-lang',
      caches: ['localStorage'],
    },
    backend: {
      loadPath: '/api/v1/i18n/translations/{{lng}}?ns={{ns}}',
      parse: (data: string) => {
        try {
          return JSON.parse(data)
        } catch {
          return {}
        }
      },
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
