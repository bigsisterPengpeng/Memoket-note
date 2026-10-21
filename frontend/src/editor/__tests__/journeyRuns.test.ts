import { describe, expect, it } from 'vitest'

import { groupRuns, RUN_SIM, similar } from '../../util/journeyRuns'

/** Segments on the timeline that "keep talking about the same thing" merge into one block -- the threshold was measured on **real output**
 *  (round 752): adjacent pairs that really were the same thing scored .60 / .58 / .52 / .40 / .32,
 *  real topic changes .07 / .06. The threshold .45 leans high; false merges cost more than misses. */

const at = (m: number) => new Date(Date.parse('2026-09-17T07:00:00Z') + m * 60_000).toISOString()
const seg = (m0: number, m1: number, app: string, desc: string) =>
  ({ start: at(m0), end: at(m1), app, desc })

describe('similar', () => {
  it('two phrasings of the same thing score high, two different things score low', () => {
    const a = '\u67e5\u770b\u300c\u67e5\u770bFirebase\u7528\u6237\u884c\u4e3a\u6570\u636e\u300d\u6807\u7b7e\u9875\u4e2d PRD.md#70-81 \u7684\u65e5\u672c Android \u5d29\u6e83\u5206\u6790'   // real CJK screen-activity descriptions (bigram similarity is CJK-sensitive)
    const b = '\u9605\u8bfb \u67e5\u770bFirebase\u7528\u6237\u884c\u4e3a\u6570\u636e \u9875\u7b7e\u4e2d PRD.md#70-81 \u7684\u65e5\u672c Android \u5d29\u6e83\u5206\u6790\u7ed3\u8bba'
    const c = '\u6539\u9700\u6c42\u6587\u6863\u4e2d [\u9879\u76ee\u540d\u79f0] \u7684 #1.\u80cc\u666f\u4e0e\u95ee\u9898 \u6a21\u677f\u5e76\u67e5\u770b\u53f3\u4fa7\u8bb0\u5fc6\u5361\u7247'
    expect(similar(a, b)).toBeGreaterThan(RUN_SIM)
    expect(similar(a, c)).toBeLessThan(0.15)
  })

  it('empty strings get no score, so two empty descriptions are not merged by similar', () => {
    expect(similar('', 'something')).toBe(0)
  })
})

describe('groupRuns', () => {
  it('consecutive segments about the same thing merge into one block spanning first to last', () => {
    const runs = groupRuns([
      seg(0, 5, 'Code', '\u67e5\u770b PRD.md#70-81 \u7684\u65e5\u672c Android \u5d29\u6e83\u5206\u6790'),
      seg(5, 11, 'Code', '\u9605\u8bfb PRD.md#70-81 \u7684\u65e5\u672c Android \u5d29\u6e83\u5206\u6790\u7ed3\u8bba'),
      seg(11, 20, 'Code', '\u67e5\u770b PRD.md#70-81 \u7684\u65e5\u672c Android \u5d29\u6e83\u4fe1\u606f'),
    ])
    expect(runs).toHaveLength(1)
    expect(runs[0].segs).toHaveLength(3)
    expect(runs[0].start).toBe(at(0))
    expect(runs[0].end).toBe(at(20))
  })

  it('a change of topic breaks the block', () => {
    const runs = groupRuns([
      seg(0, 5, 'Code', '\u67e5\u770b PRD.md#70-81 \u7684\u65e5\u672c Android \u5d29\u6e83\u5206\u6790'),
      seg(5, 9, 'Code', '\u6539\u9700\u6c42\u6587\u6863\u4e2d [\u9879\u76ee\u540d\u79f0] \u7684\u80cc\u666f\u4e0e\u95ee\u9898\u6a21\u677f'),
    ])
    expect(runs).toHaveLength(2)
  })

  it('a change of app breaks it, even if the descriptions are alike', () => {
    const d = '\u67e5\u770b PRD.md#70-81 \u7684\u65e5\u672c Android \u5d29\u6e83\u5206\u6790'
    expect(groupRuns([seg(0, 5, 'Code', d), seg(5, 9, 'Safari', d)])).toHaveLength(2)
  })

  it('a long gap in between does not merge -- the blank stretch itself is information', () => {
    const d = '\u67e5\u770b PRD.md#70-81 \u7684\u65e5\u672c Android \u5d29\u6e83\u5206\u6790'
    expect(groupRuns([seg(0, 5, 'Code', d), seg(120, 125, 'Code', d)])).toHaveLength(2)
  })

  it('compare with the block\'s first entry, not the previous one: chaining one by one drifts', () => {
    // b is like a, c is like b, but c and a are already two different things. Comparing "with the previous one" would merge all three.
    const a = '\u67e5\u770b PRD.md \u7684\u65e5\u672c Android \u5d29\u6e83\u5206\u6790'
    const b = '\u67e5\u770b PRD.md \u7684\u65e5\u672c Android \u5d29\u6e83\u5206\u6790\uff0c\u6253\u5f00 Crashlytics \u6309\u673a\u578b\u7b5b\u9009\u5bfc\u51fa CSV'
    const c = '\u6253\u5f00 Crashlytics \u6309\u673a\u578b\u7b5b\u9009\u5bfc\u51fa CSV \u5e76\u5199\u8fdb\u5468\u62a5'
    expect(similar(a, b)).toBeGreaterThan(RUN_SIM)
    expect(similar(b, c)).toBeGreaterThan(RUN_SIM)
    expect(similar(a, c)).toBeLessThan(RUN_SIM)
    const runs = groupRuns([seg(0, 5, 'Code', a), seg(5, 9, 'Code', b), seg(9, 14, 'Code', c)])
    expect(runs).toHaveLength(2)
    expect(runs[0].segs).toHaveLength(2)
  })

  it('both without descriptions yet: merge -- the two rows look identical', () => {
    const runs = groupRuns([seg(0, 5, 'Code', ''), seg(5, 9, 'Code', ''), seg(9, 14, 'Code', '')])
    expect(runs).toHaveLength(1)
  })

  it('one described and one not: no merge -- the undescribed one is still waiting', () => {
    const runs = groupRuns([seg(0, 5, 'Code', '\u67e5\u770b PRD.md \u7684\u5d29\u6e83\u5206\u6790'), seg(5, 9, 'Code', '')])
    expect(runs).toHaveLength(2)
  })

  it('the block shows the sentence with the most information', () => {
    const runs = groupRuns([
      seg(0, 5, 'Code', '\u67e5\u770b PRD.md \u7684\u5d29\u6e83\u5206\u6790'),
      seg(5, 9, 'Code', '\u67e5\u770b PRD.md#70-81 \u7684\u5d29\u6e83\u5206\u6790\uff0cCrashlytics \u5339\u914d\u5230 4 \u6761'),
    ])
    expect(runs[0].desc).toContain('Crashlytics')
  })

  it('an empty array does not blow up', () => {
    expect(groupRuns([])).toEqual([])
  })
})
