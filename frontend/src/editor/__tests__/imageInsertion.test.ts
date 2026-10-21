import { describe, expect, it } from 'vitest'
import { imageInsertion } from '../imagePaste'

describe('imageInsertion', () => {
  it('cursor in the middle of a heading line: insert after the end of this line, the heading is not split', () => {
    // the CJK heading "# One year of the startup" (6 CJK characters) starts at 0, cursor after "# " (pos 2), line end 8
    const r = imageInsertion('# \u521b\u4e1a\u4e00\u5e74\u56de\u987e', 8, 2, '![p](u)')
    expect(r).toEqual({ at: 8, text: '\n\n![p](u)\n' })
  })
  it('on a blank line, place it right there', () => {
    expect(imageInsertion('', 10, 10, '![p](u)')).toEqual({ at: 10, text: '![p](u)' })
  })
})
