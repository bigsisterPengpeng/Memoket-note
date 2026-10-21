import { describe, expect, it } from 'vitest'

import { splitSkillName } from '../../util/skillName'

describe('splitting the attribution off skill names', () => {
  it('the built-in batch: parentheses pulled out, the remaining head short enough not to be truncated', () => {
    for (const [raw, head, note] of [
      ['\u751f\u6210\u524d\u786e\u8ba4\u8303\u56f4\uff08\u53d7 brainstorming \u542f\u53d1\uff09', '\u751f\u6210\u524d\u786e\u8ba4\u8303\u56f4', '\u53d7 brainstorming \u542f\u53d1'],   // CJK built-in names with full-width parentheses
      ['\u5b81\u7f3a\u6bcb\u6ee5\uff08\u53d7 discernment-nudge \u7684\u514b\u5236\u542f\u53d1\uff09', '\u5b81\u7f3a\u6bcb\u6ee5', '\u53d7 discernment-nudge \u7684\u514b\u5236\u542f\u53d1'],
      ['\u5148\u60f3\u8bfb\u8005\u4f1a\u8ffd\u95ee\u4ec0\u4e48\uff08\u53d7 doc-coauthoring \u7684\u8bed\u5883\u6536\u96c6\u542f\u53d1\uff09', '\u5148\u60f3\u8bfb\u8005\u4f1a\u8ffd\u95ee\u4ec0\u4e48', '\u53d7 doc-coauthoring \u7684\u8bed\u5883\u6536\u96c6\u542f\u53d1'],
    ] as const) {
      expect(splitSkillName(raw)).toEqual({ head, note })
      expect(head.length).toBeLessThanOrEqual(12)      // fits on the card line
    }
  })

  it('names without parentheses are left untouched', () => {
    expect(splitSkillName('My writing habits')).toEqual({ head: 'My writing habits', note: '' })
    expect(splitSkillName('Verify trigger/skip rules')).toEqual({ head: 'Verify trigger/skip rules', note: '' })
  })

  it('only the trailing pair is taken; parentheses in the middle of a name stay', () => {
    expect(splitSkillName('\u5f15\u7528\uff08\u542b\u811a\u6ce8\uff09\u7684\u5199\u6cd5\u7ea6\u5b9a')).toEqual({ head: '\u5f15\u7528\uff08\u542b\u811a\u6ce8\uff09\u7684\u5199\u6cd5\u7ea6\u5b9a', note: '' })   // full-width parentheses mid-name
  })

  it('ASCII parentheses and empty parentheses', () => {
    expect(splitSkillName('Tone (Anthropic style)')).toEqual({ head: 'Tone', note: 'Anthropic style' })
    expect(splitSkillName('\u5947\u602a\u7684\u540d\u5b57\uff08\uff09')).toEqual({ head: '\u5947\u602a\u7684\u540d\u5b57\uff08\uff09', note: '' })   // empty full-width parentheses
  })
})
