// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import type { TrayItem } from '../../api'

const state = vi.hoisted(() => ({ items: [] as TrayItem[] }))
vi.mock('../../api', () => ({
  listTray: async () => state.items.map(item => ({ ...item })),
  putTray: async (_note: string, items: TrayItem[]) => {
    await new Promise(resolve => setTimeout(resolve, 5))
    state.items = items.map((item, index) => ({ ...item, id: `item-${index}` }))
    return state.items
  },
}))

import { appendTrayItems } from '../../util/tray'

afterEach(() => { state.items = [] })

it('preserves distinct sources when material buttons are clicked before the first save returns', async () => {
  const sources = ['obsidian-0123456789abcdef-0F1', 'obsidian-0123456789abcdef-0F2']
  await Promise.all(sources.map(ref_id => appendTrayItems('draft', [{ kind: 'fact', ref_id, excerpt: 'Fictional source.' }])))
  expect(state.items.map(item => item.ref_id)).toEqual(sources)
  expect((await appendTrayItems('draft', [{ kind: 'fact', ref_id: sources[0] }])).added).toBe(0)
  expect(state.items).toHaveLength(2)
})
