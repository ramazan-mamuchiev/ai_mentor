import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync, readdirSync } from 'fs'
import { resolve } from 'path'
import i18n from 'i18next'
import en from '../../locales/en.json'
import ru from '../../locales/ru.json'

vi.mock('../../auth/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: '1',
      email: 'test@example.com',
      name: 'Test',
      slug: 'test',
      tier: 'free',
      role: 'user',
      roles: [],
      permissions: { features: {} },
      email_verified: true,
      created_at: '2020-01-01T00:00:00Z',
    },
    logout: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    refreshUser: vi.fn(),
    loading: false,
  }),
}))

const LOCALE_DIR = resolve(__dirname, '../../locales')
const LOCALE_FILES = readdirSync(LOCALE_DIR).filter(f => f.endsWith('.json')).sort()
const ALL_LOCALES: Record<string, Record<string, string>> = {}
for (const file of LOCALE_FILES) {
  ALL_LOCALES[file] = JSON.parse(readFileSync(resolve(LOCALE_DIR, file), 'utf-8'))
}
const REFERENCE_FILE = 'en.json'
const REFERENCE_KEYS = Object.keys(ALL_LOCALES[REFERENCE_FILE]).sort()
import { LanguageToggle } from '../../components/LanguageToggle'
import { ChatWindow } from '../../components/ChatWindow'
import { ChatInput } from '../../components/ChatInput'
import { Layout } from '../../components/Layout'
import { SessionList } from '../../components/SessionList'
import { FileUpload } from '../../components/FileUpload'
import { DeviceFilter } from '../../components/DeviceFilter'
import { ThemeToggle } from '../../components/ThemeToggle'
import type { ChatSession } from '../../types'

vi.mock('tus-js-client', () => ({
  Upload: vi.fn().mockImplementation(() => ({
    start: vi.fn(),
    abort: vi.fn(),
    url: '',
  })),
}))

beforeEach(async () => {
  localStorage.clear()
  await act(() => i18n.changeLanguage('en'))
})

// ─── Translation file structure & format ───

describe('Translation file structure', () => {
  it('locales folder contains at least the reference file', () => {
    expect(LOCALE_FILES).toContain(REFERENCE_FILE)
  })

  for (const file of LOCALE_FILES) {
    describe(file, () => {
      const raw = readFileSync(resolve(LOCALE_DIR, file), 'utf-8')

      it('is valid JSON', () => {
        expect(() => JSON.parse(raw)).not.toThrow()
      })

      it('is a flat object (no nested keys)', () => {
        const parsed = JSON.parse(raw)
        for (const [key, value] of Object.entries(parsed)) {
          expect(typeof value, `key "${key}" should be a string, got ${typeof value}`).toBe('string')
        }
      })

      it('has no duplicate keys', () => {
        const keys: string[] = []
        const dupes: string[] = []
        const keyRe = /"([^"]+)"\s*:/g
        let match: RegExpExecArray | null
        while ((match = keyRe.exec(raw)) !== null) {
          if (keys.includes(match[1])) dupes.push(match[1])
          keys.push(match[1])
        }
        expect(dupes, `Duplicate keys found: ${dupes.join(', ')}`).toEqual([])
      })

      it('uses consistent key naming (dot-separated segments)', () => {
        const parsed = JSON.parse(raw)
        const segment = '[a-zA-Z0-9_]+'
        const keyRe = new RegExp(`^${segment}(\\.${segment})*$`)
        const badKeys = Object.keys(parsed).filter(k => !keyRe.test(k))
        expect(badKeys, `Keys with invalid format: ${badKeys.join(', ')}`).toEqual([])
      })

      it('has no trailing commas (strict JSON)', () => {
        expect(raw).not.toMatch(/,\s*[}\]]/)
      })

      it('uses UTF-8 without BOM', () => {
        expect(raw.charCodeAt(0), 'File starts with BOM').not.toBe(0xFEFF)
      })

      it('ends with a newline', () => {
        expect(raw.endsWith('\n'), 'File should end with newline').toBe(true)
      })

      it('has no leading/trailing whitespace in values', () => {
        const parsed = JSON.parse(raw)
        for (const [key, value] of Object.entries(parsed)) {
          if (key.endsWith('filteredByTenant') || key === 'admin.prompts.edited' || key.startsWith('admin.promptEditor.')) continue
          const str = value as string
          expect(str, `key "${key}" has leading/trailing whitespace`).toBe(str.trim())
        }
      })

      it('has no HTML tags in values (plain text + interpolation only)', () => {
        const parsed = JSON.parse(raw)
        const htmlAllowedKeys = new Set(['landing.elevator.text'])
        const htmlRe = /<\/?[a-z][\s\S]*?>/i
        for (const [key, value] of Object.entries(parsed)) {
          if (htmlAllowedKeys.has(key)) continue
          expect(htmlRe.test(value as string), `key "${key}" contains HTML: ${value}`).toBe(false)
        }
      })
    })
  }
})

