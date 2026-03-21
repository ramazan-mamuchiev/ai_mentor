# IPCodex — Design System & UI/UX Guidelines

> **Status**: v1.0 — March 21, 2026
> **Author**: Oleg Voitekhovich
> **Purpose**: Единый источник правды по дизайн-системе для всех UI-компонентов IPCodex.
> При реализации новых страниц и компонентов — использовать ТОЛЬКО этот документ.
>
> Related: [PLAN.md](PLAN.md) · [BRAND_SLOGANS.md](BRAND_SLOGANS.md) · [GTM_STRATEGY.md](GTM_STRATEGY.md)

---

## 1. Логотип

### Файлы

| Файл | Назначение | Градиент |
|------|-----------|----------|
| `frontend/public/logo-on-light.svg` | Для светлой темы | `#286CEA` → `#DF2F7F` (blue → pink) |
| `frontend/public/logo-on-dark.svg` | Для тёмной темы | `#77B8FD` → `#FEA5D0` (light blue → light pink) |

### Описание

Гексагон (шестиугольник) с символом `</>` внутри. Линейный градиент слева направо. SVG, 237×263 viewBox.

### Использование

- **Favicon**: `frontend/index.html` — `<link rel="icon" type="image/svg+xml" href="/logo-on-light.svg" />`
- **Sidebar**: `frontend/src/components/Layout.tsx` — 22×22px, переключение по теме:
  ```html
  <img src="/logo-on-light.svg" class="sidebar-icon logo-light" />
  <img src="/logo-on-dark.svg" class="sidebar-icon logo-dark" />
  ```
- **Empty state (чат)**: `frontend/src/components/ChatWindow.tsx` — 72×72px, с `drop-shadow`
- **Landing hero**: `frontend/src/pages/LandingPage.tsx` — 80px, с `drop-shadow` glow, переключение по теме (✅ реализовано)
- **Promo**: `promo/comparison.html`, `promo/ipcodex.html` — inline SVG, 72×80px / 88px

### Правила

- Светлая тема: показывать `logo-on-light.svg`, скрывать `logo-on-dark.svg`
- Тёмная тема: показывать `logo-on-dark.svg`, скрывать `logo-on-light.svg`
- CSS-классы: `.logo-light` / `.logo-dark` + `[data-theme='dark'] .logo-light { display: none; }`
- Минимальный размер: 22px (sidebar), рекомендуемый: 72px (hero/empty state)

---

## 2. Цветовая палитра

### CSS-переменные (определены в `frontend/src/styles/globals.css`)

#### Светлая тема (`:root`)

| Переменная | Значение | Назначение |
|-----------|---------|-----------|
| `--accent` | `#2563eb` | Основной акцент (кнопки, ссылки, active state) |
| `--accent2` | `#7c3aed` | Вторичный акцент (фиолетовый) |
| `--accent3` | `#db2777` | Третичный акцент (розовый) |
| `--gradient` | `linear-gradient(135deg, #2563eb, #7c3aed, #db2777)` | Градиент бренда |
| `--bg` | `#ffffff` | Основной фон |
| `--bg-secondary` | `#f8fafc` | Вторичный фон (sidebar, карточки) |
| `--bg-tertiary` | `#f1f5f9` | Третичный фон (сообщения assistant) |
| `--surface` | `#ffffff` | Поверхность (карточки, модалки) |
| `--surface-hover` | `#f8fafc` | Hover-состояние поверхностей |
| `--border` | `#e2e8f0` | Границы, разделители |
| `--text` | `#0f172a` | Основной текст |
| `--text-secondary` | `#475569` | Вторичный текст |
| `--text-muted` | `#94a3b8` | Приглушённый текст (подсказки, метаданные) |

#### Тёмная тема (`[data-theme='dark']`)

