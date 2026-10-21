/**
 * A round's diff and the hunks cut from it.
 *
 * These were the frontend's **first batch** of tests. Starting here was not because it is easiest, but because it matters most:
 * when the user clicks "Accept" and "Revert" on the panel, what they act on is exactly what toHunks() computed.
 * Get one hunk's `del` wrong and revert restores the wrong text -- while on screen everything
 * looks fine.
 *
 * These two functions are pure (they only use types from @codemirror/state, no DOM), so
 * no jsdom is needed.
 */
import { describe, expect, it } from 'vitest'

import { diffParts, toHunks } from '../roundDiff'

describe('diffParts', () => {
  it('with no change the whole thing is keep', () => {
    expect(diffParts('the same text', 'the same text'))
      .toEqual([{ type: 'keep', text: 'the same text' }])
  })

  it('CJK is split per character, marking only the character that really changed', () => {
    // splitting by whole sentence would mark a whole passage red and green for one changed character, hiding what moved
    const parts = diffParts('\u56db\u6708\u4e2d\u65ec\u4ea4\u4ed8', '\u4e09\u6708\u4e2d\u65ec\u4ea4\u4ed8')   // "deliver mid-April" -> "deliver mid-March" in CJK
    expect(parts.filter((p) => p.type === 'del').map((p) => p.text)).toEqual(['\u56db'])
    expect(parts.filter((p) => p.type === 'ins').map((p) => p.text)).toEqual(['\u4e09'])
    expect(parts.map((p) => p.text).join('')).toContain('\u6708\u4e2d\u65ec\u4ea4\u4ed8')
  })

  it('English is split by word', () => {
    const parts = diffParts('ship in April', 'ship in March')
    expect(parts.find((p) => p.type === 'del')?.text).toBe('April')
    expect(parts.find((p) => p.type === 'ins')?.text).toBe('March')
  })

  it('for a pure insertion not a single old character should be marked as deleted', () => {
    const parts = diffParts('\u539f\u6765\u7684\u8bdd\u3002', '\u539f\u6765\u7684\u8bdd\u3002\u53c8\u52a0\u4e86\u4e00\u53e5\u3002')
    expect(parts.some((p) => p.type === 'del')).toBe(false)
    expect(parts.find((p) => p.type === 'ins')?.text).toBe('\u53c8\u52a0\u4e86\u4e00\u53e5\u3002')
  })

  it('when the change is too large, the whole passage is marked delete+insert rather than compared word by word', () => {
    // in a real scenario this means the round rewrote almost the whole note; a word-by-word comparison has no reading value
    // and would freeze the UI
    const before = '\u7532'.repeat(700)
    const after = '\u4e59'.repeat(700)
    const parts = diffParts(before, after)
    expect(parts).toEqual([{ type: 'del', text: before },
                           { type: 'ins', text: after }])
  })

  it('joining back must restore both sides', () => {
    const before = '\u7b2c\u4e00\u6279 200 \u53f0\u673a\u5668\u53d1\u51fa\u53bb\u4e24\u5468\uff0c\u9000\u8d27\u7387 6%\u3002'
    const after = '\u7b2c\u4e00\u6279 200 \u53f0\u673a\u5668\u53d1\u51fa\u53bb\u4e09\u5468\uff0c\u9000\u8d27\u7387 8%\u3002'
    const parts = diffParts(before, after)
    const old = parts.filter((p) => p.type !== 'ins').map((p) => p.text).join('')
    const now = parts.filter((p) => p.type !== 'del').map((p) => p.text).join('')
    expect(old).toBe(before)
    expect(now).toBe(after)
  })
})

