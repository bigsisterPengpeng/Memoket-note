import { describe, expect, it } from 'vitest'
import { featureLabel } from '../../components/SettingsPanel'

/** Feature names **actually recorded in a real database** (distinct `feature` in llm_usage). The middleware
 *  derives them from URL paths while the label table is maintained by hand, so the two drift — the round 612
 *  screenshot showed a bare `writing-plan/start` in the usage row. */
const RECORDED = ['note-harness/run', 'writing-plan/run', 'skeleton', 'writing-plan/start',
                  'verify', 'magic-tap', 'expand', 'digest', 'compose/block',
                  'kb/extract~', 'memory/relations']

describe('feature names in the usage block', () => {
  it('every recorded feature has a human label; no route name leaks to the user', () => {
    const raw = RECORDED.filter((k) => featureLabel(k) === k)
    expect(raw).toEqual([])
  })

  it('a new route under a known group at least reads as that group', () => {
    expect(featureLabel('writing-plan/whatever')).toBe('Endless Continue · other')
    expect(featureLabel('note-harness/pause')).toBe('Smart Continue · other')
  })

  it('an unknown group is shown verbatim — the fallback must not pretend to recognise it', () => {
    expect(featureLabel('brand-new/thing')).toBe('brand-new/thing')
  })
})
