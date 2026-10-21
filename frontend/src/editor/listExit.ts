
import type { EditorView } from '@codemirror/view'
import { Prec } from '@codemirror/state'
import { keymap } from '@codemirror/view'

/** An empty list item / task item / quote line: only the marker left (indent allowed, trailing whitespace allowed) */
export const EMPTY_ITEM = /^(\s*)(?:(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?|>\s*)$/

export function exitEmptyItem(view: EditorView): boolean {
  const { state } = view
  const range = state.selection.main
  if (!range.empty) return false
  const line = state.doc.lineAt(range.head)
  if (range.head !== line.to) return false
  const m = EMPTY_ITEM.exec(line.text)
  if (!m) return false
  // A nested empty item: outdent one level first (`  - ` -> `- `); only at top level does it really exit -- coming out level by level like Notion
  const indent = m[1]
  const insert = indent.length >= 2 ? indent.slice(0, -2) + line.text.slice(indent.length) : ''
  view.dispatch({ changes: { from: line.from, to: line.to, insert }, selection: { anchor: line.from + insert.length }, userEvent: 'delete' })
  return true
}

export const listExitKeymap = Prec.high(keymap.of([{ key: 'Enter', run: exitEmptyItem }]))
