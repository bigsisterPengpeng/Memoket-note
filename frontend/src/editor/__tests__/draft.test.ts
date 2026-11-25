import { describe, expect, it } from 'vitest'
import { resolveDraft } from '../../util/draft'

const note = { title: 'T', content: 'stored', updated_at: '2026-09-14T10:00:00Z' }
const later = Date.parse('2026-09-14T10:05:00Z')
const earlier = Date.parse('2026-09-14T09:00:00Z')

describe('resolveDraft', () => {
  it('restores a newer title-only edit after a failed save', () => {
    expect(resolveDraft(note, { title: 'Revised Maple report', content: note.content, at: later }, false))
      .toEqual({ title: 'Revised Maple report', content: 'stored', restored: true, clear: false })
  })
  it('preserves an intentionally cleared title when restoring a title-only edit', () => {
    expect(resolveDraft(note, { title: '', content: note.content, at: later }, false))
      .toEqual({ title: '', content: 'stored', restored: true, clear: false })
  })
  it('restores a newer body edit with its intentionally empty title', () => {
    expect(resolveDraft(note, { title: '', content: 'draft', at: later }, false))
      .toEqual({ title: '', content: 'draft', restored: true, clear: false })
  })
  it('clears a restored body draft in probe mode', () => {
    expect(resolveDraft(note, { title: 'draft title', content: 'draft', at: later }, true)).toMatchObject({ title: 'draft title', restored: true, clear: true })
  })
  it('keeps the saved note for an outdated or identical draft', () => {
    expect(resolveDraft(note, { title: 'x', content: 'draft', at: earlier }, false)).toEqual({ title: 'T', content: 'stored', restored: false, clear: true })
    expect(resolveDraft(note, { title: note.title, content: 'stored', at: later }, false)).toMatchObject({ restored: false, clear: true })
    expect(resolveDraft(note, null, false)).toEqual({ title: 'T', content: 'stored', restored: false, clear: false })
  })
  it('discards a title-only draft older than the saved note', () => {
    expect(resolveDraft(note, { title: 'Outdated Maple title', content: note.content, at: earlier }, false))
      .toEqual({ title: 'T', content: 'stored', restored: false, clear: true })
  })
  it('clears a recovered title-only draft in probe mode', () => {
    expect(resolveDraft(note, { title: 'Maple preview', content: note.content, at: later }, true))
      .toEqual({ title: 'Maple preview', content: 'stored', restored: true, clear: true })
  })
})
