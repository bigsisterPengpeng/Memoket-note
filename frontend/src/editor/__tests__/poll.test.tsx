// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { usePoll } from '../../util/poll'

/**
 * Every rule of this hook targets a specific waste: the screen activity page stays open all day
 * (the feature behind it is capturing screenshots continuously), and the knowledge-base browser fetches three endpoints every 3 seconds while ingesting
 * (one ingest may take over ten minutes). So **really run it**, rather than checking what the code looks like.
 */
let hidden = false
Object.defineProperty(document, 'hidden', { get: () => hidden, configurable: true })
const setHidden = (v: boolean) => {
  hidden = v
  document.dispatchEvent(new Event('visibilitychange'))
}

function mount(fn: () => void, ms = 1000, on = true) {
  const el = document.createElement('div')
  const root = createRoot(el)
  function Probe({ on: o }: { on: boolean }) { usePoll(fn, ms, o); return null }
  act(() => { root.render(<Probe on={on} />) })
  return {
    rerender: (o: boolean) => act(() => { root.render(<Probe on={o} />) }),
    unmount: () => act(() => { root.unmount() }),
  }
}

afterEach(() => { hidden = false; vi.useRealTimers() })

describe('usePoll, really running', () => {
  it('runs on its period while visible', () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    const h = mount(fn)
    act(() => { vi.advanceTimersByTime(3500) })
    expect(fn).toHaveBeenCalledTimes(3)
    h.unmount()
  })

  it('**does nothing while the window is hidden** -- the whole point', () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    const h = mount(fn)
    act(() => { setHidden(true) })
    act(() => { vi.advanceTimersByTime(10_000) })
    expect(fn).toHaveBeenCalledTimes(0)
    h.unmount()
  })

  it('**runs once immediately on returning to the foreground**, without waiting for the next period', () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    const h = mount(fn)
    act(() => { setHidden(true) })
    act(() => { vi.advanceTimersByTime(5000) })
    expect(fn).toHaveBeenCalledTimes(0)
    act(() => { setHidden(false) })
    expect(fn).toHaveBeenCalledTimes(1)      // ran as soon as it came back, without waiting the 1000ms
    h.unmount()
  })

  it('on=false stops it entirely', () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    const h = mount(fn, 1000, false)
    act(() => { vi.advanceTimersByTime(5000) })
    expect(fn).toHaveBeenCalledTimes(0)
    h.rerender(true)
    act(() => { vi.advanceTimersByTime(2500) })
    expect(fn).toHaveBeenCalledTimes(2)
    h.unmount()
  })

  it('after unmount it no longer runs and leaves no listeners', () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    const h = mount(fn)
    h.unmount()
    act(() => { vi.advanceTimersByTime(10_000); setHidden(false) })
    expect(fn).toHaveBeenCalledTimes(0)
  })

  it('passing a new closure on every render does not reset the period -- the timer is not rebuilt with the callback', () => {
    vi.useFakeTimers()
    let calls = 0
    const el = document.createElement('div')
    const root = createRoot(el)
    function Probe({ n }: { n: number }) { usePoll(() => { calls += 1; void n }, 1000); return null }
    act(() => { root.render(<Probe n={0} />) })
    for (let i = 1; i <= 9; i++) {
      act(() => { vi.advanceTimersByTime(100) })
      act(() => { root.render(<Probe n={i} />) })   // re-render every 100ms with a new closure each time
    }
    act(() => { vi.advanceTimersByTime(150) })
    expect(calls).toBe(1)                            // the period was not reset; at 1000ms there should be one call
    act(() => { root.unmount() })
  })
})
