/** The insert menu opened by `/` (magic key).
 *
 * Typing `/` at the start of a line or after whitespace pops it up; keep typing to filter, ↑↓ to select, Enter to confirm, Esc to close.
 *
 * **Why CM6's tooltip instead of computing overlay coordinates ourselves**: the position must follow that `/`
 * through line breaks, wrapping, scrolling and zooming without drifting. tooltip already handles all that; computing it
 * again ourselves only goes wrong at the edges (already learned on roundDiff's accept/revert toolbar:
 * the first version relied on a CSS adjacent selector, broken by the cm-widgetBuffer CM6 inserts on both sides of a widget,
 * and not a single button appeared).
 */
import { StateEffect, StateField } from '@codemirror/state'
import { EditorView, showTooltip, type Tooltip } from '@codemirror/view'

import {
  heading1Cmd, heading2Cmd, heading3Cmd, quoteCmd,
  bulletListCmd, orderedListCmd, taskListCmd, codeBlockCmd, mermaidCmd, tableCmd,
} from './markdownCommands'
import { mountIcon } from '../components/iconDom'
import { t } from '../i18n'

export type SlashItem = {
  key: string
  label: string
  hint: string
  /** boxicons class name, e.g. `bx-pen` */
  icon: string
  /** Needs the user to type a prompt as well (smart analysis, write from prompt...) */
  needsPrompt?: boolean
  /** Has an input box, but may be left empty (smart table: "leave empty to decide automatically"). The UI's promise must be kept in code. */
  promptOptional?: boolean
  placeholder?: string
  /** Group heading. Items of the same group are listed together; a small heading row is inserted when the group changes. */
  group: string
  /** Formatting items run in place: a CM6 command, no network, no React.
   *  (These return void, not CM6's Command signature --
   *  they are called directly by buttons, there is no "not my turn".) */
  cmd?: (view: EditorView) => void
}


export const SLASH_ITEMS: SlashItem[] = [
  { group: 'AI', key: 'prompt', icon: 'bx-pen', label: 'Write with AI', hint: 'Describe what to write; uses the context and your knowledge base',
    needsPrompt: true, placeholder: 'e.g. Summarize the paragraphs above into three takeaways' },

  { group: 'AI', key: 'tray', icon: 'bx-layer-plus', label: 'Write from materials', hint: 'Write a passage using only the materials you picked for this note',
    needsPrompt: true, promptOptional: true, placeholder: 'What to write? Leave empty to write from the materials' },
  { group: 'AI', key: 'chart', icon: 'bx-image-add', label: 'Smart figure', hint: 'Charts for data, generated images for concepts — picked automatically' },
  { group: 'AI', key: 'table', icon: 'bx-table', label: 'Smart table', hint: 'Turn the context into a table',
    needsPrompt: true, promptOptional: true, placeholder: 'What kind of table? Leave empty to decide automatically' },
  { group: 'AI', key: 'table-image', icon: 'bx-image-alt', label: 'Image to table', hint: 'Upload an image and extract the table in it' },
  { group: 'AI', key: 'eda', icon: 'bx-bar-chart-alt-2', label: 'Data visualization', hint: 'Chart the tables in this note: distribution, share, comparison' },
  { group: 'AI', key: 'analysis', icon: 'bx-calculator', label: 'Smart data analysis', hint: 'Ask a data question; it computes with tools before answering',
    needsPrompt: true, placeholder: 'e.g. Which channel earns the most per impression?' },
  { group: 'AI', key: 'voice', icon: 'bx-microphone', label: 'Voice input', hint: 'Record speech and insert the transcript' },
  { group: 'AI', key: 'audio', icon: 'bx-headphone', label: 'Insert audio', hint: 'Insert an audio file and transcribe it automatically' },

  { group: 'Formatting', key: 'h1', icon: 'bx-heading', label: 'Heading 1', hint: 'Starts with #', cmd: heading1Cmd },
  { group: 'Formatting', key: 'h2', icon: 'bx-heading', label: 'Heading 2', hint: 'Starts with ##', cmd: heading2Cmd },
  { group: 'Formatting', key: 'h3', icon: 'bx-heading', label: 'Heading 3', hint: 'Starts with ###', cmd: heading3Cmd },
  { group: 'Formatting', key: 'ul', icon: 'bx-list-ul', label: 'Bulleted list', hint: 'Starts with -', cmd: bulletListCmd },
  { group: 'Formatting', key: 'ol', icon: 'bx-list-ol', label: 'Numbered list', hint: 'Starts with 1.', cmd: orderedListCmd },
  { group: 'Formatting', key: 'todo', icon: 'bx-list-check', label: 'Task list', hint: 'Starts with - [ ], checkable', cmd: taskListCmd },
  { group: 'Formatting', key: 'quote', icon: 'bxs-quote-left', label: 'Quote', hint: 'Starts with >', cmd: quoteCmd },
  { group: 'Formatting', key: 'code', icon: 'bx-code-block', label: 'Code block', hint: 'Wrapped in triple backticks', cmd: codeBlockCmd },
  { group: 'Formatting', key: 'grid', icon: 'bx-table', label: 'Empty table', hint: 'Insert an empty 3-column table', cmd: tableCmd },
  { group: 'Formatting', key: 'flow', icon: 'bx-network-chart', label: 'Flowchart', hint: 'Insert a mermaid template', cmd: mermaidCmd },
]