| Переменная | Значение | Назначение |
|-----------|---------|-----------|
| `--accent` | `#60a5fa` | Акцент (светлее для контраста) |
| `--gradient` | `linear-gradient(135deg, #77B8FD, #FEA5D0)` | Градиент бренда (мягче) |
| `--bg` | `#0b0f19` | Основной фон |
| `--bg-secondary` | `#111827` | Вторичный фон |
| `--bg-tertiary` | `#1e293b` | Третичный фон |
| `--surface` | `#1e293b` | Поверхность |
| `--surface-hover` | `#334155` | Hover-состояние |
| `--border` | `#334155` | Границы |
| `--text` | `#f1f5f9` | Основной текст |
| `--text-secondary` | `#94a3b8` | Вторичный текст |
| `--text-muted` | `#64748b` | Приглушённый текст |

### Семантические цвета (не в переменных, используются напрямую)

| Назначение | Light | Dark |
|-----------|-------|------|
| Success (ready) | `#38a169` | `#38a169` |
| Error (failed) | `#e53e3e` / `#ef4444` | `#fc8181` / `#ff6b6b` |
| Warning (pending) | `#d69e2e` | `#ffc107` |
| Info (processing) | `var(--accent)` | `var(--accent)` |

---

## 3. Типографика

### Шрифты (определены в `frontend/src/styles/globals.css`)

| Переменная | Значение | Назначение |
|-----------|---------|-----------|
| `--font-sans` | `'Inter', system-ui, -apple-system, sans-serif` | Основной текст, UI |
| `--font-mono` | `'JetBrains Mono', 'Fira Code', monospace` | Код, debug-панели, технические данные |

### Размеры текста (из существующих компонентов)

| Элемент | Размер | Вес | Дополнительно |
|---------|--------|-----|--------------|
| Заголовок страницы (hero) | `3rem` | 800 | `letter-spacing: -1.5px`, gradient text |
| Заголовок секции | `1.15rem` | 600 | `letter-spacing: -0.3px` |
| Заголовок sidebar | `15px` | 600 | gradient text |
| Основной текст | `14px` | 400 | `line-height: 1.7` |
| Вторичный текст | `13px` | 400 | `color: var(--text-secondary)` |
| Мелкий текст (meta) | `11-12px` | 400-600 | `color: var(--text-muted)` |
| Код/debug | `11px` | 400 | `font-family: var(--font-mono)` |
| Бейджи/теги | `10-11px` | 600-700 | `text-transform: uppercase`, `letter-spacing: 0.5-1.2px` |

### Gradient text (бренд)

```css
background: var(--gradient);
-webkit-background-clip: text;
-webkit-text-fill-color: transparent;
background-clip: text;
```

Используется для: sidebar title, hero title, section titles (опционально).

---

## 4. Скругления и отступы

| Переменная | Значение | Назначение |
|-----------|---------|-----------|
| `--radius` | `8px` | Кнопки, карточки, инпуты |
| `--radius-lg` | `12px` | Модалки, большие карточки |
| Pill-shape | `12-20px` | Бейджи, теги |
| Круглые кнопки | `50%` | Send, attach, theme toggle |

### Отступы (паттерны)

- Sidebar padding: `10px 10px` (header), `6px 8px` (list)
- Модалки: `16px 20px` (header), `20px` (body)
- Карточки: `10px 14px`
- Инпуты: `8px 10px`
- Кнопки: `6px 12px` (small), `10px` (full-width)

---

## 5. Иконки

### Библиотека: lucide-react

Все иконки — из `lucide-react`. Размеры:

| Контекст | Размер | Примеры |
|----------|--------|---------|
| Inline (кнопки, actions) | `16px` | `X`, `Pause`, `Play`, `Download` |
| Стандартный | `18px` | `Upload`, `Plus`, `ArrowUp`, `SquarePen` |
| Акцентный | `20px` | `FileText`, `CheckCircle`, `AlertCircle` |
| Hero / empty state | `24-32px` | `Upload` (dropzone), `CheckCircle` (success) |

### Иконки для статусов документов

| Статус | Иконка | Цвет |
|--------|--------|------|
| `pending` | `Clock` | `#d69e2e` (warning) |
| `processing` | `Loader2` (animated spin) | `var(--accent)` |
| `ready` | `CheckCircle` | `#38a169` (success) |
| `error` | `AlertCircle` | `#e53e3e` (error) |

### Иконки для навигации

| Раздел | Иконка |
|--------|--------|
| Chat | `MessageSquare` |
| Documents | `FileText` |

