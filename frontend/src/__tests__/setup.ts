import '@testing-library/jest-dom/vitest'
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from '../locales/en.json'
import ru from '../locales/ru.json'

i18n.use(initReactI18next).init({
  lng: 'en',
  resources: {
    en: { translation: en },
    ru: { translation: ru },
  },
  interpolation: { escapeValue: false },
})

Element.prototype.scrollIntoView = () => {}
