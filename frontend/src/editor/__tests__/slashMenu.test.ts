// @vitest-environment jsdom
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { afterEach, describe, expect, it } from 'vitest'
import { setLang } from '../../i18n'
import { BLOCK_MODES } from '../../api'
import { SLASH_ITEMS, filtered } from '../slashMenu'

/**
 * Round 704 collapsed the always-on Markdown toolbar, with one reason being "the `/` menu is still there" --
 * while at the time this menu had **not a single formatting command** (only found by the round 705 screenshot).
 * These cases pin exactly that: **the formatting group must really work**.
 */
describe('the formatting group of the / menu', () => {
  const layout = SLASH_ITEMS.filter((i) => i.group === 'Formatting')

  it('exists, and every item carries a command that runs in place', () => {
    expect(layout.length).toBeGreaterThanOrEqual(8)
    for (const it of layout) expect(typeof it.cmd).toBe('function')
  })

  it('the AI group has no cmd at all (they need the network and must go to the layer above)', () => {
    for (const it of SLASH_ITEMS.filter((i) => i.group === 'AI')) expect(it.cmd).toBeUndefined()
  })

  it('every item has a group (rendering inserts small headings by it; missing one mixes groups)', () => {
    for (const it of SLASH_ITEMS) expect(it.group).toBeTruthy()
  })

  /** `App.onSlash` dispatch: needsPrompt -> input box; table-image / audio -> pick a file;
   *  voice -> record; **everything else is sent to the backend as a BlockMode** (an unchecked cast).
   *  So every item must land in one of these kinds, otherwise it is "clicking does nothing" or
   *  "sent a mode the backend does not know". */
  it('every item is handled by someone (otherwise clicking does nothing)', () => {
    const handled = new Set(['table-image', 'audio', 'voice'])
    for (const it of SLASH_ITEMS) {
      if (it.cmd || it.needsPrompt || handled.has(it.key)) continue
      expect(BLOCK_MODES as readonly string[]).toContain(it.key)
    }
  })

  it('templates do not occupy the / menu; only cursor-level edits and generation actions stay here', () => {
    expect(SLASH_ITEMS.some((item) => item.group === 'Writing templates')).toBe(false)
    expect(SLASH_ITEMS.some((item) => item.key.startsWith('template-'))).toBe(false)
  })

  it('typing "list" filters to the three list commands, none of the AI ones', () => {
    const hit = filtered('list')
    expect(hit.map((i) => i.key).sort()).toEqual(['ol', 'todo', 'ul'])
  })

  it('typing "heading" filters to the three heading levels', () => {
    expect(filtered('heading').map((i) => i.key)).toEqual(['h1', 'h2', 'h3'])
  })

  /** Really run a command once: not "there is a function", but "after running, the document really changed". */
  it('the task list command really turns the current line into - [ ]', () => {
    const view = new EditorView({ state: EditorState.create({ doc: 'Buy batteries' }) })
    view.dispatch({ selection: { anchor: 3 } })
    SLASH_ITEMS.find((i) => i.key === 'todo')!.cmd!(view)
    expect(view.state.doc.toString()).toBe('- [ ] Buy batteries')
    view.destroy()
  })

  it('the level-2 heading command really adds ## ', () => {
    const view = new EditorView({ state: EditorState.create({ doc: 'Hardware' }) })
    view.dispatch({ selection: { anchor: 2 } })
    SLASH_ITEMS.find((i) => i.key === 'h2')!.cmd!(view)
    expect(view.state.doc.toString()).toBe('## Hardware')
    view.destroy()
  })
})

describe('the / menu filter in the Chinese UI', () => {
  afterEach(() => setLang('en'))
  it('the translated labels are searchable too', () => {
    setLang('zh')
    expect(filtered('\u5217\u8868').map((i) => i.key).sort()).toEqual(['ol', 'todo', 'ul'])   // "list" in Chinese
    expect(filtered('\u6807\u9898').map((i) => i.key)).toEqual(['h1', 'h2', 'h3'])            // "heading" in Chinese
  })
})
