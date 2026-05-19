# AI Mentor — Design System & UI/UX Guidelines

> **Status**: v1.0 — March 21, 2026
> **Author**: Oleg Voitekhovich
> **Purpose**: Единый источник правды по дизайн-системе для всех UI-компонентов AI Mentor.
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
- **Promo**: `promo/comparison.html`, `promo/ai-mentor.html` — inline SVG, 72×80px / 88px

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

### Цвета данных в Audit / Logs (определены в `frontend/src/styles/admin.css`)

Отдельная палитра для визуального разделения типов данных в строках аудита и логов.
Каждый тип данных имеет **уникальный цвет**, чтобы не путаться с UI-элементами (синие фильтры, ссылки).

| Переменная | Light | Dark | Назначение | CSS-класс |
|-----------|-------|------|-----------|-----------|
| `--log-info` | `#2563eb` | `#58a6ff` | Log level INFO | `.log-row__level--info` |
| `--log-warn` | `#b45309` | `#d29922` | Log level WARN | `.log-row__level--warning` |
| `--log-error` | `#dc2626` | `#f85149` | Log level ERROR, MCP error status | `.log-row__level--error` |
| `--log-debug` | `#6b7280` | `#8b949e` | Log level DEBUG | `.log-row__level--debug` |
| `--log-ok` | `#16a34a` | `#7ee787` | MCP status OK (зелёный = успех) | `.log-row__level--ok`, `.logs-level-chip--ok` |
| `--log-tool` | `#7c3aed` | `#a78bfa` | MCP tool name (фиолетовый = функция/API) | `.log-row__level--tool` |
| `--log-tenant` | `#0d9488` | `#5eead4` | Tenant email / username (бирюзовый) | `.log-row__level--tenant` |
| `--log-key` | `#16a34a` | `#7ee787` | JSON key в развёрнутой строке | — |
| `--log-highlight-bg` | `#fef08a` | `#e3b34180` | Подсветка поискового совпадения | `.log-highlight` |

**Принципы выбора цветов:**
- **Синий** (`--log-info`) — зарезервирован для UI-элементов (фильтры, ссылки, активные чипы) и нейтрального уровня INFO в логах
- **Фиолетовый** (`--log-tool`) — инструменты и функции (по аналогии с VS Code, где функции фиолетовые)
- **Бирюзовый** (`--log-tenant`) — пользователи/тенанты; нейтральный, хорошо различим от фиолетового
- **Зелёный** (`--log-ok`) — положительный статус (успех, OK); стандартная семантика «всё хорошо»
- **Красный** (`--log-error`) — ошибки; стандартная семантика «проблема»
- Все цвета имеют light/dark варианты для контраста на соответствующем фоне

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

**Toggle button (language / theme switch):**
Единый стиль для ВСЕХ страниц (auth, landing, app). Квадратная кнопка 36×36px.
```css
width: 36px;
height: 36px;
display: inline-flex;
align-items: center;
justify-content: center;
background: var(--surface);
border: 1px solid var(--border);
color: var(--text-secondary);
border-radius: 10px;
font-size: 0.8rem;
font-weight: 600;
```
Hover: `background: var(--surface-hover); border-color: var(--text-muted); color: var(--text)`.
- Language toggle: shows `RU` / `EN` text
- Theme toggle: shows `Sun` (18px) in dark mode, `Moon` (18px) in light mode
- CSS classes: `.landing-toggle-btn` (landing), `.theme-toggle` / `.lang-toggle` (auth pages)

**Primary CTA (gradient):**
Used for main call-to-action buttons on landing and auth pages.
```css
display: inline-flex;
align-items: center;
gap: 8px;
padding: 10px 24px;
background: var(--gradient);
color: #fff;
font-size: 14px;
font-weight: 600;
border: none;
border-radius: 8px;
```
Hover: `opacity: 0.9; transform: translateY(-1px)`.
Auth submit button uses the same gradient via `var(--gradient)`.

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

### 6.4 Прогресс-бар индексации

Прогресс-бар встроен в `StatusBadge` компонент и отображается при `status='processing'`:

```css
/* Container */
height: 6px;
background: var(--bg-secondary);
border-radius: 3px;
overflow: hidden;

/* Bar fill */
height: 100%;
background: var(--accent);
border-radius: 3px;
transition: width 0.3s ease;
```

**Прогресс-информация** (под бейджем):
- Процент: `font-size: 11px; font-weight: 600; color: var(--accent)` (`.docs-progress-pct`)
- Этап: `font-size: 10px; color: var(--text-muted)` (`.docs-progress-stage`)
- Контейнер: `.docs-progress-info` — `display: flex; gap: 6px; align-items: center`

