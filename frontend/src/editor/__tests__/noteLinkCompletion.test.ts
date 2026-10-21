import { describe, expect, it } from 'vitest'
import { disambiguate } from '../noteLinkCompletion'

describe('telling same-name notes apart in [[ completion', () => {
  it('unique names get only a date; duplicates get the first body sentence', () => {
    const hits = [
      { title: 'Startup year in review', content: '# Startup year in review\n\n## Timeline\n\n- **Apr 16 EVT**: 4 hosts', updated_at: '2026-09-10T00:00:00Z' },
      { title: 'Startup year in review', content: 'Startup year in review\n\nLesson: sell first.', updated_at: '2026-09-07T00:00:00Z' },
      { title: 'Startup reflections', content: 'whatever', updated_at: '2026-09-02T00:00:00Z' },
    ]
    const d = disambiguate(hits)
    expect(d[2]).not.toContain('·')
    expect(d[0]).toMatch(/· Apr 16 EVT: 4 hosts$/)
    expect(d[1]).toMatch(/· Lesson: sell first\.$/)
  })
  it('when the body has only the title, fall back to the date', () => {
    const hits = [
      { title: 'A', content: '# A', updated_at: '2026-09-10T00:00:00Z' },
      { title: 'A', content: '', updated_at: '2026-09-09T00:00:00Z' },
    ]
    expect(disambiguate(hits).every((x) => !x.includes('·'))).toBe(true)
  })
})