### Иконки для действий

| Действие | Иконка |
|----------|--------|
| Upload | `Upload` |
| Download | `Download` |
| Delete | `Trash2` |
| Reindex | `RefreshCw` |
| Cancel | `X` |
| Pause | `Pause` |
| Resume | `Play` |
| Retry | `RotateCcw` |

---

## 6. Компоненты

### 6.1 Кнопки

**Primary (accent):**
```css
background: var(--accent);
color: white;
border: none;
border-radius: 8px;
font-size: 14px;
font-weight: 500;
padding: 10px;
transition: opacity 0.2s;
```
Hover: `opacity: 0.9`. Disabled: `opacity: 0.5; cursor: not-allowed`.

**Ghost (secondary):**
```css
display: flex;
align-items: center;
gap: 4px;
padding: 6px 12px;
border: 1px solid var(--border);
border-radius: 6px;
background: var(--bg-secondary);
color: var(--text);
font-size: 13px;
transition: background 0.15s;
```
Hover: `background: var(--surface-hover)`.

**Danger:**
```css
border-color: #e53e3e;
color: #e53e3e;
```
Hover: `background: #e53e3e; color: white`.

**Icon button (круглая):**
```css
width: 36px;
height: 36px;
border-radius: 50%;
display: flex;
align-items: center;
justify-content: center;
```

### 6.2 Инпуты

```css
padding: 8px 10px;
border: 1px solid var(--border);
border-radius: 6px;
background: var(--bg);
color: var(--text);
font-size: 14px;
font-family: var(--font-sans);
outline: none;
```
Focus: `border-color: var(--accent)`.

### 6.3 Статус-бейджи

Pill-shape бейджи для статусов документов и reindex jobs:

```css
display: inline-flex;
align-items: center;
gap: 6px;
padding: 4px 12px;
border-radius: 12px;
font-size: 12px;
font-weight: 600;
```

| Статус | Фон | Текст |
|--------|-----|-------|
| `pending` | `rgba(217, 158, 46, 0.1)` | `#d69e2e` |
| `processing` | `rgba(37, 99, 235, 0.1)` | `var(--accent)` |
| `ready` | `rgba(56, 161, 105, 0.1)` | `#38a169` |
| `error` | `rgba(229, 62, 62, 0.1)` | `#e53e3e` |

В тёмной теме — те же цвета, фон автоматически контрастен.

### 6.4 Прогресс-бар

```css
/* Container */
height: 6px;
background: var(--bg-secondary);
border-radius: 3px;
overflow: hidden;

/* Bar */
height: 100%;
background: var(--accent);
border-radius: 3px;
transition: width 0.3s ease;
```

### 6.5 Таблица

```css
width: 100%;
border-collapse: collapse;
font-size: 13px;

/* Header */
th {
  background: var(--bg-secondary);
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--text-secondary);
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  white-space: nowrap;
}

/* Cell */
td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
}

/* Row hover */
tr:hover td {
  background: var(--surface-hover);
}
```

### 6.6 Модалка (overlay)

```css
/* Overlay */
position: fixed;
inset: 0;
background: rgba(0, 0, 0, 0.5);
backdrop-filter: blur(4px);
z-index: 1000;

/* Modal */
background: var(--bg);
border: 1px solid var(--border);
border-radius: 12px;
width: 480px;
max-width: 90vw;
box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
```

### 6.7 Карточка (source card pattern)

```css
background: var(--surface);
border: 1px solid var(--border);
border-radius: var(--radius);
padding: 10px 14px;
transition: border-color 0.15s, box-shadow 0.15s;
```
Hover: `border-color: var(--accent)`.
Expanded: `box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08)`.

### 6.8 Empty state

```css
height: 100%;
display: flex;
flex-direction: column;
align-items: center;
justify-content: center;
padding: 40px 20px;
```
Содержит: большую иконку (muted), заголовок, описание, CTA-кнопку.

---

## 7. Анимации

### Определены в `frontend/src/styles/chat.css`

