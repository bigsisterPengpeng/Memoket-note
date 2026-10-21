import { describe, expect, it } from 'vitest'
import { clipTitle, displayTitle } from '../../util/displayTitle'

describe('displayTitle', () => {
  it('keeps an explicit title', () => {
    expect(displayTitle({ title: 'Library reading list', content: 'Other text' })).toBe('Library reading list')
  })
  it('uses the first body line for a placeholder and handles CJK sentence punctuation', () => {
    expect(displayTitle({ title: '\u672a\u547d\u540d', content: '# Library reading list\nBody' })).toBe('Library reading list')
    expect(displayTitle({ title: '', content: '\n\n\u8bfb\u4e66\u8ba1\u5212\u3002\u7b2c\u4e8c\u53e5' })).toBe('\u8bfb\u4e66\u8ba1\u5212')
  })
  it('clips at a qualifying clause break and bounds long titles', () => {
    expect(clipTitle('The library opens on Saturday, bring your reading list')).toBe('The library opens on Saturday')
    expect(clipTitle('Yes, please continue')).toBe('Yes, please continue')
    expect(clipTitle('Books: choose a title, reserve a copy')).toBe('Books: choose a title')
    expect(clipTitle('Library opening hours: Saturday mornings')).toBe('Library opening hours')
    expect(clipTitle('x'.repeat(80))).toHaveLength(60)
  })
  it('strips indentation and heading markers', () => {
    expect(displayTitle({ title: '', content: '    # Reading list\n    ## Fiction' })).toBe('Reading list')
  })
  it('falls back to Untitled for an empty note', () => {
    expect(displayTitle({ title: 'Untitled', content: '   \n  ' })).toBe('Untitled')
  })
})
