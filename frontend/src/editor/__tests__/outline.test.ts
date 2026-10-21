/** Independently authored fixtures for outline parsing; no production notes. */
import { describe, expect, it } from 'vitest'
import { setLang } from '../../i18n'
import { parseFallbackAnchors, parseHeadings } from '../../components/DocumentOutline'
setLang('en')

const NOTE_WITH_CODE = '## Background\n\nA short introduction.\n\n## Script\n\n```python\n# Sort the books\nbooks.sort()\n# Print the catalog\nprint(books)\n```\n\n## Results\n\nThe catalog is ready.'

describe('parseHeadings', () => {
  it('ignores comments inside code blocks', () => {
    expect(parseHeadings(NOTE_WITH_CODE).map(h => h.text)).toEqual(['Background', 'Script', 'Results'])
  })
  it('preserves heading levels and source positions', () => {
    const prefix = '# First\n\nBody\n\n'
    const hs = parseHeadings(prefix + '### Third\n')
    expect(hs.map(h => h.level)).toEqual([1, 3])
    expect(hs[1].pos).toBe(prefix.length)
  })
  it('treats content after an unclosed fence as code', () => {
    expect(parseHeadings('## Visible\n\n```\n# Hidden\n').map(h => h.text)).toEqual(['Visible'])
  })
  it('recognizes tilde fences', () => {
    expect(parseHeadings('## Visible\n\n~~~\n# Hidden\n~~~\n').map(h => h.text)).toEqual(['Visible'])
  })
  it('parses ordinary heading levels', () => {
    expect(parseHeadings('# One\n## Two\n### Three').map(h => h.text)).toEqual(['One', 'Two', 'Three'])
  })
  it('truncates an embedded second heading marker', () => {
    const hs = parseHeadings('## Reading plan: ### Shelf guide\n')
    expect(hs.map(h => h.text)).toEqual(['Reading plan:'])
    expect(hs[0].level).toBe(2)
    expect(hs[0].pos).toBe(0)
  })
  it('preserves literal hash characters in names and issue numbers', () => {
    expect(parseHeadings('## C# notes\n### Issue #3 review\n').map(h => h.text)).toEqual(['C# notes', 'Issue #3 review'])
  })
  it('removes inline markup while preserving labels', () => {
    expect(parseHeadings('### **Reading habits**\n').map(h => h.text)).toEqual(['Reading habits'])
    expect(parseHeadings('## See [catalog](note://example) here\n').map(h => h.text)).toEqual(['See catalog here'])
    expect(parseHeadings('## `sort` examples\n').map(h => h.text)).toEqual(['sort examples'])
    expect(parseHeadings('## ![Book cover](/api/assets/example.png)\n').map(h => h.text)).toEqual(['Image: Book cover'])
  })
  it('strips paired markup before truncating an embedded marker', () => {
    expect(parseHeadings('## **Reading plan: ### Shelf guide**\n').map(h => h.text)).toEqual(['Reading plan:'])
  })
  it('keeps source positions after stripping inline markup', () => {
    const prefix = '# First\n\nBody\n\n'
    const hs = parseHeadings(prefix + '### **Third**\n')
    expect(hs.map(h => h.level)).toEqual([1, 3])
    expect(hs[1].pos).toBe(prefix.length)
    expect(hs[1].text).toBe('Third')
  })
})

const SIMPLE_NOTE = 'Overview:\n\nThe library is planning an evening reading group.\n\nSchedule:\n\nThe group meets every Tuesday after the library closes.\n\nBooks:\n\nReaders can nominate the next title at each session.'
describe('parseFallbackAnchors', () => {
  it('recognizes three short colon headings with correct positions', () => {
    const r = parseFallbackAnchors(SIMPLE_NOTE)
    expect(r.how).toBe('short')
    expect(r.items.map(h => h.text)).toEqual(['Overview', 'Schedule', 'Books'])
    expect(r.items[1].pos).toBe(SIMPLE_NOTE.indexOf('Schedule:'))
  })
  it('recognizes bare headings while excluding sentences and list items', () => {
    const note = 'Overview\n\nThe library is planning an evening reading group.\n\nSchedule\n\nReaders meet after closing on Tuesday evenings.\n\nBooks\n\nMembers nominate the next title at each session.\n\nA sentence.\n\n- A list item\n\n(2) Another item'
    const r = parseFallbackAnchors(note)
    expect(r.how).toBe('short')
    expect(r.items.map(h => h.text)).toEqual(['Overview', 'Schedule', 'Books'])
  })
  it('falls back to paragraph labels when no short headings exist', () => {
    const r = parseFallbackAnchors('The library has a reading room for visitors! More details follow.\n\nReaders may reserve a desk for quiet work! Further guidance follows.')
    expect(r.how).toBe('paragraph')
    expect(r.items).toHaveLength(2)
    expect(r.items[0].text.startsWith('The library')).toBe(true)
    expect(r.items[1].text.startsWith('Readers may')).toBe(true)
  })
  it('strips list markers and numbering from paragraph labels', () => {
    const r = parseFallbackAnchors('- The first paragraph describes the library reading room and its opening hours.\n\n3. The second paragraph explains how to reserve a desk for quiet work.')
    expect(r.items[0].text.startsWith('The first')).toBe(true)
    expect(r.items[1].text.startsWith('The second')).toBe(true)
  })
  it('excludes fenced code from paragraph fallback', () => {
    const r = parseFallbackAnchors('```\n# Looks like a heading:\nx = 1\n```\n\nThe first paragraph describes the library reading room.\n\nThe second paragraph explains desk reservations.')
    expect(r.how).toBe('paragraph')
    expect(r.items.every(h => !h.text.includes('Looks like'))).toBe(true)
  })
  it('has no outline for a short note', () => {
    expect(parseFallbackAnchors('A sentence.').how).toBe('none')
  })
})
