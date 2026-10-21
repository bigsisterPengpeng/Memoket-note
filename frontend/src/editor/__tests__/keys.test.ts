import { describe, expect, it } from 'vitest'

import { fmtShortcut } from '../../util/keys'

/**
 * mac's modifier order is ⌃⌥⇧⌘ (Command last), Windows' is Ctrl+Alt+Shift
 * (Ctrl first) -- **the two orders are reversed**. It used to replace character by character,
 * so `⇧⌘K` became `Shift+Ctrl+K` literally, which looked odd to Windows users (round 706).
 */
describe('shortcuts translated to Windows spelling', () => {
  it('returned as-is on mac', () => {
    expect(fmtShortcut('⇧⌘K', true)).toBe('⇧⌘K')
  })

  it('modifiers must be reordered, not translated literally', () => {
    expect(fmtShortcut('⇧⌘K', false)).toBe('Ctrl+Shift+K')
    expect(fmtShortcut('⌥⌘1', false)).toBe('Ctrl+Alt+1')
    // **This deliberately overturns the previous version**: it used to assert `Shift+Ctrl+T` (the literal result).
    expect(fmtShortcut('⇧⌘T', false)).toBe('Ctrl+Shift+T')
  })

  it('a modifier is not always followed by a key name; it may be a word like "click"', () => {
    expect(fmtShortcut('⌥click', false)).toBe('Alt+click')
  })

  it('several chords in one line, each translated on its own', () => {
    expect(fmtShortcut('⌘B / ⌘I / ⇧⌘K', false)).toBe('Ctrl+B / Ctrl+I / Ctrl+Shift+K')
    expect(fmtShortcut('⌘1 … ⌘9', false)).toBe('Ctrl+1 … Ctrl+9')
  })

  it('⌃ is Ctrl too', () => {
    expect(fmtShortcut('⌃⇧Tab', false)).toBe('Ctrl+Shift+Tab')
  })

  it('unmodified ones stay as they are', () => {
    expect(fmtShortcut('F2', false)).toBe('F2')
    expect(fmtShortcut('[[', false)).toBe('[[')
  })

  it('⌫ / ↩ become words', () => {
    expect(fmtShortcut('⌫', false)).toBe('Del')
    expect(fmtShortcut('⇧↩', false)).toBe('Shift+Enter')
  })
})
