import { describe, expect, it } from 'vitest'
import citationCases from '../../../../shared/citation-ids.json'
import { CITE_RE_SOURCE, citedFactIds, stripCitations } from '../../util/wordCount'

describe('manual KITE citations', () => {
  it('recognizes source identifiers produced by manual fact entry', () => {
    const id = 'note-abcdef123456-manualF1'
    expect([...`Saved evidence [${id}]`.matchAll(new RegExp(CITE_RE_SOURCE, 'g'))].map(m => m[1])).toEqual([id])
  })
  it('keeps extracted fact support and excludes arbitrary bracketed text', () => {
    const matches = [...'[demo-12-abcd] [ordinary label] [note-abcdef123456-manualF0]'.matchAll(new RegExp(CITE_RE_SOURCE, 'g'))]
    expect(matches.map(m => m[1])).toEqual(['demo-12-abcd'])
  })
})


describe('imported source citations', () => {
  it('uses the same source formats as backend checks and backlinks', () => {
    const cases = citationCases
    const text = cases.valid.map(id => `Evidence [${id}].`).join(' ')
    expect(citedFactIds(text)).toEqual(cases.valid)
    expect(stripCitations(text)).not.toContain('obsidian-')
    expect(citedFactIds(cases.invalid.map(id => `[${id}]`).join(' '))).toEqual([])
  })
})
