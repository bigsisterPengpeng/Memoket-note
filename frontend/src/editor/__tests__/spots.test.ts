// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { loadSpots, putSpot, saveSpots } from '../../util/spots'

describe('spots (where each note was being read)', () => {
  beforeEach(() => localStorage.clear())

  it('read back what was stored, separated by user', () => {
    const m = new Map()
    putSpot(m, 'a', { head: 10, top: 200 })
    saveSpots('u1', m)
    expect(loadSpots('u1').get('a')).toEqual({ head: 10, top: 200 })
    expect(loadSpots('u2').size).toBe(0)
  })

  it('keeps only the latest 60 notes, dropping from the oldest', () => {
    const m = new Map()
    for (let i = 0; i < 70; i++) putSpot(m, 'n' + i, { head: i, top: 0 })
    saveSpots('u1', m)
    const back = loadSpots('u1')
    expect(back.size).toBe(60)
    expect(back.has('n0')).toBe(false)
    expect(back.has('n69')).toBe(true)
  })

  it('remembering again moves it to the end, so it is not dropped as the oldest', () => {
    const m = new Map()
    for (let i = 0; i < 60; i++) putSpot(m, 'n' + i, { head: i, top: 0 })
    putSpot(m, 'n0', { head: 999, top: 0 })      // looked at the oldest note again
    for (let i = 60; i < 65; i++) putSpot(m, 'n' + i, { head: i, top: 0 })
    saveSpots('u1', m)
    const back = loadSpots('u1')
    expect(back.get('n0')).toEqual({ head: 999, top: 0 })
    expect(back.has('n1')).toBe(false)           // this is now the oldest
  })

  it('corrupt / never stored both count as none', () => {
    localStorage.setItem('memoket-note-spots:u1', '{bad json')
    expect(loadSpots('u1').size).toBe(0)
    localStorage.setItem('memoket-note-spots:u1', '{"a":null,"b":{"head":3,"top":0}}')
    expect([...loadSpots('u1').keys()]).toEqual(['b'])
  })
})
