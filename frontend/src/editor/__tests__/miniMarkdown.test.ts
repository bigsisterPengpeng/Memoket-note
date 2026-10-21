import { describe, expect, it } from 'vitest'

import { parseInline, parseMini } from '../../util/miniMarkdown'

describe('the small block of markdown in the daily report', () => {
  it('recognizes subheadings, lists, paragraphs', () => {
    const b = parseMini('## What moved forward\n\n- changed a.py\n- changed b.py\n\nThat is all.')
    expect(b.map((x) => x.kind)).toEqual(['h', 'ul', 'p'])
    expect(b[1].kind === 'ul' && b[1].items).toHaveLength(2)
  })

  it('consecutive list items go into the same ul; separated ones start another', () => {
    const b = parseMini('- a\n- b\n\n## Where it got stuck\n\n- c')
    expect(b.map((x) => x.kind)).toEqual(['ul', 'h', 'ul'])
  })

  it('bold and inline code are cut out, and the plain text on both sides is kept', () => {
    expect(parseInline('**Code** took `4 hours`, the rest')).toEqual([
      { t: 'b', s: 'Code' },
      { t: 'text', s: ' took ' },
      { t: 'code', s: '4 hours' },
      { t: 'text', s: ', the rest' },
    ])
  })

  it('a line without markers is just a piece of text as-is', () => {
    expect(parseInline('Nothing special today')).toEqual([{ t: 'text', s: 'Nothing special today' }])
  })

  it('soft line breaks in CJK paragraphs add no space; between English words they do', () => {
    const [zh] = parseMini('\u7b2c\u4e00\u884c\n\u7b2c\u4e8c\u884c')   // two CJK lines
    expect(zh.kind === 'p' && zh.parts[0].s).toBe('\u7b2c\u4e00\u884c\u7b2c\u4e8c\u884c')
    const [en] = parseMini('first line\nsecond line')
    expect(en.kind === 'p' && en.parts[0].s).toBe('first line second line')
  })

  it('empty body does not blow up', () => {
    expect(parseMini('')).toEqual([])
  })
})

describe('code fences', () => {
  it('a fence is kept whole with its newlines -- without recognizing it a mermaid diagram is squashed into one line of garbage', () => {
    const b = parseMini('# T\n\n```mermaid\ngraph TD\nA-->B\n```\n\nA paragraph after')
    expect(b.map((x) => x.kind)).toEqual(['h', 'pre', 'p'])
    expect(b[1].kind === 'pre' && b[1]).toMatchObject({ lang: 'mermaid', text: 'graph TD\nA-->B' })
  })

  it('- and ## inside a fence are not lists or headings', () => {
    const b = parseMini('```\n- not a list\n## not a heading\n```')
    expect(b).toHaveLength(1)
    expect(b[0].kind).toBe('pre')
  })

  it('an unclosed fence runs to the end without blowing up', () => {
    const b = parseMini('```python\nprint(1)')
    expect(b[0].kind === 'pre' && b[0].text).toBe('print(1)')
  })
})
