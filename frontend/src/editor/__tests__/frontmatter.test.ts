import { describe, expect, it } from 'vitest'

import { frontmatterEnd } from '../frontmatter'

/**
 * The criterion must be **strict**: judging wrong would dim the body's first paragraph as metadata.
 * So every case is written as "should this note count".
 */
describe('front-matter detection', () => {
  it('the opening block of a slides note counts (the screenshot\'s source)', () => {
    expect(frontmatterEnd('---\nmarp: true\nslides: true\n---\n\n# Startup year in review')).toBe(4)
  })

  it('an empty front-matter counts too', () => {
    expect(frontmatterEnd('---\n---\nbody')).toBe(2)
  })

  it('if the first line is not --- it does not count', () => {
    expect(frontmatterEnd('# Title\n\n---\nmarp: true\n---')).toBe(0)
  })

  it('**without a closing --- it does not count** -- otherwise the whole note would be dimmed', () => {
    expect(frontmatterEnd('---\nmarp: true\n\n# Body\n\nno more rules after this')).toBe(0)
  })

  it('an ordinary sentence in between means it does not count -- that is a rule plus a paragraph of body', () => {
    expect(frontmatterEnd('---\nThis is an ordinary sentence, not key: value\n---')).toBe(0)
  })

  it('list items and indented continuation lines are part of the YAML', () => {
    expect(frontmatterEnd('---\ntags:\n  - a\n  - b\n---\nbody')).toBe(5)
  })

  it('overly long ones do not count (front-matter should never exceed 30 lines)', () => {
    const long = '---\n' + Array.from({ length: 40 }, (_, i) => `k${i}: v`).join('\n') + '\n---'
    expect(frontmatterEnd(long)).toBe(0)
  })

  it('empty / ordinary documents do not count', () => {
    expect(frontmatterEnd('')).toBe(0)
    expect(frontmatterEnd('Just an ordinary sentence.')).toBe(0)
  })
})
