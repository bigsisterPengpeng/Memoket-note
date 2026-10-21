import { describe, expect, it } from 'vitest'
import { resolveDraft } from '../../util/draft'

const note = { title: 'T', content: 'stored', updated_at: '2026-09-14T10:00:00Z' }
const later = Date.parse('2026-09-14T10:05:00Z')
const earlier = Date.parse('2026-09-14T09:00:00Z')

describe('resolveDraft', () => {
  it('draft newer than the library and different: restore it; an empty title uses the stored one', () => {
    expect(resolveDraft(note, { title: '', content: 'draft', at: later }, false))
      .toEqual({ title: 'T', content: 'draft', restored: true, clear: false })
  })
  it('in probe mode a restored draft is also cleared (round 136: probe text mixed into a real note)', () => {
    expect(resolveDraft(note, { title: 'draft title', content: 'draft', at: later }, true)).toMatchObject({ title: 'draft title', restored: true, clear: true })
  })
  it('draft older / same content: use the stored one and clear the draft; with no draft nothing is cleared', () => {
    expect(resolveDraft(note, { title: 'x', content: 'draft', at: earlier }, false)).toEqual({ title: 'T', content: 'stored', restored: false, clear: true })
    expect(resolveDraft(note, { title: 'x', content: 'stored', at: later }, false)).toMatchObject({ restored: false, clear: true })
    expect(resolveDraft(note, null, false)).toEqual({ title: 'T', content: 'stored', restored: false, clear: false })
  })
})
