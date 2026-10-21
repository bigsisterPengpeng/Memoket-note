import { describe, expect, it } from 'vitest'
import { minimalChange } from '../minimalChange'

function apply(s: string, c: { from: number; to: number; insert: string } | null) {
  return c ? s.slice(0, c.from) + c.insert + s.slice(c.to) : s
}

describe('minimalChange', () => {
  it('appending only changes the end', () => {
    const c = minimalChange('A\n\nB', 'A\n\nBC')
    expect(c).toEqual({ from: 4, to: 4, insert: 'C' })
  })
  it('inserting in the middle only changes the middle', () => {
    const c = minimalChange('A\n\nC', 'A\n\nB\n\nC')!
    expect(c.from).toBe(3)
    expect(apply('A\n\nC', c)).toBe('A\n\nB\n\nC')
  })
  it('replace / delete / identical', () => {
    expect(apply('abcXYZdef', minimalChange('abcXYZdef', 'abc12def'))).toBe('abc12def')
    expect(apply('abcXYZdef', minimalChange('abcXYZdef', 'abcdef'))).toBe('abcdef')
    expect(minimalChange('same', 'same')).toBeNull()
  })
  it('does not split an emoji surrogate pair', () => {
    const old = 'a😀b'; const next = 'a😁b'
    const c = minimalChange(old, next)!
    expect(apply(old, c)).toBe(next)
    expect(c.from).toBe(1)
  })
})
