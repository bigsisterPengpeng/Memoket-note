import { syntaxTree } from '@codemirror/language'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import type { EditorState } from '@codemirror/state'
import { Decoration, EditorView, ViewPlugin, type DecorationSet, type ViewUpdate } from '@codemirror/view'
import { tags } from '@lezer/highlight'

/** Content styling -- headings/emphasis/links/code actually look like
 * headings/emphasis/links/code instead of raw '#'/'*'/'`' text, without
 * leaving plain-text mode (the doc is still one string underneath). */

export const MARKDOWN_HIGHLIGHT_SPEC = [
  { tag: tags.heading1, fontSize: 'var(--t-read-h1)', fontWeight: 'var(--w-bold)' },
  { tag: tags.heading2, fontSize: 'var(--t-read-h2)', fontWeight: 'var(--w-bold)' },
  { tag: tags.heading3, fontSize: 'var(--t-read-h3)', fontWeight: 'var(--w-bold)' },
  { tag: [tags.heading4, tags.heading5, tags.heading6], fontWeight: 'var(--w-bold)' },
  { tag: tags.emphasis, fontStyle: 'italic' },
  { tag: tags.strong, fontWeight: 'var(--w-bold)' },
  { tag: tags.strikethrough, textDecoration: 'line-through' },
  { tag: tags.link, color: 'var(--accent)', textDecoration: 'underline' },
  { tag: tags.url, color: 'var(--muted)' },
  { tag: tags.monospace, fontFamily: 'var(--mono)', background: 'var(--card-alt)' },
  { tag: tags.quote, fontStyle: 'italic' },
  // NOT colored like tags.link -- a plain "- " list item isn't clickable,
  // and coloring it the same accent blue as a real link is a misleading
  // affordance (reported directly: "it looks like a link but can't be clicked"). No color at all:
  // the list *content* is body text; only the "- "/"1. " marker is dimmed,
  // via ListMark in MARK_NODES below.
  { tag: tags.list },
]
export const markdownHighlight = HighlightStyle.define(MARKDOWN_HIGHLIGHT_SPEC)

// The literal delimiter characters (#, *, _, `, >) -- always visible, styled
// gray/muted rather than hidden. An earlier version hid these on every line
// except the one the cursor is on (full Obsidian-style live preview), but
// that made marks pop in/out while typing nearby and felt jumpy for such a
// small, frequent element -- reverted back to a flat gray on explicit
// request ("keep markdown formatting grey"). The bigger, less-frequent case
// (a whole ```mermaid block) gets the cursor-aware hide/show treatment
// instead, see mermaid.ts -- showing both the diagram AND its full source
// at once is real redundant clutter in a way a few gray "**" characters
// mixed into a sentence isn't.
export const MARK_NODES = new Set(['HeaderMark', 'QuoteMark', 'LinkMark', 'EmphasisMark', 'CodeMark', 'ListMark'])

function markDecorations(state: EditorState): DecorationSet {
  const decos: { from: number; to: number }[] = []
  syntaxTree(state).iterate({
    enter: (node) => {
      if (MARK_NODES.has(node.name)) decos.push({ from: node.from, to: node.to })
    },
  })
  return Decoration.set(
    decos.map((d) => Decoration.mark({ class: 'cm-syntax-mark' }).range(d.from, d.to)),
    true,
  )
}

export const dimSyntaxMarks = ViewPlugin.fromClass(class {
  decorations: DecorationSet
  constructor(view: EditorView) { this.decorations = markDecorations(view.state) }
  update(update: ViewUpdate) {
    if (update.docChanged) this.decorations = markDecorations(update.state)
  }
}, { decorations: (v) => v.decorations })

/** 30vh of padding under the body (Trilium's ScrollPadding): even the last line can scroll to the middle of the view, and when writing at the end the cursor
 *  does not hug the status bar; clicking blank space puts the cursor at the end. Main editor only -- quick view / split / revisions / review
 *  read-only panes already have a height cap, and padding there is just pointless scrolling. */
export const scrollPadding = EditorView.theme({ '.cm-content': { paddingBottom: '30vh' } })

export const editorTheme = EditorView.theme({
  '&': {
    fontSize: 'var(--t-read)',
    backgroundColor: 'transparent',
  },
  '.cm-content': {
    padding: '0',
    lineHeight: 'var(--lh-read)',
    fontFamily: 'inherit',
    caretColor: 'var(--fg)',
  },
  '.cm-scroller': {
    fontFamily: 'inherit',
    minHeight: '60vh',
  },
  '&.cm-focused': { outline: 'none' },
  '.cm-syntax-mark': { opacity: 0.35 },
  /* front-matter: monospace, faint, normal size, **overriding the setext heading's bold enlargement**
     (see the history in editor/frontmatter.ts). `!important` is needed --
     the heading style comes from syntax highlighting and outweighs line decorations. */
  '.cm-frontmatter': {
    fontFamily: 'var(--mono)',
    fontSize: 'var(--t-sm)',
    color: 'var(--ink-3)',
  },
  '.cm-frontmatter *': {
    fontSize: 'inherit !important',
    fontWeight: 'var(--w-normal) !important',
    color: 'inherit !important',
  },
  '.cm-mermaid-widget': {
    margin: '10px 0',
    padding: '12px',
    borderRadius: 'var(--r)',
    background: 'var(--card-alt)',
    textAlign: 'center',
    fontSize: 'var(--t-md)',
    color: 'var(--muted)',
  },
  '.cm-mermaid-widget svg': { maxWidth: '100%' },
  '.cm-mermaid-autofix-note': {
    fontSize: 'var(--t-xs)',
    color: 'var(--muted)',
    fontStyle: 'italic',
    marginBottom: '6px',
  },
  '.cm-mermaid-error': { textAlign: 'left' },
  '.cm-mermaid-error-msg': { color: 'var(--del)', marginBottom: '6px' },
  '.cm-mermaid-error-code': {
    whiteSpace: 'pre-wrap',
    fontFamily: 'var(--mono)',
    fontSize: 'var(--t-sm)',
    color: 'var(--fg)',
    background: 'var(--card-alt)',
    borderRadius: 'var(--r-sm)',
    padding: '8px',
    margin: 0,
  },
  '.cm-image-embed': {
    maxWidth: '100%',
    maxHeight: '480px',
    borderRadius: 'var(--r-sm)',
    display: 'block',
    margin: '6px 0',
    cursor: 'text',
  },
  '.cm-task-checkbox': {
    cursor: 'pointer',
    marginRight: '4px',
    verticalAlign: 'middle',
    position: 'relative',
    top: '-1px',
  },
})

export { syntaxHighlighting }