/** Maximum instruction length in characters. Same number as backend `compose_block.MAX_PROMPT_CHARS`. */
export const MAX_PROMPT_CHARS = 2000
/** Cannot be done on a blank note: what would you chart / tabulate / analyze? (`prompt` only needs an instruction, so it is not here) */
const NEEDS_CONTENT = new Set(['chart', 'table', 'eda', 'analysis'])


export function blockPrecondition(item: Pick<SlashItem, 'key' | 'needsPrompt' | 'promptOptional'>,
                                  prompt: string, selection: string, docText: string): string {
  const p = prompt.trim()
  if (item.needsPrompt && !item.promptOptional && !p) {
    return item.key === 'custom'
      ? t('Say what to do with the selected text — with nothing written, it cannot know what to change.')
      : t('Say what it should do first.')
  }
  if (item.key === 'custom' && !selection.trim()) return t('Nothing is selected — select some text first, then right-click “Custom prompt”.')
  if (p.length > MAX_PROMPT_CHARS) return t('The instruction is too long ({n} characters, limit {max}) — one sentence is enough; no need to paste the text in.', { n: p.length, max: MAX_PROMPT_CHARS })
  if (NEEDS_CONTENT.has(item.key) && !docText.trim()) return t('The note is still empty — write something first (even one sentence about the topic) before adding figures, tables or analysis.')
  return ''
}

export type SlashState = {
  /** The position of the `/` itself. The menu is anchored here, and on confirm the typed filter is replaced starting here. */
  from: number
  /** The filter the user typed after `/` */
  query: string
  active: number
  /** A filter menu opened directly at the cursor by Smart Continue; no `/template` is actually inserted into the body. */
  preset?: boolean
}

export const openSlash = StateEffect.define<number>()
export const closeSlash = StateEffect.define<null>()
export const moveSlash = StateEffect.define<number>()

/** Hand the selected action to React to run. The menu itself touches neither network nor uploads -- the CM6 extension
 * only cares "which item was picked, where `/` spans"; what to do is decided by the layer above. */
export type SlashRunner = (item: SlashItem, from: number, to: number, preset?: boolean) => void

export function filtered(query: string): SlashItem[] {
  const q = query.trim().toLowerCase()
  if (!q) return SLASH_ITEMS
  return SLASH_ITEMS.filter((i) =>
    i.label.toLowerCase().includes(q) || i.key.includes(q) || i.hint.toLowerCase().includes(q)
    || t(i.label).toLowerCase().includes(q) || t(i.hint).toLowerCase().includes(q))
}

/** Whether this change is "typed a / at line start or after whitespace". If so, return that `/`'s position.
 *
 * **The check lives in the field's own update**, not an updateListener: that is a view-layer extension
 * that never runs in a pure EditorState (the first version was written that way: build passed, types passed, and the menu
 * never popped up once), and dispatching synchronously inside an updateListener is something CM6 discourages.
 * Inside the field it needs no view, and becomes testable as a bonus. */
function slashTypedAt(tr: { changes: { iterChanges: (f: (fA: number, tA: number, fB: number, tB: number, ins: { toString(): string }) => void) => void }; state: { sliceDoc: (a: number, b: number) => string } }): number {
  let at = -1
  tr.changes.iterChanges((_fA, _tA, _fB, tB, ins) => {
    if (ins.toString() !== '/') return
    const before = tB > 1 ? tr.state.sliceDoc(tB - 2, tB - 1) : ''
    // Only at line start (no character before) or after whitespace -- "A/B test" or "he/she" should not pop the menu
    if (before === '' || /\s/.test(before)) at = tB - 1
  })
  return at
}

