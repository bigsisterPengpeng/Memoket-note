import { afterEach, describe, expect, it } from 'vitest'
import { getLang, hasZh, setLang, t } from '../index'

describe('UI language', () => {
  afterEach(() => setLang('en'))

  it('defaults to English; t() returns the source text', () => {
    expect(getLang()).toBe('en')
    expect(t('Untitled')).toBe('Untitled')
  })

  it('Chinese mode looks the key up; a missing key falls back to English', () => {
    setLang('zh')
    expect(t('Untitled')).toBe('\u672a\u547d\u540d')
    expect(hasZh('Surely never translated')).toBe(false)
    expect(t('Surely never translated')).toBe('Surely never translated')
  })

  it('{placeholders} are filled in both languages; a missing param stays literal', () => {
    expect(t('Imported {n} notes', { n: 3 })).toBe('Imported 3 notes')
    expect(t('Imported {n} notes')).toBe('Imported {n} notes')
  })
})
