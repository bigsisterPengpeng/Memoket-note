import { describe, expect, it } from 'vitest'
import { MIN_LEFT_W, layoutPanes, makeRoomForRight } from '../../util/layoutPanes'

/** User screenshot: "the right sidebar won't open?" -- `rightOn` was already true; the passive layout rule
 *  (collapse the right pane when the middle has less than 520) overrode it, so clicking the button did nothing.
 *  An explicit action should win. */
const shown = (p: ReturnType<typeof makeRoomForRight>, winW: number) =>
  layoutPanes({ winW, panes: p, splitW: null, focusMode: false }).rightShown

describe('explicitly opening the right pane', () => {
  it('already wide enough: nothing changes', () => {
    const p = { leftW: 260, rightW: 340, leftOn: true, rightOn: false }
    const next = makeRoomForRight(p, 1440)
    expect(next).toEqual({ ...p, rightOn: true })
    expect(shown(next, 1440)).toBe(true)
  })

  it('not wide enough: narrow the left pane just enough to fit, rather than silently not opening', () => {
    // the tier from the screenshot: left pane 289, window 1200 -> 1200-80-289-340 = 491 < 520
    const p = { leftW: 289, rightW: 340, leftOn: true, rightOn: true }
    expect(shown(p, 1200)).toBe(false)          // before the change: clicking still could not open it
    const next = makeRoomForRight(p, 1200)
    expect(shown(next, 1200)).toBe(true)
    expect(next.leftOn).toBe(true)
    expect(next.leftW).toBeLessThan(289)
  })

  it('left pane already at its minimum and still no room: collapse the left pane rather than give up the right', () => {
    const p = { leftW: 300, rightW: 340, leftOn: true, rightOn: false }
    const next = makeRoomForRight(p, 900)
    expect(next.rightOn).toBe(true)
    expect(next.leftOn).toBe(false)
    expect(shown(next, 900)).toBe(true)
  })

  it('the freed left pane is never narrower than the minimum', () => {
    for (const winW of [900, 1000, 1100, 1200, 1366]) {
      const next = makeRoomForRight({ leftW: 400, rightW: 340, leftOn: true, rightOn: false }, winW)
      if (next.leftOn) expect(next.leftW).toBeGreaterThanOrEqual(MIN_LEFT_W)
      expect(shown(next, winW)).toBe(true)
    }
  })

  it('left pane already collapsed: only open the right pane, leave it alone', () => {
    const p = { leftW: 400, rightW: 340, leftOn: false, rightOn: false }
    expect(makeRoomForRight(p, 900)).toEqual({ ...p, rightOn: true })
  })
})
