import { describe, expect, it } from 'vitest'
import { fmtWhen, whenLabel } from '../../util/time'

/** When the sidebar sorts by recent, a date alone separates nothing -- three notes written on the same day would look identical.
 *  Resolution follows distance: the closer, the more the clock time matters; the farther, the more only the day matters. */
describe('"when" in a list', () => {
  const now = new Date('2026-09-14T15:00:00')
  const at = (s: string) => fmtWhen(new Date(s).toISOString(), now)

  it('today gives the clock time -- several written on the same day must be told apart', () => {
    expect(at('2026-09-14T09:05:00')).toBe('Today 09:05')
    expect(at('2026-09-14T14:32:00')).toBe('Today 14:32')
  })

  it('yesterday says yesterday, with the clock time too', () => {
    expect(at('2026-09-13T22:10:00')).toBe('Yesterday 22:10')
  })

  it('within this year month-day, only earlier years the full date', () => {
    expect(at('2026-09-07T13:29:00')).toBe('09-07')
    expect(at('2025-12-31T13:29:00')).toBe('2025-12-31')
  })

  it('"yesterday" across a month / year boundary is recognized too', () => {
    expect(fmtWhen(new Date('2025-12-31T23:00:00').toISOString(), new Date('2026-01-01T10:00:00')))
      .toBe('Yesterday 23:00')
  })

  it('empty and broken input does not blow up', () => {
    expect(fmtWhen('')).toBe('—')
    expect(fmtWhen('not a time')).toBe('not a time')
  })
})

describe('the time on colliding rows in a list', () => {
  const now = new Date('2026-09-14T20:00:00')
  it('no collision: as usual -- today gives a time of day, which must not be overridden by a date', () => {
    expect(whenLabel(undefined, '2026-09-14T09:12:00', now)).toBe(fmtWhen('2026-09-14T09:12:00', now))
  })
  it('collision but separable by day: as usual, a day-level label adds no information', () => {
    expect(whenLabel('09-07', '2026-09-07T12:50:00', now)).toBe(fmtWhen('2026-09-07T12:50:00', now))
  })
  it('collision on the same day: switch to minute level -- the only thing that separates the two rows', () => {
    expect(whenLabel('09-07 12:58', '2026-09-07T12:58:00', now)).toBe('09-07 12:58')
  })
})