| Имя | CSS | Назначение |
|-----|-----|-----------|
| `spin` | `to { transform: rotate(360deg); }` 1s linear infinite | Спиннеры загрузки |
| `pulse-bg` | `0%,100% { opacity:1; } 50% { opacity:0.6; }` 2s ease-in-out infinite | Typing indicator, pending states |
| `menu-fade-in` | `from { opacity:0; transform:translateY(-4px) scale(0.97); }` 0.12s ease-out | Dropdown-меню, появление элементов |
| `blink-cursor` | `0%,100% { opacity:1; } 50% { opacity:0; }` 1s step-end infinite | Streaming cursor |

### Transitions (стандартные)

- Цвет/фон: `0.15s`
- Размер/позиция: `0.2s`
- Сложные (карточки): `0.3s ease` или `0.35s cubic-bezier(.4,0,.2,1)`

---

## 8. Тёмная тема

### Механизм

- Атрибут `data-theme="dark"` на `<html>`
- Переключение: `useTheme()` хук (`frontend/src/hooks/useTheme.ts`)
- Сохранение: `localStorage`
- CSS: переопределение переменных в `[data-theme='dark'] { ... }`

### Правила

- Все цвета — через CSS-переменные. НИКОГДА не хардкодить цвета.
- Логотипы: `.logo-light` / `.logo-dark` с `display: none` переключением.
- Тени: в тёмной теме — более прозрачные или отключены.
- Иконки: цвет через `currentColor` или CSS-переменные.

---

## 9. Локализация (i18n)

### Механизм

- Библиотека: `i18next` + `react-i18next`
- Файлы: `frontend/src/locales/en.json`, `frontend/src/locales/ru.json`
- Конфигурация: `frontend/src/i18n.ts`
- Переключение: компонент `LanguageToggle`

### Правила

- Все пользовательские строки — через `t('key')`.
- Ключи: `section.element` (например, `docs.status.pending`, `reindex.cancel`).
- Интерполяция: `{{variable}}` (например, `t('upload.queued', { filename })`).
- Оба языка обязательны: EN и RU.

---

## 10. UI/UX референсы из индустрии

Анализ косвенных конкурентов из [BRAND_SLOGANS.md](BRAND_SLOGANS.md), [GTM_STRATEGY.md](GTM_STRATEGY.md) и `promo/CONTEXT.md`.

### Context7 (context7.com) — ближайший по модели

- Минималистичный dashboard: список библиотек со статусами, кнопка "Manage"
- Add Library: одно поле (URL), submit, автоматический парсинг и индексация
- Admin panel с табами: Configuration, Chat, Benchmark, Metrics, Versions
- Metrics: Page Views, API Requests, MCP Requests, графики трендов
- Построен на Mintlify. Чистый, минималистичный стиль.

### Documentation.AI (documentation.ai) — #1 Product Hunt

- Notion-style editor: drag-and-drop блоки, slash-команды, AI-агент
- Статус-индикаторы: Pending, Running, Success, Error, In Review
- Actions per document: Process, Reprocess, Track, Review, View Results
- Analytics dashboard: pageviews, sessions, bounce rate, feedback
- 100/100 Lighthouse, pixel-perfect, responsive, dark mode, 100+ компонентов

### GitBook — зрелая платформа (Est. 2014)

- Sidebar navigation: spaces, integrations, trash, settings
- Import panel: .docx, .html, .md, Google Docs, Notion, Confluence
- AI-assisted import для очистки контента
- Per-page actions menu

### Mintlify ($21.3M) — красивая документация

- Drag-and-drop file explorer, организация по папкам
- Live preview статуса
- AI search внутри документации

### ReadMe.io ($9M) — API-документация

- Dashboard с категоризацией документов
- Interactive API playground ("Try It")
- Enterprise-grade (SSO, RBAC, analytics)

### Postman — API-платформа

- Drag-and-drop импорт коллекций
- Single-click workflow, авторедирект к результату
- Streamlined UI для импорта

### Algolia — поисковая платформа

- Таблица индексов, статус индексации
- Уведомление об успешном сохранении после upload
- Минималистичный UI, фокус на статусах

### Синтезированные UI/UX принципы для IPCodex

