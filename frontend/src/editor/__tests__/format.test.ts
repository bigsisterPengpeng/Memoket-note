import { describe, expect, it } from 'vitest'
import { fixBoldPunct, formatMarkdown } from '../format'

describe('fixBoldPunct', () => {
  it('moves punctuation inside bold to the outside', () => {
    expect(fixBoldPunct('**\u4f9d\u8d56\u94fe\uff1a**\u5bb9\u91cf\u786e\u8ba4')).toBe('**\u4f9d\u8d56\u94fe**\uff1a\u5bb9\u91cf\u786e\u8ba4')   // CJK colon before the closing ** followed by CJK text
    expect(fixBoldPunct('- **\u63d0\u51fa\u53d8\u66f4\u7684\u4eba**\uff1a\u8bb0\u5f55')).toBe('- **\u63d0\u51fa\u53d8\u66f4\u7684\u4eba**\uff1a\u8bb0\u5f55')
  })
  it('applies when formatting the whole note; code blocks untouched', () => {
    const out = formatMarkdown('**\u4f9d\u8d56\u94fe\uff1a**\u5bb9\u91cf\n\n```\n**a\uff1a**\n```\n')
    expect(out).toContain('**\u4f9d\u8d56\u94fe**\uff1a\u5bb9\u91cf')
    expect(out).toContain('**a\uff1a**')
  })
})

describe('formatMarkdown is idempotent', () => {
  it('formatting twice gives the same result', () => {
    const src = '# \u6807\u9898\n\u6bb5\u843d\u4e2d\u6587English\u6df7\u6392\u3002\n- \u5217\u88681\n- \u5217\u88682\n|a|b|\n|-|-|\n|1|2|\n```py\nx=1\n```\n> \u5f15\u7528\n**\u7c97\u4f53\uff1a**\u540e\u9762'   // mixed CJK/Latin sample
    const once = formatMarkdown(src)
    expect(formatMarkdown(once)).toBe(once)
  })
})

import { stripCommonIndent } from '../format'
describe('stripCommonIndent', () => {
  it('a note indented 4 spaces throughout loses the common indent', () => {
    expect(stripCommonIndent('    # Title\n\n    ## Level two\n        - child')).toBe('# Title\n\n## Level two\n    - child')
  })
  it('with fences or inconsistent indentation, leave it alone', () => {
    expect(stripCommonIndent('    a\nb')).toBe('    a\nb')
    expect(stripCommonIndent('    ```\n    x\n    ```')).toBe('    ```\n    x\n    ```')
  })
  it('applies when formatting the whole note', () => {
    expect(formatMarkdown('    ## Title\n    body')).toBe('## Title\n\nbody\n')
  })
})
