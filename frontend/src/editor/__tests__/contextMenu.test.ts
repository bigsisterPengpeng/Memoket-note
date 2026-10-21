import { describe, expect, it } from 'vitest'

import { selectableItem, tidyMenu, type MenuItem } from '../../components/ContextMenu'

/**
 * The "which item can be clicked now" check in the context menu used to be written twice
 * (assembled with `as any`), and the Enter path **asked first** before calling `onSelect` --
 * relying on call sites remembering to ask. Collapsed into one type predicate, the compiler watches it (round 709).
 */
describe('context menu: which items can be clicked', () => {
  const sep: MenuItem = { kind: 'sep' }
  const head: MenuItem = { kind: 'header', label: 'This passage' }
  const act: MenuItem = { label: 'Delete', onSelect: () => {} }
  const off: MenuItem = { label: 'Polish', disabled: true, onSelect: () => {} }

  it('separators, headers and disabled items cannot be clicked', () => {
    expect(selectableItem(sep)).toBe(false)
    expect(selectableItem(head)).toBe(false)
    expect(selectableItem(off)).toBe(false)
    expect(selectableItem(undefined)).toBe(false)
  })

  it('ordinary items can be clicked', () => {
    expect(selectableItem(act)).toBe(true)
  })
})

describe('context menu: separators tidied up', () => {
  it('consecutive separators merge into one', () => {
    const out = tidyMenu([{ label: 'a', onSelect: () => {} }, { kind: 'sep' }, { kind: 'sep' },
                          { label: 'b', onSelect: () => {} }])
    expect(out.filter((i) => i.kind === 'sep')).toHaveLength(1)
  })

  it('leading and trailing separators are removed', () => {
    const out = tidyMenu([{ kind: 'sep' }, { label: 'a', onSelect: () => {} }, { kind: 'sep' }])
    expect(out).toHaveLength(1)
  })

  it('all separators clears everything (no lone line left)', () => {
    expect(tidyMenu([{ kind: 'sep' }, { kind: 'sep' }])).toHaveLength(0)
  })
})