1. **Чистая таблица/список** документов с фильтрацией по статусу и продукту
2. **Drag-and-drop upload** как основной способ загрузки
3. **Real-time статус-бейджи** с цветовой индикацией (Pending/Processing/Ready/Error)
4. **Inline-действия** для каждого документа (Download, Reindex, Delete)
5. **Прогресс-бары** для длительных операций (индексация, reindex)
6. **Минимум кликов**: upload → автоматический переход к отслеживанию
7. **Dark mode** из коробки
8. **Sidebar navigation** с переключением разделов (5 пунктов)
9. **Stepper** для многошаговых процессов (Upload → Processing → Ready)
10. **Empty states** с CTA-кнопкой для первого действия

---

## 11. Sidebar-навигация

### Разделы

IPCodex — публичный коммерческий SaaS-продукт. Sidebar содержит 5 разделов навигации (паттерн из GitBook, Documentation.AI, Postman, Algolia):

| Иконка (lucide-react) | Раздел | `activePage` value | Статус |
|---|---|---|---|
| `MessageSquare` | Chat | `'chat'` | Работает |
| `FileText` | Documents | `'documents'` | Реализуем |
| `Box` | Products | `'products'` | Заглушка (Coming Soon) |
| `BarChart3` | Analytics | `'analytics'` | Заглушка (Coming Soon) |
| `Settings` | Settings | `'settings'` | Заглушка (Coming Soon) |

### Стиль навигационных пунктов

```css
/* Nav item */
display: flex;
align-items: center;
gap: 10px;
padding: 8px 10px;
border-radius: 8px;
font-size: 13px;
font-weight: 500;
color: var(--text-secondary);
cursor: pointer;
transition: background 0.15s, color 0.15s;

/* Active */
background: var(--surface-hover);
color: var(--text);
border-left: 2.5px solid var(--accent);

/* Hover */
background: var(--surface-hover);
```

### Поведение

- При `activePage === 'chat'` — под навигацией показывается список сессий (как сейчас)
- При других страницах — список сессий скрывается, sidebar показывает только навигацию + footer
- Разделитель `1px solid var(--border)` между навигацией и контентом sidebar

### Страницы-заглушки

Компоненты `ProductsPage`, `AnalyticsPage`, `SettingsPage` — empty state (стиль как `.messages-empty`):
- Иконка раздела (48px, `color: var(--text-muted)`)
- Заголовок раздела (gradient text)
- Описание функционала (1-2 строки, `var(--text-secondary)`)
- Бейдж "Coming Soon" (pill-shape, `background: rgba(37, 99, 235, 0.08)`, `color: var(--accent)`)

---

## 12. Copyright и брендинг

IPCodex — **публичный коммерческий SaaS-продукт**. Copyright обязателен.

### Лендинг footer ✅

```
© 2026 IPCodex · by Aleh Vaitsekhovich
```

Где "Aleh Vaitsekhovich" — кликабельная ссылка на LinkedIn:
`https://www.linkedin.com/in/aleh-vaitsekhovich-067557a9/`
(`target="_blank"`, `rel="noopener noreferrer"`)

Реализовано в `frontend/src/pages/LandingPage.tsx`.

### App sidebar footer

В footer sidebar (рядом с переключателями темы и языка) добавить:

```
© 2026 IPCodex · by Aleh Vaitsekhovich
```

Стиль:
```css
font-size: 11px;
color: var(--text-muted);
```

### Референсы конкурентов

| Продукт | Copyright | Расположение |
|---------|-----------|-------------|
| Documentation.AI | © 2026 Documentation.AI | Footer сайта |
| Context7 | © 2026, Context7 is an Upstash project | Footer сайта |
| GitBook | Нет в app UI | — |
| Postman | Нет в app UI (есть на сайте) | — |

### Правило

Для публичного SaaS-продукта copyright должен быть виден в UI. Размещение в footer — стандартное решение.

### Локализация

```json
"landing.footer.copyright": "© 2026 IPCodex",
"landing.footer.by": "by" / "от",
"landing.footer.author": "Aleh Vaitsekhovich"
```

---

## 13. Структура файлов стилей