export const slashField = StateField.define<SlashState | null>({
  create: () => null,
  update(v, tr) {
    for (const e of tr.effects) {
      if (e.is(openSlash)) return { from: e.value, query: '', active: 0 }
      if (e.is(closeSlash)) return null
      if (e.is(moveSlash) && v) {
        const n = filtered(v.query).length || 1
        return { ...v, active: (v.active + e.value + n) % n }
      }
    }
    if (!v) {
      if (!tr.docChanged) return null
      const at = slashTypedAt(tr)
      return at >= 0 ? { from: at, query: '', active: 0 } : null
    }
    // A preset menu has no `/query` to sync with: it only accepts ↑↓ / Enter / mouse.
    // When the user keeps typing or moves the cursor, close the menu; never leave a string of control text in the body.
    if (v.preset) {
      if (tr.docChanged || tr.state.selection.main.head !== v.from) return null
      return v
    }
    let from = v.from
    if (tr.docChanged) from = tr.changes.mapPos(from, -1)
    const head = tr.state.selection.main.head
    // Close when the cursor moves back before the `/`, or goes somewhere else
    if (head <= from || head > from + 40) return null
    const query = tr.state.sliceDoc(from + 1, head)
    // Typed a space and still matches nothing = the user is just writing an ordinary slash
    if (/\s/.test(query) && filtered(query).length === 0) return null
    return { ...v, query, active: Math.min(v.active, Math.max(0, filtered(query).length - 1)) }
  },
})

/** Select an item.
 *
 *  Items with `cmd` (formatting) **run in place**: delete the `/query` first, then run that CM6 command.
 *  They touch no network and need no React state; handing them to the runner above would mean passing the whole command set
 *  again. Both Enter and mouse go through here, so the two never behave differently. */
function pick(view: EditorView, it: SlashItem, from: number, to: number, run: SlashRunner, preset = false) {
  view.dispatch({ effects: closeSlash.of(null) })
  if (it.cmd) {
    view.dispatch({ changes: { from, to, insert: '' }, selection: { anchor: from } })
    it.cmd(view)
    view.focus()
    return
  }
  run(it, from, to, preset)
}

function menuDom(view: EditorView, st: SlashState, run: SlashRunner): { dom: HTMLElement; dispose: () => void } {
  const disposers: (() => void)[] = []
  const wrap = document.createElement('div')
  wrap.className = 'slash-menu'
  const items = filtered(st.query)
  if (!items.length) {
    const empty = document.createElement('div')
    empty.className = 'slash-empty'
    empty.textContent = t('No matching command')
    wrap.append(empty)
    return { dom: wrap, dispose: () => {} }
  }
  let lastGroup = ''
  items.forEach((it, i) => {
    // Insert a small heading row when the group changes. Keep it even when filtering leaves only one group -- it tells the user
    // "what was filtered out are formatting commands", more useful than saving a row.
    if (it.group !== lastGroup) {
      lastGroup = it.group
      const g = document.createElement('div')
      g.className = 'slash-group'
      g.textContent = t(it.group)
      wrap.append(g)
    }
    const row = document.createElement('div')
    row.className = 'slash-item' + (i === st.active ? ' active' : '')
    row.innerHTML = ''

    const icon = document.createElement('span')
    icon.className = 'slash-icon bx'
    disposers.push(mountIcon(icon, it.icon))
    const text = document.createElement('span')
    const label = document.createElement('div')
    label.className = 'slash-label'
    label.textContent = t(it.label)
    const hint = document.createElement('div')
    hint.className = 'slash-hint'
    hint.textContent = t(it.hint)
    text.append(label, hint)
    row.append(icon, text)
    // mousedown rather than click: before click the editor would already drop the selection and focus
    row.addEventListener('mousedown', (e) => {
      e.preventDefault()
      e.stopPropagation()
      const head = view.state.selection.main.head
      pick(view, it, st.from, head, run, !!st.preset)
    })
    wrap.append(row)
  })
  return { dom: wrap, dispose: () => disposers.forEach((d) => d()) }
}

export function slashMenu(run: SlashRunner) {
  const tip = showTooltip.compute([slashField], (state): Tooltip | null => {
    const st = state.field(slashField)
    if (!st) return null
    return {
      pos: st.from,
      above: false,
      arrow: false,
      // `destroy` unmounts the icons' React roots -- the menu is rebuilt on every filter, so not unmounting would leak.
      create: (view) => { const { dom, dispose } = menuDom(view, st, run); return { dom, destroy: dispose } },
    }
  })

  const keys = EditorView.domEventHandlers({
    keydown(e, view) {
      const st = view.state.field(slashField, false)
      if (!st) return false
      if (e.key === 'Escape') { view.dispatch({ effects: closeSlash.of(null) }); return true }
      if (e.key === 'ArrowDown') { view.dispatch({ effects: moveSlash.of(1) }); return true }
      if (e.key === 'ArrowUp') { view.dispatch({ effects: moveSlash.of(-1) }); return true }
      if (e.key === 'Enter' || e.key === 'Tab') {
        const items = filtered(st.query)
        const it = items[st.active]
        if (!it) return false
        e.preventDefault()
        const head = view.state.selection.main.head
        pick(view, it, st.from, head, run, !!st.preset)
        return true
      }
      return false
    },
    // Close on clicking elsewhere
    mousedown(_e, view) {
      if (view.state.field(slashField, false)) view.dispatch({ effects: closeSlash.of(null) })
      return false
    },
  })

  return [slashField, tip, keys]
}
