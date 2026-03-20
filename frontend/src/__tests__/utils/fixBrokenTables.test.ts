import { describe, it, expect } from 'vitest'
import { fixBrokenTables } from '../../utils/fixBrokenTables'

describe('fixBrokenTables', () => {
  it('passes through text without tables unchanged', () => {
    const md = 'Hello **world**\n\nSome paragraph.'
    expect(fixBrokenTables(md)).toBe(md)
  })

  it('does not modify a valid GFM table', () => {
    const md = '| Name | Type |\n| --- | --- |\n| id | string |'
    expect(fixBrokenTables(md)).toBe(md)
  })

  it('inserts separator when header row is followed by data row', () => {
    const md = '| Параметр | Описание |\n| id | Идентификатор карты |'
    const result = fixBrokenTables(md)
    expect(result).toContain('| --- | --- |')
    const lines = result.split('\n')
    expect(lines[0]).toBe('| Параметр | Описание |')
    expect(lines[1]).toBe('| --- | --- |')
    expect(lines[2]).toBe('| id | Идентификатор карты |')
  })

  it('handles table without leading/trailing pipes', () => {
    const md = 'Field | Type\nid | string'
    const result = fixBrokenTables(md)
    expect(result).toContain('---')
  })

  it('inserts separator for 3-column table', () => {
    const md = '| A | B | C |\n| 1 | 2 | 3 |'
    const result = fixBrokenTables(md)
    expect(result).toContain('| --- | --- | --- |')
  })

  it('collapses blank lines between pipe rows', () => {
    const md = '| Name | Type |\n| --- | --- |\n\n| id | string |'
    const result = fixBrokenTables(md)
    expect(result).toBe('| Name | Type |\n| --- | --- |\n| id | string |')
  })

  it('handles multiple blank lines between pipe rows', () => {
    const md = '| A | B |\n| --- | --- |\n\n\n| 1 | 2 |'
    const result = fixBrokenTables(md)
    expect(result).not.toContain('\n\n')
    expect(result).toContain('| 1 | 2 |')
  })

  it('does not break code blocks containing pipes', () => {
    const md = '```python\ndata = {"a": 1 | 2}\n```'
    expect(fixBrokenTables(md)).toBe(md)
  })

  it('handles table embedded in surrounding text', () => {
    const md = 'Some intro text.\n\n| Param | Desc |\n| id | The ID |\n\nMore text.'
    const result = fixBrokenTables(md)
    expect(result).toContain('| --- | --- |')
    expect(result).toContain('Some intro text.')
    expect(result).toContain('More text.')
  })

  it('does not double-insert separator if already present', () => {
    const md = '| A | B |\n| --- | --- |\n| 1 | 2 |'
    const result = fixBrokenTables(md)
    const separators = result.split('\n').filter(l => /^\|[\s:|\-]+\|$/.test(l.trim()) && l.includes('-'))
    expect(separators.length).toBe(1)
  })

  it('handles real-world LLM output with params table', () => {
    const md = [
      '**Метод:** `axxonsoft.bl.maps.MapService.ChangeMaps`',
      '',
      '**Действие:** `created`',
      '',
      'Параметры запроса (`data.created`):',
      '',
      '| Параметр | Описание |',
      '| `id` | Идентификатор карты. |',
      '| `name` | Название карты. |',
    ].join('\n')

    const result = fixBrokenTables(md)
    expect(result).toContain('| --- | --- |')

    const lines = result.split('\n')
    const headerIdx = lines.findIndex(l => l.includes('Параметр') && l.includes('Описание'))
    expect(lines[headerIdx + 1]).toContain('---')
    expect(lines[headerIdx + 2]).toContain('`id`')
  })

  it('fixes table where separator row has no dashes', () => {
    const md = '| A | B |\n| | |\n| 1 | 2 |'
    const result = fixBrokenTables(md)
    expect(result).toContain('---')
  })

  it('returns empty string for empty input', () => {
    expect(fixBrokenTables('')).toBe('')
  })

  it('handles single pipe row without crash', () => {
    const md = '| just one row |'
    expect(fixBrokenTables(md)).toBe(md)
  })
})
