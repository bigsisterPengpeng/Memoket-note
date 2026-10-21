import { describe, expect, it } from 'vitest'
import { setLang } from '../../i18n'
setLang('zh')   // these assertions check the Chinese UI text

import { appColors, bandCells, describable, hhmm, sayNoDesc, saySpan, stepDay } from '../../components/JourneyPage'

const seg = (start: string, end: string, app = 'Code') =>
  ({ i: 0, start, end, app, title: '', desc: '', n: 1, has_frame: true, has_thumb: false })

describe('the screen activity band', () => {
  it('the same app has the same color across the page; order of appearance decides its slot', () => {
    const c = appColors(['Code', 'Chrome', 'Code', 'Finder'])
    expect(c.get('Code')).toBe('var(--jn-1)')
    expect(c.get('Chrome')).toBe('var(--jn-2)')
    expect(c.get('Finder')).toBe('var(--jn-3)')
  })

  it('from the 9th app on they go into "other", not wrapping back to the first slot -- wrapping would give two apps the same color', () => {
    const c = appColors(Array.from({ length: 10 }, (_, i) => `App${i}`))
    expect(c.get('App7')).toBe('var(--jn-8)')
    expect(c.get('App8')).toBe('var(--jn-other)')
    expect(c.get('App9')).toBe('var(--jn-other)')
  })

  it('a gap of 15 minutes or more inserts a blank slot; short gaps do not', () => {
    const cells = bandCells([
      seg('2026-09-14T01:00:00Z', '2026-09-14T02:00:00Z'),
      seg('2026-09-14T02:05:00Z', '2026-09-14T02:30:00Z'),   // only 5 minutes apart
      seg('2026-09-14T06:00:00Z', '2026-09-14T07:00:00Z'),   // 3.5 hours apart
    ])
    expect(cells.filter((c) => c.gap)).toHaveLength(1)
    expect(cells).toHaveLength(4)
  })

  it('long overnight gaps are capped on the band, so a whole day is not squeezed into two slivers', () => {
    const cells = bandCells([
      seg('2026-09-13T01:00:00Z', '2026-09-13T02:00:00Z'),
      seg('2026-09-14T01:00:00Z', '2026-09-14T02:00:00Z'),
    ])
    expect(cells.find((c) => c.gap)!.sec).toBe(20 * 60)
  })
})

describe('times written for people', () => {
  it('a segment that just started recording must not show as "0 minutes"', () => {
    expect(saySpan(20)).toBe('\u4e0d\u5230 1 \u5206\u949f')   // JourneyPage's wording (still Chinese until its owner converts it)
    expect(saySpan(0)).toBe('\u4e0d\u5230 1 \u5206\u949f')
  })

  it('a whole hour does not drag a "0 minutes" tail', () => {
    expect(saySpan(3600)).toBe('1 \u5c0f\u65f6')
    expect(saySpan(3600 + 12 * 60)).toBe('1 \u5c0f\u65f6 12 \u5206\u949f')
  })

  it('the shell writes UTC, and it must print local time -- a timeline off by one time zone is as good as none', () => {
    // slicing the string directly would print "01:12"; local time is the clock time the user actually saw
    expect(hhmm('2026-09-14T01:12:00Z')).toBe(
      new Date('2026-09-14T01:12:00Z').toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }))
  })
})