// ─── Translation files completeness (all locales vs reference) ───

describe('Translation files completeness', () => {
  const placeholderRe = /\{\{(\w+)\}\}/g

  for (const file of LOCALE_FILES) {
    const locale = ALL_LOCALES[file]
    const localeKeys = Object.keys(locale).sort()

    describe(`${file} vs ${REFERENCE_FILE}`, () => {
      it('has the same set of keys as reference', () => {
        const missing = REFERENCE_KEYS.filter(k => !localeKeys.includes(k))
        expect(missing, `Missing keys in ${file}: ${missing.join(', ')}`).toEqual([])
      })

      it('has no empty values', () => {
        for (const [key, value] of Object.entries(locale)) {
          expect(value, `${file} key "${key}" is empty`).not.toBe('')
        }
      })

      it('interpolation placeholders match reference', () => {
        const ref = ALL_LOCALES[REFERENCE_FILE]
        for (const key of REFERENCE_KEYS) {
          if (!locale[key] || !ref[key]) continue
          const refPlaceholders = [...ref[key].matchAll(placeholderRe)].map(m => m[1]).sort()
          const localePlaceholders = [...locale[key].matchAll(placeholderRe)].map(m => m[1]).sort()
          expect(localePlaceholders, `Placeholders mismatch for key "${key}" in ${file}`).toEqual(refPlaceholders)
        }
      })
    })
  }
})

// ─── LanguageToggle component ───

describe('LanguageToggle', () => {
  it('renders with current language label', () => {
    render(<LanguageToggle />)
    expect(screen.getByText('EN')).toBeInTheDocument()
  })

  it('renders current language code', () => {
    render(<LanguageToggle />)
    expect(screen.getByRole('button', { name: 'EN' })).toBeInTheDocument()
  })

  it('switches to RU on click', async () => {
    render(<LanguageToggle />)
    await userEvent.click(screen.getByText('EN'))
    expect(screen.getByText('RU')).toBeInTheDocument()
    expect(i18n.language).toBe('ru')
  })

  it('switches back to EN on second click', async () => {
    render(<LanguageToggle />)
    await userEvent.click(screen.getByText('EN'))
    expect(screen.getByText('RU')).toBeInTheDocument()
    await userEvent.click(screen.getByText('RU'))
    expect(screen.getByText('EN')).toBeInTheDocument()
    expect(i18n.language).toBe('en')
  })

  it('calls changeLanguage which updates i18n.language', async () => {
    render(<LanguageToggle />)
    await userEvent.click(screen.getByText('EN'))
    expect(i18n.language).toBe('ru')
  })

  it('shows RU label after switching to Russian', async () => {
    render(<LanguageToggle />)
    await userEvent.click(screen.getByText('EN'))
    expect(screen.getByRole('button', { name: 'RU' })).toBeInTheDocument()
  })
})

// ─── Language switching in ChatWindow ───

