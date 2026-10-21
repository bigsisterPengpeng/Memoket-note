import { syntaxTree } from '@codemirror/language'
import { StateField, type EditorState, type Range } from '@codemirror/state'
import { Decoration, EditorView, WidgetType, type DecorationSet } from '@codemirror/view'
import type { Mermaid } from 'mermaid'
import { t } from '../i18n'


// while most notes have no diagram at all. Import it the first time a diagram really needs drawing, then reuse the same instance.
// styles.css themes the whole app off prefers-color-scheme (no manual
// toggle) -- mermaid needs the same signal or its diagrams render with a
// light-mode palette on a dark background, which looks broken rather than
// merely mismatched (white diagram boxes on a near-black page).
let mermaidP: Promise<Mermaid> | null = null
function loadMermaid(): Promise<Mermaid> {
  if (!mermaidP) {
    mermaidP = import('mermaid').then((m) => {
      const prefersDark = typeof window !== 'undefined'
        && window.matchMedia?.('(prefers-color-scheme: dark)').matches
      m.default.initialize({
        startOnLoad: false,
        layout: 'dagre',
        look: 'classic',
        theme: prefersDark ? 'dark' : 'default',
        securityLevel: 'strict',
      })
      return m.default
    })
  }
  return mermaidP
}

// Same source text is re-scanned into a fresh widget on every doc edit
// elsewhere in the file -- cache by source so retyping a line above a
// diagram doesn't re-run the mermaid parser/layout for an unchanged diagram.
type RenderResult = { svg: string | null; usedCode: string }
const renderCache = new Map<string, Promise<RenderResult>>()
let renderSeq = 0

// The one confirmed, reproducible mermaid syntax killer in this app's actual
// output: any straight or curly quote character INSIDE a [...]/(...)/{...}
// node label desyncs mermaid's parser (`mermaid.parse()` rejects; verified
// directly against mermaid 11.17). The model is now instructed not to do
// this (see _MERMAID_HINT in prompts.py), but a belt-and-suspenders repair
// here covers anything hand-typed or from a future/local-model regression --
// "there should be an autofix" was asked for directly rather than just erroring out.
// Deliberately narrow: strip only quote chars, only inside bracket labels,
// and only kept if the result actually re-parses -- never guess further.
const QUOTE_CHARS = /["'“”‘’]/g
export function autoFixMermaid(code: string): string {
  return code.replace(/([[({])([^\])}]*)([\])}])/g, (_m, open, inner, close) => (
    open + inner.replace(QUOTE_CHARS, '') + close
  ))
}

// mermaid.render() does NOT reject on a syntax error -- it catches its own
// parse failure internally and resolves with a built-in "bomb icon + Syntax
// error in text" SVG instead (confirmed: mermaid.parse() rejects with a
// real message, mermaid.render() on the same bad source resolves fine).
// That left our own `.catch(() => null)` fallback dead code -- every syntax
// error rendered mermaid's generic bomb icon with zero actionable info, no
// way to see or recover the source. Calling parse() ourselves first lets us
// catch the real error before render() swallows it, so we can either
// auto-fix and render the repaired version, or fall back to showing the raw
// ```mermaid source instead of a dead end.
async function renderOnce(code: string, id: string): Promise<string | null> {
  try {
    const mermaid = await loadMermaid()
    await mermaid.parse(code)
    return (await mermaid.render(id, code)).svg
  } catch {
    return null
  }
}

/** Render a mermaid snippet to an SVG string; null on failure.
 *
 *  PDF export needs it: the print step runs in an **offscreen window** with JS turned off (`javascript: false`),
 *  so diagrams must be rendered here first and the SVG inlined. It takes the same path as the editor (including `autoFixMermaid`
 *  and that cache), not a second implementation -- two paths rendering different diagrams is the real trap. */
export async function mermaidSvg(code: string): Promise<string | null> {
  const r = await renderMermaid(code)
  return r.svg
}

function renderMermaid(code: string): Promise<RenderResult> {
  const cached = renderCache.get(code)
  if (cached) return cached
  const id = `mermaid-${renderSeq++}`
  const promise = (async (): Promise<RenderResult> => {
    const svg = await renderOnce(code, id)
    if (svg) return { svg, usedCode: code }
    const fixed = autoFixMermaid(code)
    if (fixed === code) return { svg: null, usedCode: code }
    const fixedSvg = await renderOnce(fixed, `${id}-fixed`)
    return fixedSvg ? { svg: fixedSvg, usedCode: fixed } : { svg: null, usedCode: code }
  })()
  renderCache.set(code, promise)
  return promise
}