**Этапы прогресса** (локализованы через i18n):

| Ключ | EN | RU | Диапазон % |
|------|----|----|:---:|
| `docs.stage.converting` | Converting to MD | Конвертация в MD | 0%→25% |
| `docs.stage.ocr` | OCR (image recognition) | OCR (распознавание изображений) | 25%→40% |
| `docs.stage.chunking` | Chunking | Разбиение на чанки | 40%→50% |
| `docs.stage.embedding` | Embedding | Эмбеддинг | 50%→90% |
| `docs.stage.storing` | Saving to DB | Сохранение в БД | 92% |

Для не-PDF или PDF без изображений: `converting` прыгает с 25% на 40% (этап OCR пропускается).

При `progress_percent > 0` — анимация `pulse-bg` заменяется на реальную ширину бара.
При `progress_percent === 0` и `status === 'processing'` — индетерминированная анимация.

### 6.4.1 Debug Timing Bar (DocumentDebugPanel)

Компонент `TimingBar` в debug-панели отображает 6 этапов индексации:

| Этап | Цвет | Поле |
|------|------|------|
| Read | `#4dabf7` (blue) | `read_ms` |
| Convert | `#69db7c` (green) | `convert_ms` |
| OCR | `#ff6b6b` (red) | `ocr_ms` |
| Parse | `#ffd43b` (yellow) | `parse_ms` |
| Embed | `#ff922b` (orange) | `embed_ms` |
| DB Write | `#da77f2` (purple) | `db_ms` |

**Дополнительные секции debug-панели:**
- **OCR** (показывается только если `ocr_images_total != null`): Images found, Recognized, Empty result, Failed
- **File** секция: добавлено поле `detected_language` (показывается если не null)

**Правила отображения:**
- Минимальная ширина сегмента: `MIN_PCT = 3%` (даже для 0ms этапов)
- Этапы с `rawPct < 1%` отображаются с `opacity: 0.45`
- Tooltip (`title`) показывает точное значение: `{label}: {ms}ms ({rawPct.toFixed(1)}%)`
- Все 5 этапов всегда видны в полоске

### 6.5 Таблица (DataTable)

Все таблицы в проекте используют **единый универсальный компонент** `DataTable` + хук `useDataTable`.

#### Файлы

| Файл | Назначение |
|------|-----------|
| `frontend/src/hooks/useDataTable.ts` | Хук: TanStack Table + localStorage persistence |
| `frontend/src/components/DataTable.tsx` | Компонент: рендеринг таблицы с DnD, группировкой, настройками колонок |

#### Функционал (одинаковый для всех таблиц)

| Функция | Описание |
|---------|----------|
| **Сортировка** | Multi-sort по клику на заголовок (TanStack `getSortedRowModel`) |
| **Перетаскивание колонок** | Drag-and-drop заголовков (`@dnd-kit/core` + `@dnd-kit/sortable`) |
| **Группировка** | По колонкам с `enableGrouping: true` (кнопки внизу таблицы) |
| **Видимость колонок** | Шестерёнка (⚙) — dropdown с чекбоксами |
| **Сохранение состояния** | `localStorage` с debounce 300ms (sorting, grouping, columnOrder, columnVisibility) |
| **Сброс настроек** | Кнопка "Reset to defaults" в dropdown настроек |
| **Expandable rows** | Через `renderExpandedRow` callback (debug-панели) |

#### Использование

```tsx
import { DataTable } from '../components/DataTable'
import { useDataTable } from '../hooks/useDataTable'

const DEFAULT_COLUMN_ORDER = ['name', 'status', 'size', 'actions']
const STORAGE_KEY = 'ai-mentor-my-table'

// В компоненте:
const { table, columnOrder, grouping, handleColumnOrderChange,
        removeGrouping, toggleGrouping, resetSettings } = useDataTable({
  data,
  columns,
  storageKey: STORAGE_KEY,
  defaultColumnOrder: DEFAULT_COLUMN_ORDER,
  getRowId: row => String(row.id),
  columnFilters,
  globalFilter,
  onGlobalFilterChange: setGlobalFilter,
})

<DataTable
  table={table}
  columnOrder={columnOrder}
  grouping={grouping}
  onColumnOrderChange={handleColumnOrderChange}
  removeGrouping={removeGrouping}
  toggleGrouping={toggleGrouping}
  resetSettings={resetSettings}
  renderExpandedRow={(row) => /* debug panel or null */}
/>
```

#### Таблицы в проекте

