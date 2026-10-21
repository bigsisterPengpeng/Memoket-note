import { describe, expect, it } from 'vitest'
import { memoketMatches } from '../../util/memoketResults'

describe('Memoket recording matches', () => {
  it('keeps opaque IDs and ignores line and summary IDs', () => {
    expect(memoketMatches({ conversation_ids: ['1234567890123456789'], hits: [
      { conversation_id: '1234567890123456789', title: 'Fictional Maple' },
      { id: 'line-7', text: 'A transcript line' },
    ] })).toEqual([{ id: '1234567890123456789', title: 'Fictional Maple' }])
  })
  it('reads MCP text wrappers and deduplicates sources', () => {
    expect(memoketMatches({ content: [{ type: 'text', text: JSON.stringify({ conversation_ids: ['maple', 'maple'] }) }] }))
      .toEqual([{ id: 'maple', title: '' }])
  })
})