class MermaidWidget extends WidgetType {
  constructor(readonly code: string) { super() }
  eq(other: MermaidWidget) { return other.code === this.code }
  toDOM() {
    const wrap = document.createElement('div')
    wrap.className = 'cm-mermaid-widget'
    wrap.textContent = t('Rendering diagram…')
    renderMermaid(this.code).then(({ svg, usedCode }) => {
      if (svg) {
        wrap.innerHTML = svg
        if (usedCode !== this.code) {
          const note = document.createElement('div')
          note.className = 'cm-mermaid-autofix-note'
          note.textContent = t('⚙ Syntax error fixed automatically (quotes inside labels removed)')
          wrap.prepend(note)
        }
        return
      }
      wrap.textContent = ''
      wrap.classList.add('cm-mermaid-error')
      const msg = document.createElement('div')
      msg.className = 'cm-mermaid-error-msg'
      msg.textContent = t('mermaid syntax error; auto-fix failed too. The original code is kept (edit it above to fix):')
      const pre = document.createElement('pre')
      pre.className = 'cm-mermaid-error-code'
      pre.textContent = this.code
      wrap.append(msg, pre)
    }).catch((e: unknown) => {
      // renderMermaid itself turns syntax errors into svg=null; this catches the unexpected throws (mermaid failing to initialize and the like)
      wrap.textContent = t('mermaid rendering failed: {err}', { err: String(e).slice(0, 80) })
      wrap.classList.add('cm-mermaid-error')
    })
    return wrap
  }
  ignoreEvent() { return true }
}

/** Find every ```mermaid fenced block. Live-preview like Obsidian's code
 * blocks: while the cursor is OUTSIDE the block, the raw fenced source is
 * hidden and only the rendered diagram widget shows (showing both at once
 * is redundant clutter, reported directly: "the mermaid diagram is shown, why is the
 * mermaid code still shown"). While the cursor is INSIDE the block (actively editing
 * it), the raw source is shown instead and the widget is suppressed, so you
 * never see a stale diagram next to source you're mid-edit on. */
function mermaidDecorations(state: EditorState): DecorationSet {
  const decos: Range<Decoration>[] = []
  const ranges = state.selection.ranges
  syntaxTree(state).iterate({
    enter: (node) => {
      if (node.name !== 'FencedCode') return
      const text = state.doc.sliceString(node.from, node.to)
      const firstNewline = text.indexOf('\n')
      if (firstNewline === -1) return
      const infoLine = text.slice(0, firstNewline)
      // info string is whatever follows the opening ``` fence marker
      const info = infoLine.replace(/^`{3,}/, '').trim()
      if (info !== 'mermaid') return
      const lastNewline = text.lastIndexOf('\n')
      const code = text.slice(firstNewline + 1, lastNewline > firstNewline ? lastNewline : undefined).trim()
      if (!code) return

      const cursorInside = ranges.some((r) => r.from <= node.to && r.to >= node.from)
      if (cursorInside) return // editing -- leave raw source visible, no widget

      decos.push(Decoration.replace({ block: true }).range(node.from, node.to))
      decos.push(Decoration.widget({
        widget: new MermaidWidget(code),
        side: 1,
        block: true,
      }).range(node.to))
    },
  })
  return Decoration.set(decos, true)
}

// Block decorations (both the hide-source replace and the diagram widget)
// MUST come from a StateField, not a ViewPlugin -- CM6 throws `RangeError:
// Block decorations may not be specified via plugins` at the first render
// otherwise. (revisionField in revisions.ts already follows this correctly;
// this one didn't originally and would have crashed the editor on the first
// ```mermaid block.)
export const mermaidPreview = StateField.define<DecorationSet>({
  create(state) {
    return mermaidDecorations(state)
  },
  update(value, tr) {
    return (tr.docChanged || tr.selection) ? mermaidDecorations(tr.state) : value
  },
  provide: (f) => EditorView.decorations.from(f),
})