| Страница | `storageKey` | Колонки |
|----------|-------------|---------|
| `DocumentsPage` | `ai-mentor-docs-table` | title, format, status, size, chunks, product, uploaded, indexed, actions |
| `ProductsPage` | `ai-mentor-products-table` | name, documents, format, status, size, chunks, uploaded, indexed, actions |

#### Правило

**Любая новая таблица в проекте ОБЯЗАНА использовать `useDataTable` + `DataTable`.** Это гарантирует единообразный UX: сортировку, DnD колонок, группировку, настройки видимости и persistence в localStorage.

#### Базовые стили

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

#### Responsive strategy: sticky edges + scroll fallback

Tables in Products and Documents are **reference catalogs**, not analytics grids. The approach:

- **First column** (name/title) is `position: sticky; left: 0` -- always visible
- **Last column** (actions) is `position: sticky; right: 0` -- always visible
- **Middle columns** have `min-width` to prevent text truncation
- On wide screens everything fits with no scroll; on narrow screens horizontal scroll activates with sticky edges
- **<768px**: table is hidden, replaced by mobile cards (`.docs-cards`)
- Scroll shadows (`.docs-table-wrap--scrolled-left/right`) hint at scrollable content

Column min-widths (set via `.col-*` classes):

| Column | min-width | Notes |
|--------|-----------|-------|
| `col-name` / `col-title` | 180px | Sticky left |
| `col-documents` | 70px | |
| `col-format` | 100px | |
| `col-status` | 120px | Segmented bar in Products |
| `col-size` | 70px | |
| `col-chunks` | 60px | |
| `col-product` | 100px | Documents only |
| `col-uploaded` / `col-indexed` | 90px | Compact date, full datetime in tooltip |
| `col-actions` | 72px | Sticky right, primary btn + "..." dropdown |

#### Actions dropdown

Instead of 4-5 inline icon buttons, actions use a compact layout:
- **One primary button** always visible (edit for Products, debug for Documents)
- **"..." button** opens a dropdown with remaining actions (reindex, delete, etc.)
- Dropdown: `.docs-actions-dropdown`, positioned absolutely, auto-closes on outside click

#### Product segmented status bar

Products use a segmented color bar instead of individual status badges:
- Segments: green (ready), blue (processing), yellow (pending), red (error), gray (cancelled)
- Width proportional to document count in each status
- Compact text below: "90% 155/174"
- Full breakdown in tooltip on hover
- CSS: `.product-segmented-bar`, `.product-segmented-segment--{status}`

#### CSS-классы таблицы

| Класс | Назначение |
|-------|-----------|
| `.docs-table-wrap` | Контейнер с overflow: auto, scroll detection |
| `.docs-table` | Элемент `<table>` |
| `.docs-th` | Заголовок колонки |
| `.docs-th-inner` | Flex-контейнер внутри th (drag handle + label) |
| `.docs-th-drag` | Иконка GripVertical для перетаскивания |
| `.docs-th-label--sortable` | Кликабельный заголовок для сортировки |
| `.docs-sort-icon--active` | Активная иконка сортировки (accent) |
| `.docs-drag-overlay` | Overlay при перетаскивании колонки |
| `.docs-table-toolbar` | Тулбар над таблицей (кнопка настроек) |
| `.docs-col-settings-*` | Dropdown настроек колонок |
| `.docs-group-bar` | Полоска активных группировок |
| `.docs-group-actions` | Кнопки группировки под таблицей |
| `.docs-actions-dropdown` | Dropdown-меню действий |
| `.product-segmented-bar` | Сегментированный статус-бар продукта |
| `.docs-row-group` | Строка-группа (bg-secondary) |
| `.docs-group-cell` | Ячейка с toggle expand/collapse |

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

### Синтезированные UI/UX принципы для AI Mentor

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

AI Mentor — публичный коммерческий SaaS-продукт. Sidebar содержит 5 разделов навигации (паттерн из GitBook, Documentation.AI, Postman, Algolia):

| Иконка (lucide-react) | Раздел | `activePage` value | Статус |
|---|---|---|---|
| `MessageSquare` | Chat | `'chat'` | ✅ |
| `FileText` | Documents | `'documents'` | ✅ |
| `Box` | Products | `'products'` | ✅ |
| `BarChart3` | Analytics | `'analytics'` | ✅ |
| `Settings` | Settings | `'settings'` | ✅ |

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

AI Mentor — **публичный коммерческий SaaS-продукт**. Copyright обязателен.

### Лендинг footer ✅

```
© 2026 AI Mentor · by Aleh Vaitsekhovich
```

