import { describe, expect, it } from 'vitest'
import { CITE_RE_SOURCE } from '../../util/wordCount'

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
