import { syntaxTree } from '@codemirror/language'
import { StateField, type EditorState, type Range } from '@codemirror/state'
import { Decoration, EditorView, WidgetType, type DecorationSet } from '@codemirror/view'

/** Replaces the raw `[ ]`/`[x]` TaskMarker text (from the GFM TaskList
 * extension) with a real, clickable checkbox -- otherwise it's just styled
 * text, same as any other markdown syntax, and Notion/Apple Notes users
 * expect to click it. `pos` is captured at decoration-build time rather
 * than resolved via posAtDOM() on click -- simpler and doesn't depend on
 * the DOM node still matching a live document position by the time a click
 * lands (edits in between would desync posAtDOM, not a fixed captured pos
 * combined with recomputing decorations on every doc change anyway). */
class CheckboxWidget extends WidgetType {
  constructor(readonly checked: boolean, readonly pos: number) { super() }
  eq(other: CheckboxWidget) { return other.checked === this.checked && other.pos === this.pos }
  toDOM(view: EditorView) {
    const box = document.createElement('input')
    box.type = 'checkbox'
    box.checked = this.checked
    box.className = 'cm-task-checkbox'
    box.addEventListener('mousedown', (e) => e.preventDefault())
    box.addEventListener('click', () => {
      const charPos = this.pos + 1
      const ch = view.state.doc.sliceString(charPos, charPos + 1)
      const next = /[xX]/.test(ch) ? ' ' : 'x'
      view.dispatch({ changes: { from: charPos, to: charPos + 1, insert: next } })
    })
    return box
  }
  ignoreEvent() { return false }
}

function taskDecorations(state: EditorState): DecorationSet {
  const decos: Range<Decoration>[] = []
  syntaxTree(state).iterate({
    enter: (node) => {
      if (node.name !== 'TaskMarker') return
      const text = state.doc.sliceString(node.from, node.to)
      const checked = /\[[xX]\]/.test(text)
      decos.push(Decoration.replace({ widget: new CheckboxWidget(checked, node.from) }).range(node.from, node.to))
    },
  })
  return Decoration.set(decos, true)
}

export const taskCheckbox = StateField.define<DecorationSet>({
  create(state) {
    return taskDecorations(state)
  },
  update(value, tr) {
    return tr.docChanged ? taskDecorations(tr.state) : value
  },
  provide: (f) => EditorView.decorations.from(f),
})