describe('ChatWindow language switching', () => {
  function renderEmpty() {
    return render(
      <ChatWindow
        messages={[]}
        streamingContent=""
        streamingSources={[]}
        status="idle"
        onSend={() => {}}
        onCancel={() => {}}
      />,
    )
  }

  it('shows English empty state by default', () => {
    renderEmpty()
    expect(screen.getByText('AI Integration Platform')).toBeInTheDocument()
    expect(screen.getByText('AI Mentor')).toBeInTheDocument()
    const slogan = document.querySelector('.empty-slogan')
    const count = parseInt(ALL_LOCALES[REFERENCE_FILE]['slogans.count'], 10) || 10
    const enLine1s = Array.from({ length: count }, (_, i) => ALL_LOCALES[REFERENCE_FILE][`slogans.${i}.line1`])
    expect(enLine1s).toContain(slogan?.textContent ?? '')
  })

  it('switches empty state to Russian', async () => {
    renderEmpty()
    await act(() => i18n.changeLanguage('ru'))
    expect(screen.getByText('AI-платформа интеграции')).toBeInTheDocument()
    expect(screen.getByText('AI Mentor')).toBeInTheDocument()
    const slogan = document.querySelector('.empty-slogan')
    const ru = ALL_LOCALES['ru.json']
    const count = parseInt(ru['slogans.count'], 10) || 10
    const ruLine1s = Array.from({ length: count }, (_, i) => ru[`slogans.${i}.line1`])
    expect(ruLine1s).toContain(slogan?.textContent ?? '')
  })

  it('switches placeholder to Russian', async () => {
    renderEmpty()
    expect(screen.getByPlaceholderText(/Ask anything about your docs/)).toBeInTheDocument()
    await act(() => i18n.changeLanguage('ru'))
    expect(screen.getByPlaceholderText(/Задайте вопрос по документации/)).toBeInTheDocument()
  })
})

// ─── Language switching in ChatInput ───

describe('ChatInput language switching', () => {
  it('shows English placeholder by default', () => {
    render(<ChatInput onSend={() => {}} onCancel={() => {}} status="idle" />)
    expect(screen.getByPlaceholderText('Ask anything about your docs...')).toBeInTheDocument()
  })

  it('switches placeholder to Russian', async () => {
    render(<ChatInput onSend={() => {}} onCancel={() => {}} status="idle" />)
    await act(() => i18n.changeLanguage('ru'))
    expect(screen.getByPlaceholderText('Задайте вопрос по документации...')).toBeInTheDocument()
  })

  it('switches attach toast to Russian', async () => {
    const user = userEvent.setup()
    const { container } = render(<ChatInput onSend={() => {}} onCancel={() => {}} status="idle" />)
    const attachBtn = container.querySelector('.chat-attach-btn') as HTMLElement
    await user.click(attachBtn)
    expect(screen.getByText(/Attach files to chat/)).toBeInTheDocument()
    await act(() => i18n.changeLanguage('ru'))
    await user.click(attachBtn)
    expect(screen.getByText(/Прикрепление файлов к чату/)).toBeInTheDocument()
  })

  it('shows streaming stop control in both languages', async () => {
    const { container } = render(<ChatInput onSend={() => {}} onCancel={() => {}} status="streaming" />)
    expect(container.querySelector('.chat-send-btn.active')).toBeInTheDocument()
    await act(() => i18n.changeLanguage('ru'))
    expect(container.querySelector('.chat-send-btn.active')).toBeInTheDocument()
  })
})

// ─── Language switching in Layout ───

