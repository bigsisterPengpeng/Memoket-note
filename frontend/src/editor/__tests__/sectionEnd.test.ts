import { describe, expect, it } from 'vitest'
import { sectionEnd } from '../../util/sectionEnd'

const doc = '# Retro\n\n## Timeline\n\n### APP\n\nAPP body.\n\n### Hardware\n\nHardware body.\n\n## Team\n\nTeam body.\n'

describe('sectionEnd (same rule as backend outline.section_end)', () => {
  it('up to before the next heading of no deeper level', () => {
    expect(sectionEnd(doc, 'Hardware')).toBe(doc.indexOf('## Team'))
    expect(sectionEnd(doc, 'Timeline')).toBe(doc.indexOf('## Team'))
    expect(sectionEnd(doc, 'Team')).toBe(doc.length)
    expect(sectionEnd(doc, 'Missing')).toBeNull()
  })
  it('a # inside a fenced code block is not a heading', () => {
    const d = '## Alpha\n\n```sh\n# comment\n```\n\n## Beta\n'
    expect(sectionEnd(d, 'Alpha')).toBe(d.indexOf('## Beta'))
    expect(sectionEnd(d, 'comment')).toBeNull()
  })
})