describe('toHunks', () => {
  it('no change, no hunk', () => {
    expect(toHunks(null)).toEqual([])
    expect(toHunks([{ type: 'keep', text: 'unchanged' }])).toEqual([])
  })

  it('an adjacent delete+insert merge into one change, because that is one replacement', () => {
    // split in two, clicking accept would leave half a strikethrough hanging there
    const hunks = toHunks(diffParts('\u4ea4\u4ed8\u5728\u56db\u6708', '\u4ea4\u4ed8\u5728\u4e09\u6708'))
    expect(hunks).toHaveLength(1)
    expect(hunks[0].del).toBe('\u56db')
  })

  it('two nearby changes merge, and del carries the untouched characters in between', () => {
    // the cost of per-character CJK diff: "mid-April" -> "early March" splits into two changes each covering one
    // character, too fine-grained for hover. After merging, del must carry the part in between so revert restores exactly.
    const hunks = toHunks(diffParts('\u56db\u6708\u4e2d\u65ec', '\u4e09\u6708\u4e0a\u65ec'))
    expect(hunks).toHaveLength(1)
    expect(hunks[0].del).toBe('\u56db\u6708\u4e2d')
  })

  it('two changes far apart are not merged', () => {
    const before = '\u5f00\u5934\u6539\u8fd9\u91cc\u3002' + '\u4e2d\u95f4\u9694\u7740\u5f88\u957f\u4e00\u6bb5\u5b8c\u5168\u6ca1\u6709\u52a8\u8fc7\u7684\u6587\u5b57\u3002'.repeat(3) + '\u7ed3\u5c3e\u4e5f\u6539\u3002'
    const after = '\u5f00\u5934\u6539\u90a3\u91cc\u3002' + '\u4e2d\u95f4\u9694\u7740\u5f88\u957f\u4e00\u6bb5\u5b8c\u5168\u6ca1\u6709\u52a8\u8fc7\u7684\u6587\u5b57\u3002'.repeat(3) + '\u7ed3\u5c3e\u4e5f\u53d8\u3002'
    expect(toHunks(diffParts(before, after)).length).toBeGreaterThan(1)
  })

  it('each hunk\'s range falls on the new text, and ids are unique', () => {
    const after = '\u4ea4\u4ed8\u5728\u4e09\u6708\uff0c\u4ef7\u683c\u6539\u6210 199\u3002'
    const hunks = toHunks(diffParts('\u4ea4\u4ed8\u5728\u56db\u6708\uff0c\u4ef7\u683c\u6539\u6210 179\u3002', after))
    expect(new Set(hunks.map((h) => h.id)).size).toBe(hunks.length)
    for (const h of hunks) {
      expect(h.from).toBeGreaterThanOrEqual(0)
      expect(h.to).toBeLessThanOrEqual(after.length)
      expect(h.from).toBeLessThanOrEqual(h.to)
    }
  })
})

import { diffParts as _dp, toHunks as _th } from '../roundDiff'
describe('whitespace-only differences are not changes', () => {
  it('added spaces / blank lines are not marked green (the hunk is soft), but the position is recorded', () => {
    const parts = _dp('\u4e2d\u6587English\u6df7\u6392\u3002\n\u6bb5\u843d', '\u4e2d\u6587 English \u6df7\u6392\u3002\n\n\u6bb5\u843d')   // CJK/Latin spacing added by formatting
    const hunks = _th(parts)
    expect(hunks.length).toBeGreaterThan(0)
    expect(hunks.every((h) => h.soft)).toBe(true)
    const real = _th(_dp('\u7532\u4e59\u4e19', '\u7532\u4e01\u4e19'))
    expect(real.some((h) => !h.soft)).toBe(true)
  })
  it('with whitespace changes and real changes mixed, revert restores exactly (turning whitespace into keep used to shift by one)', () => {
    const before = ' b \u4e19\u4e01\u4e19\u620ab\u7532\u3002\u620a\ncb'
    const after = ' b \n\u4e59\n \u4e19\u4e01\u4e19\u620ab\u7532\u3002\u620a\nc'
    const hunks = _th(_dp(before, after))
    let s = after
    for (const h of [...hunks].sort((a, b) => b.from - a.from)) s = s.slice(0, h.from) + h.del + s.slice(h.to)
    expect(s).toBe(before)
  })
})

