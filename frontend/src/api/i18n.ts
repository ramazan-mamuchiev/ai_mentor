import { apiFetch } from './client'

export interface LanguageInfo {
  id: number
  code: string
  name_native: string
  is_default: boolean
  is_system: boolean
}

export async function fetchLanguages(): Promise<LanguageInfo[]> {
  return apiFetch<LanguageInfo[]>('/i18n/languages')
}

export async function fetchTranslations(lang: string, ns: string = 'ui'): Promise<Record<string, string>> {
  return apiFetch<Record<string, string>>(`/i18n/translations/${lang}?ns=${ns}`)
}

export async function fetchTranslationVersion(lang: string): Promise<{ version: string }> {
  return apiFetch<{ version: string }>(`/i18n/version/${lang}`)
}