describe('flipping days', () => {
  // newest first, consistent with backend /days
  const days = ['2026-09-14', '2026-09-11', '2026-09-04']

  it('flipping back skips the days in between that have no records', () => {
    // **adding or subtracting one day walks into a run of empty days**: ill for a week, on a trip without the computer, seven flips to reach the previous record
    expect(stepDay(days, '', -1)).toBe('2026-09-11')
    expect(stepDay(days, '2026-09-11', -1)).toBe('2026-09-04')
  })

  it('flipping back to the latest day restores the empty string -- the date is left to the backend, so a page left open past midnight is not pinned', () => {
    expect(stepDay(days, '2026-09-11', 1)).toBe('')
  })

  it('flipping to the end returns null (button greyed out), not staying in place', () => {
    expect(stepDay(days, '2026-09-04', -1)).toBeNull()
    expect(stepDay(days, '', 1)).toBeNull()
  })

  // -- today is not among "days with records" (P52) ------------------------
  // after not opening for a few days, or with today's segments deleted one by one, today is **not** in /days,
  // while the old implementation hard-wired "today" as `days[0]`. Screenshot (`$S/p52/stepday_probe.mjs`):
  // from today "previous record" -> 09-18 (skipping 09-19), from 09-18 "next record" -> today (skipping 09-19 again)
  // -- **the most recently recorded day was unreachable in both directions**.
  describe('today has not a single record', () => {
    const d2 = ['2026-09-19', '2026-09-18']
    const today = '2026-09-20'

    it('flipping back from today lands on the most recently recorded day without skipping it', () => {
      expect(stepDay(d2, '', -1, today)).toBe('2026-09-19')
    })

    it('flipping forward from the earliest day comes back to the most recently recorded day, not jumping straight to today', () => {
      expect(stepDay(d2, '2026-09-18', 1, today)).toBe('2026-09-19')
    })

    it('the most recently recorded day is already the end for "next record" -- greyed out', () => {
      expect(stepDay(d2, '2026-09-19', 1, today)).toBeNull()
    })

    it('when today has records not a word changed: flipping back to today is still the empty string', () => {
      const d3 = ['2026-09-20', '2026-09-19']
      expect(stepDay(d3, '2026-09-19', 1, '2026-09-20')).toBe('')
      expect(stepDay(d3, '', -1, '2026-09-20')).toBe('2026-09-19')
      expect(stepDay(d3, '', 1, '2026-09-20')).toBeNull()
    })

    it('without today the behavior is word for word as before -- old callers must not be changed', () => {
      expect(stepDay(d2, '', -1)).toBe('2026-09-18')      // the old behavior (which is exactly this bug)
      expect(stepDay(d2, '2026-09-18', 1)).toBe('')
    })
  })

  it('with no records on any day, neither direction can flip', () => {
    expect(stepDay([], '', -1)).toBeNull()
  })
})

describe('segments whose descriptions can still be filled in', () => {
  it('ones without screenshots do not count -- clicking "Describe" any number of times leaves them undescribed (on 09-17, 71 segments had no screenshots and the button stayed lit)', () => {
    expect(describable([
      { desc: '', has_frame: true },        // really waiting to be described
      { desc: '', has_frame: false },       // blocked by the blacklist / failed to save / expired after three days: cannot be filled in
      { desc: 'editing capture.ts', has_frame: false },
    ])).toBe(1)
  })

  // -- P50 (round 793): that dead end came back through another door ----------
  //
  // real data screenshot: on 09-16 **37 segments** and on 09-17 **71 segments** had `skip` "no screenshot",
  // while `frames` still held a path that had long ceased to exist -> `has_frame` was still true.
  // Looking only at `has_frame`, these segments were all counted into "Describe these N segments", and clicking returned only
  // "nothing left to describe", **however many clicks**.
  it('ones the backend already ruled out (skip) do not count, even if has_frame still claims the image exists', () => {
    expect(describable([
      { desc: '', has_frame: true },                              // really waiting to be described
      { desc: '', has_frame: true, skip: '\u6ca1\u6709\u622a\u56fe' },              // <- the dangling-path kind (backend skip reasons are Chinese data)
      { desc: '', has_frame: true, skip: '\u622a\u56fe\u5df2\u8fc7\u671f' },
    ])).toBe(1)
  })

  it('an empty skip = not its turn yet, still counted (a false alarm is worse than a miss)', () => {
    expect(describable([{ desc: '', has_frame: true, skip: '' }])).toBe(1)
  })
})

describe('what a row without a description says', () => {
  it('with the image still there it says "not described yet" -- a promise that "it will come if you wait"', () => {
    expect(sayNoDesc({ has_frame: true })).toBe('\u8fd8\u6ca1\u63cf\u8ff0')
  })
  it('with the image gone it says so on the spot, rather than keeping people waiting', () => {
    expect(sayNoDesc({ has_frame: false })).toBe('\u6ca1\u622a\u56fe\uff0c\u8865\u4e0d\u4e86\u63cf\u8ff0')
  })
  it('when the backend can give a reason, use its own words', () => {
    expect(sayNoDesc({ has_frame: true, skip: '\u622a\u56fe\u5df2\u8fc7\u671f' })).toBe('\u622a\u56fe\u5df2\u8fc7\u671f\uff0c\u8865\u4e0d\u4e86\u63cf\u8ff0')
    expect(sayNoDesc({ has_frame: false, skip: '\u6ca1\u6709\u622a\u56fe' })).toBe('\u6ca1\u6709\u622a\u56fe\uff0c\u8865\u4e0d\u4e86\u63cf\u8ff0')
  })
})
