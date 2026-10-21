
import { Decoration, EditorView, ViewPlugin, type DecorationSet, type ViewUpdate } from '@codemirror/view'
import { RangeSetBuilder } from '@codemirror/state'

/** How many lines down to look for the closing `---` at most. Front-matter should never be longer than this. */
const MAX_LINES = 30

const line = Decoration.line({ class: 'cm-frontmatter' })

/** The line (1-based, the closing `---` line) the front-matter at the start of the document reaches; 0 if none. */
export function frontmatterEnd(doc: string): number {
  const lines = doc.split('\n')
  if (lines[0]?.trim() !== '---') return 0
  for (let i = 1; i < Math.min(lines.length, MAX_LINES); i++) {
    const t = lines[i].trim()
    if (t === '---') return i + 1
    // Anything other than blank lines, `key: value`, `- list item` and indented continuation lines -> this is not front-matter
    if (t && !/^[\w.-]+\s*:/.test(t) && !/^-\s/.test(t) && !/^\s/.test(lines[i])) return 0
  }
  return 0
}

function build(view: EditorView): DecorationSet {
  const b = new RangeSetBuilder<Decoration>()
  const end = frontmatterEnd(view.state.doc.toString())
  for (let n = 1; n <= end; n++) b.add(view.state.doc.line(n).from, view.state.doc.line(n).from, line)
  return b.finish()
}

export const frontmatterDim = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet
    constructor(view: EditorView) { this.decorations = build(view) }
    update(u: ViewUpdate) { if (u.docChanged) this.decorations = build(u.view) }
  },
  { decorations: (v) => v.decorations },
)
