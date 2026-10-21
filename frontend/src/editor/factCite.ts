
import { syntaxTree } from '@codemirror/language'
import { RangeSetBuilder, type Extension } from '@codemirror/state'
import { CITE_RE_SOURCE } from '../util/wordCount'
import {
  Decoration, type DecorationSet, EditorView, ViewPlugin, type ViewUpdate,
  hoverTooltip, WidgetType,
} from '@codemirror/view'
import { t } from '../i18n'

/** Recognize structured KITE, imported-note and manual-fact IDs while leaving ordinary brackets alone. */
export { CITE_RE_SOURCE }
const CITE = new RegExp(CITE_RE_SOURCE, 'g')

/** Fetch a fact's details. Injected by the caller; the editor layer does not know the api module -- it must be
 *  testable on its own and reusable in other hosts. */
export type FactLookup = (id: string) => Promise<{
  text: string
  when?: string
  sources?: string[]
} | null>

/** Do not expose `[username-digits-hash]` directly in the body: it is a machine primary key with no reading value for the author.
 * The underlying text is kept as-is; copy, export, verification and model grounding keep using the full id;
 * when the cursor enters the citation the source expands too, so the user can still delete or correct it. */
export function citeChipLabel(id: string): string {
  const suffix = id.match(/-([0-9A-Fa-f]+)$/)?.[1]?.toUpperCase()
  return suffix ? t('Source · {id}', { id: suffix.slice(-4) }) : t('Source')
}

class FactCiteWidget extends WidgetType {
  constructor(readonly ids: string[]) { super() }
  eq(other: FactCiteWidget) { return other.ids.join('\0') === this.ids.join('\0') }
  toDOM() {
    const el = document.createElement('span')
    el.className = 'cm-fact-cite-chip'
    el.textContent = this.ids.length > 1 ? t('{n} sources', { n: this.ids.length }) : citeChipLabel(this.ids[0])
    el.title = this.ids.length > 1 ? t('View {n} sources', { n: this.ids.length }) : t('View this source')
    el.tabIndex = 0
    el.setAttribute('role', 'link')
    el.setAttribute('aria-label', t('Open cited source {ids}', { ids: this.ids.join(', ') }))
    const open = () => window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:fact:' + this.ids[0] }))
    el.addEventListener('mousedown', (e) => { e.preventDefault(); open() })
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() }
    })
    return el
  }
  ignoreEvent() { return true }
}

function buildCites(view: EditorView): DecorationSet {
  const b = new RangeSetBuilder<Decoration>()
  const sel = view.state.selection.main
  for (const { from, to } of view.visibleRanges) {
    const text = view.state.doc.sliceString(from, to)
    CITE.lastIndex = 0
    let m: RegExpExecArray | null
    let pending: { start: number; end: number; ids: string[] } | null = null
    const flush = () => {
      if (!pending) return
      if (!(sel.from <= pending.end && sel.to >= pending.start)) {
        b.add(pending.start, pending.end, Decoration.replace({ widget: new FactCiteWidget(pending.ids) }))
      }
      pending = null
    }
    while ((m = CITE.exec(text))) {
      const start = from + m.index
      const end = start + m[0].length
      // Square brackets inside code blocks are not sources -- they may be the code itself
      const node = syntaxTree(view.state).resolveInner(start, 1)
      if (/CodeBlock|FencedCode|InlineCode/.test(node.type.name)) { flush(); continue }
      // Adjacent ids in the body are several sources for one thing, collapsed into one chip; the underlying text stays as-is.
      if (pending && /^\s*$/.test(view.state.doc.sliceString(pending.end, start))) {
        pending.end = end
        pending.ids.push(m[1])
      } else {
        flush()
        pending = { start, end, ids: [m[1]] }
      }
    }
    flush()
  }
  return b.finish()
}

const citePlugin = ViewPlugin.fromClass(class {
  decorations: DecorationSet
  constructor(view: EditorView) { this.decorations = buildCites(view) }
  update(u: ViewUpdate) {
    if (u.docChanged || u.viewportChanged || u.selectionSet) this.decorations = buildCites(u.view)
  }
}, { decorations: (v) => v.decorations })

/** Hover popover. Caches the facts already fetched: the same source is scanned repeatedly in a long note, and
 *  a network request each time would make hovering noticeably laggy. */
function citeTooltip(lookup: FactLookup) {
  const cache = new Map<string, Awaited<ReturnType<FactLookup>>>()

  return hoverTooltip(async (view, pos) => {
    const line = view.state.doc.lineAt(pos)
    CITE.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = CITE.exec(line.text))) {
      const from = line.from + m.index
      const to = from + m[0].length
      if (pos < from || pos > to) continue
      const id = m[1]
      if (!cache.has(id)) {
        try { cache.set(id, await lookup(id)) } catch { cache.set(id, null) }
      }
      const fact = cache.get(id)
      return {
        pos: from, end: to, above: true,
        create() {
          const dom = document.createElement('div')
          dom.className = 'cm-fact-peek'
          if (!fact) {
            // **Say so when it cannot be found.** A citation pointing at a nonexistent fact is a real problem
            // (made up by the model, or the knowledge base was rebuilt); silently showing it as plain text hides it.
            dom.textContent = t('Record not found ({id}) — the citation may be wrong, or the knowledge base was rebuilt', { id })
            dom.classList.add('missing')
            return { dom }
          }
          const when = document.createElement('div')
          when.className = 'peek-when'
          when.textContent = fact.when ?? ''
          const body = document.createElement('div')
          body.className = 'peek-text'
          body.textContent = fact.text
          dom.append(when, body)
          for (const s of (fact.sources ?? []).slice(0, 3)) {
            const src = document.createElement('div')
            src.className = 'peek-source'
            src.textContent = s
            dom.append(src)
          }
          return { dom }
        },
      }
    }
    return null
  }, { hoverTime: 200 })
}

export function factCite(lookup: FactLookup): Extension {
  return [citePlugin, citeTooltip(lookup)]
}
