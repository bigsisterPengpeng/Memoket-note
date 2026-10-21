/**
 * An in-note link `[title](note://<id>)` folds into a clickable chip when the cursor is not on it
 * (in Trilium an internal link is a reference link with an icon). When the cursor enters, it expands into
 * editable source. Clicking the chip opens that note directly -- it is a widget, so there is no "is a click edit or jump"
 * ambiguity, and unlike external links no ⌘ is needed.
 */
import { syntaxTree } from '@codemirror/language'
import { RangeSetBuilder, type Extension } from '@codemirror/state'
import { Decoration, type DecorationSet, EditorView, ViewPlugin, type ViewUpdate, WidgetType } from '@codemirror/view'
import { fmtDate } from '../util/time'
import { wordCount } from '../util/wordCount'
import { mountIcon } from '../components/iconDom'
import { t } from '../i18n'

const NOTE_LINK = /\[([^\]\n]{1,80})\]\(note:\/\/([0-9a-f]{12})\)/g

/** The detail of the `note-link-menu` event fired on right-clicking a note link chip */
export type NoteLinkMenuDetail = { id: string; title: string; x: number; y: number }

/** Fetch a note's summary. Injected by the caller -- the editor layer does not know the api module. */
export type NoteLookup = (id: string) => Promise<{ title: string; content: string; updated_at: string } | null>

/** Hovering 300ms shows a summary card (Trilium's note_tooltip): know which note it links to without opening it.
 *  Each note is fetched only once; the card hangs on body and is positioned by the chip. */
const peekCache = new Map<string, Awaited<ReturnType<NoteLookup>>>()
let peekEl: HTMLElement | null = null
function hidePeek() { peekEl?.remove(); peekEl = null }

async function showPeek(anchor: HTMLElement, id: string, lookup: NoteLookup, still: () => boolean) {
  if (!peekCache.has(id)) {
    try { peekCache.set(id, await lookup(id)) } catch { peekCache.set(id, null) }
  }
  if (!anchor.isConnected || !still()) return
  const n = peekCache.get(id)
  hidePeek()
  const el = document.createElement('div')
  el.className = 'cm-fact-peek cm-note-peek' + (n ? '' : ' missing')
  if (!n) {
    el.textContent = t('This note no longer exists (it may have been deleted)')
  } else {
    const ttl = document.createElement('div'); ttl.className = 'peek-text'; ttl.textContent = n.title || t('Untitled')
    const w = document.createElement('div'); w.className = 'peek-when'; w.textContent = fmtDate(n.updated_at) + ' · ' + t('{n} chars', { n: wordCount(n.content) })
    const b = document.createElement('div'); b.className = 'peek-body'
    // In the summary, fold in-note links back into titles and drop heading hashes -- seeing `](note://…)` in the card means nothing

    const plain = n.content.replace(/\[([^\]\n]+)\]\(note:\/\/[0-9a-f]{12}\)/g, '$1').replace(/^#+\s*/gm, '').replace(/\n{2,}/g, '\n').trim()
    b.textContent = plain.slice(0, 240) + (plain.length > 240 ? '…' : '')
    el.append(w, ttl, b)
  }
  const r = anchor.getBoundingClientRect()
  el.style.position = 'fixed'
  el.style.left = Math.min(r.left, window.innerWidth - 440) + 'px'
  el.style.zIndex = '300'
  document.body.append(el)

  const h = el.offsetHeight
  el.style.top = (r.bottom + 6 + h > window.innerHeight ? Math.max(4, r.top - 6 - h) : r.bottom + 6) + 'px'
  peekEl = el
}

class NoteLinkWidget extends WidgetType {
  constructor(readonly title: string, readonly id: string, readonly lookup?: NoteLookup) { super() }
  eq(o: NoteLinkWidget) { return o.title === this.title && o.id === this.id }
  /** Unmount function of the icon's React root (given by `mountIcon`); must be called when the widget is destroyed. */
  private dispose?: () => void
  destroy() { this.dispose?.() }
  toDOM() {
    const a = document.createElement('a')
    a.className = 'cm-note-link'
    a.title = t('Open this note')
    const i = document.createElement('span')
    i.className = 'bx'
    this.dispose = mountIcon(i, 'bx-note')
    a.append(i, document.createTextNode(this.title))
    a.addEventListener('mousedown', (e) => {
      if (e.button === 2) return                      // right click is left to the contextmenu below
      e.preventDefault()
      hidePeek()
      window.dispatchEvent(new CustomEvent('open-note', { detail: this.id }))
    })

    // stopPropagation: do not let MarkdownEditor's selection context menu pop up too.
    a.addEventListener('contextmenu', (e) => {
      e.preventDefault()
      e.stopPropagation()
      hidePeek()
      window.dispatchEvent(new CustomEvent<NoteLinkMenuDetail>('note-link-menu', {
        detail: { id: this.id, title: this.title, x: e.clientX, y: e.clientY } }))
    })
    if (this.lookup) {
      let timer = 0
      let hovering = false
      a.addEventListener('mouseenter', () => { hovering = true; timer = window.setTimeout(() => void showPeek(a, this.id, this.lookup!, () => hovering), 300) })
      a.addEventListener('mouseleave', () => { hovering = false; clearTimeout(timer); hidePeek() })
    }
    return a
  }
  ignoreEvent() { return true }
}

function build(view: EditorView, lookup?: NoteLookup): DecorationSet {
  const b = new RangeSetBuilder<Decoration>()
  const sel = view.state.selection.main
  for (const { from, to } of view.visibleRanges) {
    const text = view.state.doc.sliceString(from, to)
    NOTE_LINK.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = NOTE_LINK.exec(text))) {
      const start = from + m.index
      const end = start + m[0].length
      // Cursor inside: expand to source for editing
      if (sel.from <= end && sel.to >= start) continue
      const node = syntaxTree(view.state).resolveInner(start, 1)
      if (/CodeBlock|FencedCode|InlineCode/.test(node.type.name)) continue
      b.add(start, end, Decoration.replace({ widget: new NoteLinkWidget(m[1], m[2], lookup) }))
    }
  }
  return b.finish()
}

export function noteLinkChips(lookup?: NoteLookup): Extension {
  return ViewPlugin.fromClass(class {
    decorations: DecorationSet
    constructor(view: EditorView) { this.decorations = build(view, lookup) }
    update(u: ViewUpdate) {
      if (u.docChanged || u.viewportChanged || u.selectionSet) this.decorations = build(u.view, lookup)
    }
    destroy() { hidePeek() }
  }, { decorations: (v) => v.decorations })
}
