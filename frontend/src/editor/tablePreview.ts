/** Live preview of markdown tables.
 *
 * Exactly the same pattern as mermaid (see editor/mermaid.ts): when the cursor is **outside the table**
 * hide the source and render a real table; once the cursor **enters the table** swap back to source for editing.
 * Showing both is redundant, and looking at a rendered result while editing is stale.
 *
 * Why not just syntax highlighting: GFM table syntax itself is parseable (lang-markdown
 * already includes GFM), but a pile of pipes and |---| in the body neither shows structure nor lines up -- the AI now
 * generates whole tables (smart tables / EDA), and unrendered, the most useful output would be the hardest to read.
 */
import { syntaxTree } from '@codemirror/language'
import { StateField, type EditorState, type Range } from '@codemirror/state'
import { Decoration, EditorView, WidgetType, type DecorationSet } from '@codemirror/view'

/** ``| a | b |`` -> ``['a','b']``. Leading and trailing pipes are delimiters, not empty cells, and are removed;
 * an inner ``\|`` is an escaped pipe and must not split. */
function cells(line: string): string[] {
  const t = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  const out: string[] = []
  let cur = ''
  for (let i = 0; i < t.length; i++) {
    if (t[i] === '\\' && t[i + 1] === '|') { cur += '|'; i++; continue }
    if (t[i] === '|') { out.push(cur.trim()); cur = ''; continue }
    cur += t[i]
  }
  out.push(cur.trim())
  return out
}

/** The separator row ``|---|:--:|`` decides each column's alignment. */
function alignments(line: string): ('left' | 'center' | 'right')[] {
  return cells(line).map((c) => {
    const l = c.startsWith(':')
    const r = c.endsWith(':')
    return l && r ? 'center' : r ? 'right' : 'left'
  })
}

function isSeparator(line: string): boolean {
  const cs = cells(line)
  return cs.length > 0 && cs.every((c) => /^:?-{1,}:?$/.test(c))
}

class TableWidget extends WidgetType {
  constructor(readonly source: string) { super() }
  eq(other: TableWidget) { return other.source === this.source }

  toDOM() {
    const lines = this.source.split('\n').filter((l) => l.trim())
    const wrap = document.createElement('div')
    wrap.className = 'cm-md-table'
    const table = document.createElement('table')
    const align = lines[1] ? alignments(lines[1]) : []
    const head = document.createElement('thead')
    const hr = document.createElement('tr')
    cells(lines[0]).forEach((c, i) => {
      const th = document.createElement('th')
      th.textContent = c
      th.style.textAlign = align[i] ?? 'left'
      hr.append(th)
    })
    head.append(hr)
    const body = document.createElement('tbody')
    for (const line of lines.slice(2)) {
      const tr = document.createElement('tr')
      cells(line).forEach((c, i) => {
        const td = document.createElement('td')
        td.textContent = c
        td.style.textAlign = align[i] ?? 'left'
        tr.append(td)
      })
      body.append(tr)
    }
    table.append(head, body)
    wrap.append(table)
    return wrap
  }

  // Clicking a table must be able to put the cursor into the source for editing, so the event **must not** be swallowed
  ignoreEvent() { return false }
}

/** Find all GFM tables. lang-markdown's GFM extension parses them into ``Table`` nodes;
 * use the syntax tree directly rather than scanning lines ourselves -- our own scan would misfire on fake tables inside code blocks. */
function tableDecorations(state: EditorState): DecorationSet {
  const decos: Range<Decoration>[] = []
  const ranges = state.selection.ranges
  syntaxTree(state).iterate({
    enter: (node) => {
      if (node.name !== 'Table') return
      const text = state.doc.sliceString(node.from, node.to)
      const lines = text.split('\n').filter((l) => l.trim())
      if (lines.length < 2 || !isSeparator(lines[1])) return
      // Cursor inside the table = editing, show source
      if (ranges.some((r) => r.from <= node.to && r.to >= node.from)) return
      decos.push(Decoration.replace({ block: true }).range(node.from, node.to))
      decos.push(Decoration.widget({
        widget: new TableWidget(text), side: 1, block: true,
      }).range(node.to))
    },
  })
  return Decoration.set(decos, true)
}

// Block decorations must come from a StateField, not a ViewPlugin -- CM6 throws outright
// `RangeError: Block decorations may not be specified via plugins`
// (the comments on the mermaid side record the same trap).
export const tablePreview = StateField.define<DecorationSet>({
  create(state) { return tableDecorations(state) },
  update(value, tr) {
    return (tr.docChanged || tr.selection) ? tableDecorations(tr.state) : value
  },
  provide: (f) => EditorView.decorations.from(f),
})
