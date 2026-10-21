import { describe, expect, it } from 'vitest'
import { layoutPanes } from '../../util/layoutPanes'

const panes = { leftW: 260, rightW: 340, leftOn: true, rightOn: true }

describe('layoutPanes', () => {
  it('keeps compact windows usable even when both side panes were enabled on desktop', () => {
    for (const width of [375, 480, 639]) {
      expect(layoutPanes({ winW: width, panes, splitW: null, focusMode: false }))
        .toMatchObject({ leftShown: false, rightShown: false })
      expect(layoutPanes({ winW: width, panes: { ...panes, leftOn: false }, splitW: null, focusMode: false }).rightShown).toBe(false)
    }
  })
  it('wide window: both sides present, widths as the user set them', () => {
    expect(layoutPanes({ winW: 1440, panes, splitW: null, focusMode: false }))
      .toEqual({ leftW: 260, splitW: 0, leftShown: true, rightShown: true })
  })
  it('900x600 (screenshot: ribbon wrapped to three lines): the right pane collapses first, the left stays and is capped at 30% of the window', () => {
    const r = layoutPanes({ winW: 900, panes, splitW: null, focusMode: false })
    expect(r.rightShown).toBe(false)
    expect(r.leftShown).toBe(true)
    expect(r.leftW).toBe(260)   // 900*0.3 = 270 > 260
    expect(layoutPanes({ winW: 800, panes, splitW: null, focusMode: false }).leftW).toBe(240)
  })
  it('1000x700 with the split open (screenshot: middle pane 250px): split capped at 45%, right pane collapses, left too', () => {
    const r = layoutPanes({ winW: 1000, panes, splitW: 600, focusMode: false })
    expect(r.splitW).toBe(450)
    expect(r.rightShown).toBe(false)
    expect(r.leftShown).toBe(false)
  })
  it('when the user closed the left pane it is not counted; focus mode collapses both', () => {
    expect(layoutPanes({ winW: 900, panes: { ...panes, leftOn: false }, splitW: null, focusMode: false }))
      .toMatchObject({ leftShown: false, rightShown: true })
    expect(layoutPanes({ winW: 1440, panes, splitW: null, focusMode: true })).toMatchObject({ leftShown: false, rightShown: false })
  })
})
