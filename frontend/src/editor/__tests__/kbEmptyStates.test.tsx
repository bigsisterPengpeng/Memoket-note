// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { setLang } from '../../i18n'
setLang('zh')   // these assertions check the Chinese UI text

/**
 * The two pages of an empty knowledge base: the overview and the facts table.
 *
 * It started in round 673, walking every page as a brand-new user -- the empty overview's
 * "see what the facts table looks like" button led to five empty dropdowns + "0 items · no facts.".
 * **The button promised to show you, and what it showed was empty.** Now the shape is laid out on the spot.
 *
 * So these two test **what the user can see**: whether the example is there, whether the fake facts are clickable,
 * and whether the row of filters is shown on an empty library. Not what the source looks like.
 */
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api')
  return {
    ...actual,
    kbDashboard: () => Promise.resolve({
      stats: { facts: 0, topics: 0, entities: 0, units: 0, start_date: '', end_date: '' },
      kinds: [], speakers: [], topics: [], entities: [], months: [], recent: [],
    }),
    memoryFacts: () => Promise.resolve({ total: 0, facts: [], limit: 50, offset: 0 }),
    recall: () => Promise.resolve({ facts: [], terms: [], took: 0 }),
  }
})

const { default: FactsTable } = await import('../../components/kb/FactsTable')
const { ExampleFacts } = await import('../../components/kb/KbBits')

const ACTIONS = { onOpen: () => {}, onOpenNote: () => {}, onCite: null }

async function mount(node: React.ReactNode) {
  const el = document.createElement('div')
  document.body.append(el)
  const root = createRoot(el)
  await act(async () => { root.render(node) })
  await act(async () => { await Promise.resolve() })
  return { el, unmount: () => act(() => root.unmount()) }
}

afterEach(() => { document.body.innerHTML = '' })

describe('the two pages of an empty knowledge base', () => {
  it('example facts are visible real rows, but not clickable and not tabbable', async () => {
    const { el, unmount } = await mount(<ExampleFacts />)
    const rows = el.querySelectorAll('.fact-row')
    expect(rows.length).toBe(2)
    expect(el.textContent).toContain('\u793a\u4f8b')   // the kb pages' wording (still Chinese until their owner converts them)
    // a fake id would only open a 404: the whole block must be inert.
    // jsdom does not implement inert's behavior (the property reads undefined), so this asserts what the browser really
    // looks at -- whether the attribute is present. **The behavior was measured in real Chromium**: the `openclick` probe
    // called `focus()` on this row and `document.activeElement` was not it (while clickable() gave it
    // tabIndex=0, so without inert it would be focusable) -- round 673.
    const list = el.querySelector('.fact-list') as HTMLElement
    expect(list.hasAttribute('inert')).toBe(true)
    // and it must look real: date, speaker, kind and source badge are all there
    expect(el.textContent).toContain('2026-03-04')
    expect(el.textContent).toContain('\u674e\u5de5')
    expect(el.textContent).toContain('\u6765\u81ea\u7b14\u8bb0')
    unmount()
  })

  it('with an empty library the facts table does not show filters that filter nothing, but offers a way out', async () => {
    const { el, unmount } = await mount(<FactsTable query="" actions={ACTIONS} />)
    expect(el.querySelector('.filter-row')).toBeNull()
    expect(el.textContent).not.toContain('\u6309\u7c7b\u578b / \u8bf4\u8bdd\u4eba / \u4e3b\u9898 / \u5b9e\u4f53 / \u7f6e\u4fe1\u5ea6\u7b5b')
    expect(el.textContent).toContain('\u5bfc\u5165')
    expect(el.textContent).toContain('\u56de\u77e5\u8bc6\u5e93\u603b\u89c8')
    // an empty table should still show what it looks like -- exactly what the old button owed
    expect(el.querySelectorAll('.kb-example .fact-row').length).toBe(2)
    unmount()
  })
})