describe('Layout language switching', () => {
  const layoutProps = {
    sessions: [] as ChatSession[],
    activeSessionId: null as string | null,
    theme: 'light' as const,
    onSelectSession: vi.fn(),
    onNewSession: vi.fn(),
    onDeleteSession: vi.fn(),
    onToggleTheme: vi.fn(),
  }

  function renderLayout() {
    return render(
      <MemoryRouter initialEntries={['/app']}>
        <Layout {...layoutProps}><div /></Layout>
      </MemoryRouter>,
    )
  }

  it('shows language switch in account menu', async () => {
    const user = userEvent.setup()
    const { container } = renderLayout()
    await user.click(container.querySelector('.account-badge-btn') as HTMLElement)
    expect(screen.getByRole('button', { name: 'Русский' })).toBeInTheDocument()
  })

  it('switches sidebar new-chat label to Russian', async () => {
    renderLayout()
    expect(screen.getByRole('button', { name: 'New chat' })).toBeInTheDocument()
    await act(() => i18n.changeLanguage('ru'))
    expect(screen.getByRole('button', { name: 'Новый чат' })).toBeInTheDocument()
  })

  it('switches theme labels in account menu to Russian', async () => {
    const user = userEvent.setup()
    const { container } = renderLayout()
    await user.click(container.querySelector('.account-badge-btn') as HTMLElement)
    expect(screen.getByRole('button', { name: 'Dark theme' })).toBeInTheDocument()
    await act(() => i18n.changeLanguage('ru'))
    expect(screen.getByRole('button', { name: 'Тёмная тема' })).toBeInTheDocument()
  })
})

// ─── Language switching in SessionList ───

describe('SessionList language switching', () => {
  const sessions: ChatSession[] = [
    { id: '1', title: null, product_filter: null, version_filter: null, created_at: '', updated_at: '', message_count: 0, last_message_preview: null },
  ]

  it('shows "New Chat" fallback in English', () => {
    render(<SessionList sessions={sessions} activeSessionId={null} onSelect={() => {}} onNew={() => {}} onDelete={() => {}} />)
    expect(screen.getByText('New Chat')).toBeInTheDocument()
  })

  it('switches fallback to Russian', async () => {
    render(<SessionList sessions={sessions} activeSessionId={null} onSelect={() => {}} onNew={() => {}} onDelete={() => {}} />)
    await act(() => i18n.changeLanguage('ru'))
    expect(screen.getByRole('button', { name: 'Новый чат' })).toBeInTheDocument()
  })

  it('switches context menu items to Russian', async () => {
    render(<SessionList sessions={sessions} activeSessionId={null} onSelect={() => {}} onNew={() => {}} onDelete={() => {}} />)
    const menuBtn = document.querySelector('.session-menu-btn') as HTMLElement
    await userEvent.click(menuBtn)
    expect(screen.getByText('Rename')).toBeInTheDocument()
    expect(screen.getByText('Delete')).toBeInTheDocument()

    await act(() => i18n.changeLanguage('ru'))
    expect(screen.getByText('Переименовать')).toBeInTheDocument()
    expect(screen.getByText('Удалить')).toBeInTheDocument()
  })
})

// ─── Language switching in FileUpload ───

describe('FileUpload language switching', () => {
  it('shows English title by default', () => {
    render(<FileUpload onClose={() => {}} onComplete={() => {}} />)
    expect(screen.getByText('Upload Documentation')).toBeInTheDocument()
  })

  it('switches title to Russian', async () => {
    render(<FileUpload onClose={() => {}} onComplete={() => {}} />)
    await act(() => i18n.changeLanguage('ru'))
    expect(screen.getByText('Загрузка документации')).toBeInTheDocument()
  })

  it('switches dropzone text to Russian', async () => {
    render(<FileUpload onClose={() => {}} onComplete={() => {}} />)
    expect(screen.getByText(/Drag & drop/)).toBeInTheDocument()
    await act(() => i18n.changeLanguage('ru'))
    expect(screen.getByText(/Перетащите файл/)).toBeInTheDocument()
  })
})

// ─── Language switching in DeviceFilter ───

describe('DeviceFilter language switching', () => {
  it('shows "All products" in English', () => {
    render(<DeviceFilter product="" onChange={() => {}} products={['Cam1']} />)
    expect(screen.getByText('All products')).toBeInTheDocument()
  })

  it('switches to Russian', async () => {
    render(<DeviceFilter product="" onChange={() => {}} products={['Cam1']} />)
    await act(() => i18n.changeLanguage('ru'))
    expect(screen.getByText('Все продукты')).toBeInTheDocument()
  })
})

// ─── Language switching in ThemeToggle ───