Где "Aleh Vaitsekhovich" — кликабельная ссылка на LinkedIn:
`https://www.linkedin.com/in/aleh-vaitsekhovich-067557a9/`
(`target="_blank"`, `rel="noopener noreferrer"`)

Реализовано в `frontend/src/pages/LandingPage.tsx`.

### App sidebar footer

В footer sidebar (рядом с переключателями темы и языка) добавить:

```
© 2026 AI Mentor · by Aleh Vaitsekhovich
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
"landing.footer.copyright": "© 2026 AI Mentor",
"landing.footer.by": "by" / "от",
"landing.footer.author": "Aleh Vaitsekhovich"
```

---

## 13. Структура файлов стилей

```
frontend/src/styles/
  globals.css      — CSS-переменные, reset, scrollbar, base styles
  auth.css         — ✅ Страницы авторизации: login, register, OAuth
  chat.css         — Sidebar, layout, messages, input, sources, debug, file upload, code blocks
  landing.css      — ✅ Лендинг: header, hero, секции, карточки, steps, footer, responsive
  documents.css    — ✅ Таблицы (sticky columns, min-widths, scroll shadows), статус-бейджи, segmented bar, actions dropdown, карточки (mobile), responsive
  admin.css        — ✅ Админ-панель: dashboard, tenants, roles, prompts, logs, stats, system
```

### Правила

- Все стили — через CSS-переменные из `globals.css`.
- Без CSS-in-JS, без CSS Modules — plain CSS с BEM-подобными именами классов.
- Префиксы классов по компоненту: `.file-upload-*`, `.docs-*`, `.reindex-*`, `.nav-*`, `.landing-*`.
- Адаптивность: обязательна для всех компонентов (см. секцию 15).
- Анимации: переиспользовать существующие `@keyframes` из `chat.css`.

---

## 14. Тип продукта

**AI Mentor — публичный коммерческий SaaS-продукт** для управления и поиска по технической документации с помощью AI.

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
- **Таблицы Products/Documents**: sticky name + sticky actions + horizontal scroll fallback on desktop; mobile cards on <768px (see section 6.5)
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
| `/app/documents` | `DocumentsPage` | Управление документами | ✅ |
| `/app/products` | `ProductsPage` | Список продуктов | ✅ |
| `/app/products/:manufacturer/:product` | `ProductDetailPage` | Детали продукта | ✅ |
| `/app/analytics` | `AnalyticsPage` | Аналитика | ✅ |
| `/app/settings` | `SettingsPage` | Настройки аккаунта | ✅ |
| `/s/:token` | `SharedView` | Публичная ссылка | ✅ |
| `/app/admin` | `AdminApp > DashboardPage` | Главная админ-панели | ✅ |
| `/app/admin/tenants` | `TenantsPage` | Управление тенантами | ✅ |
| `/app/admin/tenants/:id` | `TenantDetailPage` | Детали тенанта | ✅ |
| `/app/admin/documents` | `DocumentsAdminPage` | Документы (админ) | ✅ |
| `/app/admin/chats` | `ChatAuditPage` | Аудит чатов | ✅ |
| `/app/admin/roles` | `RolesPage` | Управление ролями | ✅ |
| `/app/admin/roles/:id` | `RoleDetailPage` | Детали роли | ✅ |
| `/app/admin/prompts` | `PromptsPage` | Управление промптами | ✅ |
| `/app/admin/prompts/:id` | `PromptEditorPage` | Редактор промптов | ✅ |
| `/app/admin/logs` | `LogsPage` | Логи | ✅ |
| `/app/admin/stats` | `StatsPage` | Статистика | ✅ |
| `/app/admin/system` | `SystemPage` | Системная информация | ✅ |
| `*` | Redirect → `/` | Fallback | ✅ |

### Файловая структура

```
frontend/src/
  hooks/
    useDataTable.ts    — ✅ Универсальный хук для таблиц (TanStack + DnD + localStorage)
  components/
    DataTable.tsx      — ✅ Универсальный компонент таблицы (DnD, группировка, настройки колонок)
  pages/
    LandingPage.tsx    — Публичный лендинг
    ChatApp.tsx        — Основное приложение (бывший App.tsx)
    DocumentsPage.tsx  — ✅ Управление документами (использует DataTable)
    ProductsPage.tsx   — ✅ Управление продуктами (использует DataTable)
    AnalyticsPage.tsx  — ✅ Заглушка (Coming Soon)
    SettingsPage.tsx   — ✅ Заглушка (Coming Soon)
  App.tsx              — Роутер (Routes)
  main.tsx             — BrowserRouter + App
```

### nginx

Существующий `try_files $uri $uri/ /index.html` обеспечивает SPA fallback для всех роутов.
