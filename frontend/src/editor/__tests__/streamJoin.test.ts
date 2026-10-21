import { describe, expect, it } from 'vitest'
import { insertStreamed, applyScrub, prepareInsert } from '../streamJoin'

describe('insertStreamed', () => {
  it('three or more newlines in a delta are squeezed into a paragraph break', () => {
    const r = insertStreamed('\u524d\u6587\u3002\n\n', 5, '\u786e\u8ba4\u3002\n\n\n\n\u8fd8\u8981\u628a')   // CJK text with CJK full stops
    expect(r.next).toBe('\u524d\u6587\u3002\n\n\u786e\u8ba4\u3002\n\n\u8fd8\u8981\u628a')
    expect(r.cursor).toBe(r.next.length)
  })
  it('newlines split across chunks are squeezed too: two at the end of one chunk, two at the start of the next', () => {
    let s = '\u524d\u6587\u3002\n\n'; let cur: number | null = s.length
    for (const chunk of ['\u4e00\u6bb5\n\n', '\n\n\u4e8c\u6bb5']) { const r = insertStreamed(s, cur, chunk); s = r.next; cur = r.cursor }
    expect(s).toBe('\u524d\u6587\u3002\n\n\u4e00\u6bb5\n\n\u4e8c\u6bb5')
  })
  it('a delta without extra newlines is inserted as-is, with the cursor at the end of the delta', () => {
    const r = insertStreamed('abc', 1, 'XY')
    expect(r.next).toBe('aXYbc')
    expect(r.cursor).toBe(3)
  })
  it('an empty / out-of-range cursor appends at the end', () => {
    expect(insertStreamed('abc', null, 'd').next).toBe('abcd')
    expect(insertStreamed('abc', 99, 'd').next).toBe('abcd')
  })
  it('only touches the seam: consecutive blank lines elsewhere in the body are left alone', () => {
    const r = insertStreamed('x\n\n\n\ny', 6, 'z')
    expect(r.next).toBe('x\n\n\n\nyz')
  })
})

import { tidyBlankLines } from '../streamJoin'

describe('tidyBlankLines (copied from the backend)', () => {
  it('three blank lines squeezed into one, trailing whitespace stripped', () => {
    expect(tidyBlankLines('a  \n\n\n\nb')).toBe('a\n\nb')
  })
  it('blank lines and whitespace inside code blocks are kept as-is', () => {
    const s = 'x\n```\nline  \n\n\n\nend\n```\ny'
    expect(tidyBlankLines(s)).toBe(s)
  })
  it('leaves alone text without extra blank lines', () => {
    expect(tidyBlankLines('a\n\nb\nc')).toBe('a\n\nb\nc')
  })
})

describe('applyScrub (per the server\'s scrub_meta_sentences_v)', () => {
  it('deletes that sentence, eats the leading/trailing spaces of the paragraph\'s other sentences, trims the whole note', () => {
    const c = '\u524d\u8a00\u3002\n\nDVT \u8282\u70b9\u8c03\u6574\u3002 [t-1-A] \u8fd9\u4e00\u6b65\u4e0d\u80fd\u636e\u6b64\u5224\u65ad\u5df2\u7ecf\u5b8c\u6210\u3002 \u540e\u9762\u7ee7\u7eed\u3002\n\n# \u6807\u9898\n\n\u5c3e\u5df4\u3002\n'   // CJK sentences split on CJK full stops
    // the server splits sentences on the CJK full stop / exclamation / question marks, and a citation id after the previous full stop goes to the next sentence -- the sentence sent starts with "[t-1-A] ..."
    expect(applyScrub(c, '[t-1-A] \u8fd9\u4e00\u6b65\u4e0d\u80fd\u636e\u6b64\u5224\u65ad\u5df2\u7ecf\u5b8c\u6210\u3002')).toBe('\u524d\u8a00\u3002\n\nDVT \u8282\u70b9\u8c03\u6574\u3002\u540e\u9762\u7ee7\u7eed\u3002\n\n# \u6807\u9898\n\n\u5c3e\u5df4\u3002')
    // not a whole-sentence match (only a substring): leave it alone
    expect(applyScrub(c, '\u8fd9\u4e00\u6b65\u4e0d\u80fd\u636e\u6b64\u5224\u65ad\u5df2\u7ecf\u5b8c\u6210\u3002')).toBe(c)
  })
  it('sentence not found / inside a table or code block: unchanged', () => {
    expect(applyScrub('a\u3002 b\u3002', '\u6ca1\u6709')).toBe('a\u3002 b\u3002')
    expect(applyScrub('| x | \u4e0d\u80fd\u636e\u6b64\u3002 |', '\u4e0d\u80fd\u636e\u6b64\u3002')).toBe('| x | \u4e0d\u80fd\u636e\u6b64\u3002 |')
  })
})

describe('prepareInsert (per the server\'s outline.insert_into)', () => {
  it('one blank line each side; blank lines reserved at the end are taken back first; stray punctuation right after the insertion point is dropped', () => {
    expect(prepareInsert('## A\n\u6b63\u6587\u3002\n\n\n## B\n\u4e59\n\n\n', 9)).toEqual({ next: '## A\n\u6b63\u6587\u3002\n\n\n\n## B\n\u4e59\n', cursor: 10 })
    expect(prepareInsert('\u7532\u3002\uff0c\u540e\u534a\u53e5', 2)).toEqual({ next: '\u7532\u3002\n\n\n\n\u540e\u534a\u53e5', cursor: 4 })   // a stray CJK comma after the insertion point
  })
})
