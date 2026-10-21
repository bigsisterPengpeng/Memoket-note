import { describe, expect, it } from 'vitest'
import { matchSnippet } from '../../util/snippet'

describe('search snippet', () => {
  it('keeps a short prefix, so the hit is not eaten by a one-line ellipsis', () => {
    const content = '# Title\n\n' + 'a very very long rambling preamble '.repeat(5) + 'Apr 16 EVT prepared 4 hosts' + ' and more content after'.repeat(5)
    const s = matchSnippet(content, 'EVT', 40, 8)!
    expect(s.hit).toBe('EVT')
    expect(s.before.replace(/^…/, '').length).toBeLessThanOrEqual(8)
    expect(s.after.length).toBeGreaterThan(20)
  })
  it('no hit gives null; hashes and list markers stay out of the snippet', () => {
    expect(matchSnippet('# Title\n- one item', 'zzz')).toBeNull()
    expect(matchSnippet('# Title EVT', 'evt')!.before).toBe('Title ')
  })
})