```
frontend/src/styles/
  globals.css      — CSS-переменные, reset, scrollbar, base styles
  chat.css         — Sidebar, layout, messages, input, sources, debug, file upload, code blocks
  landing.css      — ✅ Лендинг: header, hero, секции, карточки, steps, footer, responsive
  documents.css    — (Planned) Таблица документов, статус-бейджи, прогресс-бары, reindex panel, navigation tabs
```

### Правила

- Все стили — через CSS-переменные из `globals.css`.
- Без CSS-in-JS, без CSS Modules — plain CSS с BEM-подобными именами классов.
- Префиксы классов по компоненту: `.file-upload-*`, `.docs-*`, `.reindex-*`, `.nav-*`, `.landing-*`.
- Адаптивность: обязательна для всех компонентов (см. секцию 15).
- Анимации: переиспользовать существующие `@keyframes` из `chat.css`.

---

## 14. Тип продукта

**IPCodex — публичный коммерческий SaaS-продукт** для управления и поиска по технической документации с помощью AI.

### Следствия для UI/UX

- Copyright обязателен (см. секцию 12)
- Онбординг и empty states должны быть дружелюбными и информативными
- Все тексты локализованы (EN/RU)
- UI должен соответствовать стандартам коммерческих SaaS (профессиональный вид, консистентность, accessibility)
- Брендинг (логотип, цвета, шрифты) должен быть единообразным во всех разделах

---

## 15. Адаптивность (Responsive Design)

**Вся разметка должна корректно отображаться на компьютерах, планшетах и телефонах.**

### Breakpoints

| Устройство | Breakpoint | Поведение |
|---|---|---|
| Desktop | > 1024px | Полная раскладка, sidebar, таблицы, 3-колоночные сетки |
| Tablet | 768px–1024px | Sidebar скрыт (hamburger), 2-колоночные сетки, упрощённые таблицы |
| Mobile | < 768px | Одна колонка, карточки вместо таблиц, компактный header, hamburger-меню |
| Small Mobile | < 480px | Уменьшенные шрифты и отступы |

### Правила

- **Touch targets**: минимум 44×44px для кнопок на mobile (Apple HIG)
- **Лендинг**: hero — одна колонка на mobile; карточки — 1 колонка mobile, 2 tablet, 3 desktop
- **App sidebar**: на tablet/mobile — скрыт, открывается по hamburger (overlay)
- **Таблица документов**: на mobile — заменяется карточками
- **Header лендинга**: на mobile — hamburger-меню вместо горизонтальной навигации
- **CTA-кнопки**: на mobile — full-width
- **Все отступы/шрифты**: уменьшаются через media queries

### Media queries

```css
@media (max-width: 1024px) { /* Tablet */ }
@media (max-width: 768px)  { /* Mobile */ }
@media (max-width: 480px)  { /* Small mobile */ }
```

---

## 16. Роутинг

### Библиотека

`react-router-dom` (v7+)

### Структура роутов

| Путь | Компонент | Описание | Статус |
|------|-----------|----------|:------:|
| `/` | `LandingPage` | Публичный лендинг (маркетинговая страница) | ✅ |
| `/app` | `ChatApp` | Основное приложение (Chat) | ✅ |
| `/app/documents` | `DocumentsPage` | Управление документами | Planned |
| `/app/products` | `ProductsPage` | Продукты (заглушка) | Planned |
| `/app/analytics` | `AnalyticsPage` | Аналитика (заглушка) | Planned |
| `/app/settings` | `SettingsPage` | Настройки (заглушка) | Planned |
| `*` | Redirect → `/` | Fallback | ✅ |

### Файловая структура

```
frontend/src/
  pages/
    LandingPage.tsx    — Публичный лендинг
    ChatApp.tsx        — Основное приложение (бывший App.tsx)
    DocumentsPage.tsx  — (будущее) Управление документами
    ProductsPage.tsx   — (будущее) Заглушка
    AnalyticsPage.tsx  — (будущее) Заглушка
    SettingsPage.tsx   — (будущее) Заглушка
  App.tsx              — Роутер (Routes)
  main.tsx             — BrowserRouter + App
```

### nginx

Существующий `try_files $uri $uri/ /index.html` обеспечивает SPA fallback для всех роутов.
