import { describe, expect, it } from 'vitest'
import { dupSuffixes } from '../../util/dupTitles'

const row = (key: string, title: string, at = '') => ({ key, title, at })

describe('rows whose titles collide in the tree', () => {
  it('only rows that really collide get a suffix', () => {
    const d = dupSuffixes([
      row('a', 'Startup year in review', '2026-09-07T06:09:14+00:00'),
      row('b', 'Startup reflections', '2026-09-02T04:44:18+00:00'),
      row('c', 'Startup year in review', '2026-09-10T10:22:53+00:00'),
    ])
    expect([...d.keys()].sort()).toEqual(['a', 'c'])
    expect(d.get('a')).toBe('09-07')
  })

  it('two written on the same day go down to the minute -- a date alone does not separate them', () => {
    const d = dupSuffixes([
      row('a', 'Startup year in review', '2026-09-07T06:09:14+00:00'),
      row('b', 'Startup year in review', '2026-09-07T12:58:28+00:00'),
    ])
    expect(d.get('a')).toBe('09-07 06:09')
    expect(d.get('b')).toBe('09-07 12:58')
  })

  it('not separable even by minute: no mark, marking would not help', () => {
    const same = '2026-09-07T06:09:14+00:00'
    expect(dupSuffixes([row('a', 'X', same), row('b', 'X', same)]).size).toBe(0)
  })

  it('empty titles do not count as collisions -- a column of "Untitled" should not all get dates', () => {
    expect(dupSuffixes([row('a', '', '2026-09-07T06:09:14+00:00'),
                        row('b', '  ', '2026-09-08T06:09:14+00:00')]).size).toBe(0)
  })

  it('all different: none marked', () => {
    expect(dupSuffixes([row('a', 'A', '2026-09-07T00:00:00+00:00'),
                        row('b', 'B', '2026-09-08T00:00:00+00:00')]).size).toBe(0)
  })

  it('surrounding whitespace counts as the same name', () => {
    const d = dupSuffixes([row('a', 'Startup ', '2026-09-07T00:00:00+00:00'),
                           row('b', ' Startup', '2026-09-08T00:00:00+00:00')])
    expect(d.size).toBe(2)
  })
})
