import { describe, expect, it } from 'vitest'

import { NEUTRAL_ENTITY_ICON, entityIcon } from '../../util/entityIcon'

/** Screenshot (round 658): on entity pages Facebook / Canada / iphone / Russia / Apple Watch
 *  all wore `bx-user`. **An icon is an assertion**, and not one of the 1239 entities in the whole library has an etype value. */
describe('no person icon when the type is unknown', () => {
  it('unknown ones are all neutral, never claimed to be a person', () => {
    for (const n of ['Facebook', 'Canada', 'iphone', 'Russia', 'Apple Watch', 'app', 'cloud', '\u90ed\u78ca'])   // last one is a CJK personal name
      expect(entityIcon(n)).toBe(NEUTRAL_ENTITY_ICON)
  })

  it('two narrow suffix rules: low coverage, but 100% never wrong', () => {
    expect(entityIcon('\u6d69\u654f\u79d1\u6280')).toBe('bx-buildings')   // CJK company suffix "technology"
    expect(entityIcon('\u666e\u53d1\u94f6\u884c')).toBe('bx-buildings')   // CJK suffix "bank"
    expect(entityIcon('\u5317\u4eac\u5927\u5b66')).toBe('bx-book')   // CJK suffix "university"
    expect(entityIcon('\u7ef4\u591a\u5229\u4e9a\u56fd\u9645\u5b66\u6821')).toBe('bx-book')   // CJK suffix "school"
  })

  it('once the index layer really fills in etype, follow it', () => {
    expect(entityIcon('Guo Lei', 'person')).toBe('bx-user')
    expect(entityIcon('Guangzhou', 'place')).toBe('bx-map')
    expect(entityIcon('GAC Group', 'org')).toBe('bx-buildings')
    expect(entityIcon('iphone', 'product')).toBe('bx-package')
    expect(entityIcon('unclear', 'whatever')).toBe(NEUTRAL_ENTITY_ICON)
  })

  it('empty does not blow up', () => {
    expect(entityIcon('')).toBe(NEUTRAL_ENTITY_ICON)
  })
})