describe('large documents: by line, then by word', () => {
  it('eight thousand characters with only spaces added: almost no green', () => {
    const lines = Array.from({ length: 400 }, (_, i) => `\u7b2c${i}\u6bb5\uff1a\u4e2d\u6587English\u6df7\u6392\uff0c\u8ba8\u8bba\u4e86\u6392\u671f\u548c\u6837\u673a${i}\u3002`)
    const before = lines.join('\n')
    const after = lines.map((l) => l.replace('\u4e2d\u6587English\u6df7\u6392', '\u4e2d\u6587 English \u6df7\u6392')).join('\n')
    const parts = _dp(before, after)
    const changed = parts.filter((p) => p.type !== 'keep').map((p) => p.text).join('')
    expect(changed.trim()).toBe('')
  })
  it('one word really changed in eight thousand characters: only that word is marked', () => {
    const lines = Array.from({ length: 400 }, (_, i) => `\u7b2c${i}\u6bb5\uff1a\u4e2d\u6587English\u6df7\u6392\uff0c\u8ba8\u8bba\u4e86\u6392\u671f\u548c\u6837\u673a${i}\u3002`)
    const before = lines.join('\n')
    const after = lines.map((l, i) => (i === 123 ? l.replace('\u6392\u671f', '\u9884\u7b97') : l)).join('\n')
    const parts = _dp(before, after)
    expect(parts.filter((p) => p.type === 'ins').map((p) => p.text)).toEqual(['\u9884\u7b97'])
    expect(parts.filter((p) => p.type === 'del').map((p) => p.text)).toEqual(['\u6392\u671f'])
  })
})

describe('very long notes aligned by line (anchors)', () => {
  it('1500 lines, spaces added to each: not a single real change, and it must not degrade into whole delete+insert', () => {
    const paras: string[] = []
    for (let i = 0; i < 300; i++) paras.push(`## \u7b2c${i + 1}\u8282 \u91cc\u7a0b\u7891\n\n\u8fd9\u4e00\u8282\u8ba8\u8bba\u7b2c${i + 1}\u5468\u7684\u6392\u671f\u3002\n\n- \u8ba1\u5212\u65f6\u95f4\uff1a\u7b2c${i + 1}\u5468\n- \u5f53\u524d\u72b6\u6001\uff1a\u5f85\u9a8c\u8bc1\n`)
    const before = paras.join('\n')
    const after = before.replace(/\u7b2c(\d+)/g, '\u7b2c $1').replace(/(\d+)\u5468/g, '$1 \u5468').replace(/(\d+)\u8282/g, '$1 \u8282')
    const t0 = performance.now()
    const hunks = _th(_dp(before, after))
    expect(performance.now() - t0).toBeLessThan(500)
    expect(hunks.length).toBeGreaterThan(100)
    expect(hunks.every((h) => h.soft)).toBe(true)
    // revert restores everything exactly
    let s = after
    for (const h of [...hunks].sort((a, b) => b.from - a.from)) s = s.slice(0, h.from) + h.del + s.slice(h.to)
    expect(s).toBe(before)
  })
  it('one sentence really changed in 1500 lines: only that sentence is marked', () => {
    const lines = Array.from({ length: 1500 }, (_, i) => `\u7b2c${i}\u884c\uff1a\u8ba8\u8bba\u4e86\u6392\u671f\u548c\u6837\u673a${i}\u3002`)
    const before = lines.join('\n')
    const after = lines.map((l, i) => (i === 777 ? l.replace('\u6392\u671f', '\u9884\u7b97') : l)).join('\n')
    const hunks = _th(_dp(before, after)).filter((h) => !h.soft)
    expect(hunks.length).toBe(1)
    expect(hunks[0].del).toBe('\u6392\u671f')
  })
})