describe('ThemeToggle language switching', () => {
  it('still renders after language change (icon-only control)', async () => {
    const { container } = render(<ThemeToggle theme="light" onToggle={() => {}} />)
    expect(container.querySelector('.theme-toggle')).toBeInTheDocument()
    await act(() => i18n.changeLanguage('ru'))
    expect(container.querySelector('.theme-toggle')).toBeInTheDocument()
  })
})

// ─── Interpolation ───

describe('i18n interpolation', () => {
  it('interpolates {{count}} in chat.sources', () => {
    expect(i18n.t('chat.sources', { count: 5 })).toBe('Sources (5)')
  })

  it('interpolates {{count}} in Russian', async () => {
    await act(() => i18n.changeLanguage('ru'))
    expect(i18n.t('chat.sources', { count: 3 })).toBe('Источники (3)')
  })

  it('interpolates {{filename}} in upload.queued', () => {
    expect(i18n.t('upload.queued', { filename: 'test.pdf' }))
      .toBe('test.pdf has been uploaded and queued for processing.')
  })

  it('interpolates {{filename}} in Russian', async () => {
    await act(() => i18n.changeLanguage('ru'))
    expect(i18n.t('upload.queued', { filename: 'doc.pdf' }))
      .toBe('doc.pdf загружен и поставлен в очередь на обработку.')
  })

  it('interpolates {{value}} in match', () => {
    expect(i18n.t('match', { value: '95.3' })).toBe('95.3% match')
  })

  it('interpolates {{message}} in chat.error', () => {
    expect(i18n.t('chat.error', { message: 'timeout' })).toBe('Error: timeout')
  })

  it('interpolates {{message}} in Russian chat.error', async () => {
    await act(() => i18n.changeLanguage('ru'))
    expect(i18n.t('chat.error', { message: 'timeout' })).toBe('Ошибка: timeout')
  })
})

// ─── localStorage persistence (with LanguageDetector) ───

describe('i18n localStorage persistence', () => {
  let detectorI18n: typeof i18n

  beforeEach(async () => {
    const { default: i18nCore } = await import('i18next')
    const { initReactI18next } = await import('react-i18next')
    const { default: LanguageDetector } = await import('i18next-browser-languagedetector')

    detectorI18n = i18nCore.createInstance()
    await detectorI18n
      .use(LanguageDetector)
      .use(initReactI18next)
      .init({
        defaultNS: 'ui',
        partialBundledLanguages: true,
        resources: {
          en: { ui: en },
          ru: { ui: ru },
        },
        fallbackLng: 'en',
        interpolation: { escapeValue: false },
        detection: {
          order: ['localStorage', 'navigator'],
          lookupLocalStorage: 'ai-mentor-lang',
          caches: ['localStorage'],
        },
      })
  })

  it('saves language to localStorage on change', async () => {
    await act(() => detectorI18n.changeLanguage('ru'))
    expect(localStorage.getItem('ai-mentor-lang')).toBe('ru')
  })

  it('saves back to en', async () => {
    await act(() => detectorI18n.changeLanguage('ru'))
    await act(() => detectorI18n.changeLanguage('en'))
    expect(localStorage.getItem('ai-mentor-lang')).toBe('en')
  })

  it('restores language from localStorage on init', async () => {
    localStorage.setItem('ai-mentor-lang', 'ru')

    const { default: i18nCore2 } = await import('i18next')
    const { initReactI18next: iri } = await import('react-i18next')
    const { default: LD } = await import('i18next-browser-languagedetector')

    const fresh = i18nCore2.createInstance()
    await fresh
      .use(LD)
      .use(iri)
      .init({
        defaultNS: 'ui',
        partialBundledLanguages: true,
        resources: {
          en: { ui: en },
          ru: { ui: ru },
        },
        fallbackLng: 'en',
        interpolation: { escapeValue: false },
        detection: {
          order: ['localStorage', 'navigator'],
          lookupLocalStorage: 'ai-mentor-lang',
          caches: ['localStorage'],
        },
      })

    expect(fresh.language).toBe('ru')
  })
})
