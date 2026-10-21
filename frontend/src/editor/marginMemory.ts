
import { StateEffect, StateField, type Extension } from '@codemirror/state'
import { EditorView, gutter, GutterMarker } from '@codemirror/view'
import type { Fact, MemoryRelationKind } from '../api'
import { t } from '../i18n'

export type MarginMark = {
  /** 1-based line number (the paragraph's first line) */
  line: number
  relation: MemoryRelationKind
  say: string
  /** How many kinds of relation this paragraph has in total; the dot only draws the most important one */
  kinds?: number

  fact_ids?: string[]
  facts?: Fact[]
  /** Only for "no grounding": `no_record` = not even a related record in the knowledge base; `no_value` = related records exist, but none carry this paragraph's figure.
   *  Judged by backend `kb/relations.detect()` (zero model; it is just whether `related` is empty). */
  why?: string
}


export function dotWorthy(m: { relation: MemoryRelationKind; why?: string }): boolean {
  return !(m.relation === 'unsupported' && m.why === 'no_record')
}

/** The one sentence on the panel for the folded tier (`n` = number of `no_record` paragraphs in this note). */
export function noRecordNote(n: number): string {
  return t('{n} paragraphs contain numbers, but the knowledge base has no related records yet.', { n })
}

/** Plain words for the six relations. Shared by the right-pane relation card, the margin dot hover and the legend. */
export const RELATION_LABEL: Record<MemoryRelationKind, string> = {
  conflict: 'Conflict', continuation: 'Continuation', corroborated: 'Corroborated', unsupported: 'Unsupported', accumulation: 'Accumulation', merge: 'Merge',
}


export const MARGIN_RULE = 'Margin dots mark how paragraphs with numbers or dates relate to the knowledge base; hover to view, click to act'

export const KB_EMPTY_NOTE = 'The knowledge base is still empty. Once you import material, related memory appears here automatically.'


export const RECALL_FAILED_NOTE = 'This paragraph could not be looked up (no answer) — the previous paragraph’s memory is not shown; edit a character or move the cursor to ask again.'


/** Which relations deserve to attach to the line edge **by themselves** (no hover): the two where the knowledge base has something to say. The rest stay silent; hover to see. */
export const AUTO_SHOW: ReadonlySet<MemoryRelationKind> = new Set<MemoryRelationKind>(['conflict', 'continuation'])

/** A dot's identity: relation + fact. Line numbers change, this does not -- "already auto-popped once" is recorded by it. */
export function markKey(m: MarginMark): string { return m.relation + ':' + (m.fact_ids ?? []).join(',') }

/** What hovering a dot shows (the top line of the card; the native title is kept for screen readers): this paragraph · relation · that plain sentence. */
export function markTitle(m: MarginMark): string {
  const more = (m.kinds ?? 1) > 1 ? t('This paragraph also has {n} other relations, ', { n: (m.kinds ?? 1) - 1 }) : ''
  return t('This paragraph (from line {line}) · {rel}', { line: m.line, rel: t(RELATION_LABEL[m.relation]) }) + `\n${m.say}\n${t(MARGIN_RULE)}\n${more}` + t('Click to see everything in the Memory tab')
}

/** Which paragraphs get relation-checked: **the same threshold as backend `relations_batch`** (>= 8 characters, contains a digit, not a heading).
 *  No cap -- the old `.slice(0, 80)` dropped everything after the 80th numbered paragraph of a 30k-character note,
 *  which is exactly where "some paragraphs have dots, some don't" came from; requests are sent in batches of 80 (the backend's per-batch limit is 80). */
export const MARGIN_BATCH = 80
export function marginParagraphs(content: string, clean: (s: string) => string): { text: string; line: number }[] {
  return paragraphsWithLines(content).map((p) => ({ ...p, text: clean(p.text).trim() }))
    .filter((p) => /\d/.test(p.text) && !p.text.startsWith('#') && p.text.length >= 8)
}
/** One paragraph's judgment (without line number); null = this paragraph has no relation. */
export type MarginVerdict = Omit<MarginMark, 'line'> | null


export function splitCached(paras: { text: string; line: number }[], cache: Map<string, MarginVerdict>):
    { hits: MarginMark[]; misses: { text: string; line: number }[] } {
  const hits: MarginMark[] = []
  const misses: { text: string; line: number }[] = []
  for (const p of paras) {
    if (cache.has(p.text)) { const v = cache.get(p.text); if (v) hits.push({ ...v, line: p.line }) }
    else misses.push(p)
  }
  return { hits, misses }
}
/** The cache must not grow forever: past this size, clear and start over (even a 30k-character note is only about 250 paragraphs). */
export const MARGIN_CACHE_MAX = 3000

export function chunked<T>(xs: T[], n: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < xs.length; i += n) out.push(xs.slice(i, i + n))
  return out
}

export const setMarginMarks = StateEffect.define<MarginMark[]>()

class Dot extends GutterMarker {
  constructor(readonly m: MarginMark) { super() }
  eq(other: Dot) { return other.m.relation === this.m.relation && other.m.say === this.m.say && other.m.line === this.m.line }
  toDOM() {
    const el = document.createElement('span')
    el.className = 'mm-dot mm-' + this.m.relation
    el.title = markTitle(this.m)
    el.dataset.line = String(this.m.line)
    el.setAttribute('aria-label', t(RELATION_LABEL[this.m.relation]))
    return el
  }
}

export const marginField = StateField.define<MarginMark[]>({
  create: () => [],
  update(marks, tr) {
    for (const e of tr.effects) if (e.is(setMarginMarks)) return e.value
    if (!tr.docChanged || marks.length === 0) return marks
    // Line numbers follow document changes: map the paragraph start position through, then convert back to a line number
    const old = tr.startState.doc
    return marks.map((m) => {
      const ln = Math.min(Math.max(1, m.line), old.lines)
      const pos = tr.changes.mapPos(old.line(ln).from, 1)
      return { ...m, line: tr.newDoc.lineAt(Math.min(pos, tr.newDoc.length)).number }
    })
  },
})

/** First line number of the paragraph at the cursor (blank lines separate paragraphs) -- the same segmentation as `paragraphsWithLines`. */
export function paragraphStartLine(doc: { lines: number; line(n: number): { text: string } }, lineNo: number): number {
  let n = Math.min(Math.max(1, lineNo), doc.lines)
  if (!doc.line(n).text.trim()) return 0            // cursor on a blank line: belongs to no paragraph
  while (n > 1 && doc.line(n - 1).text.trim()) n--
  return n
}

/** The dot's position on screen (only once drawn; CM does not draw lines outside the viewport) */
function dotRect(view: EditorView, line: number): DOMRect | null {
  const el = view.dom.querySelector(`.cm-memory-gutter .mm-dot[data-line="${line}"]`)
  return el ? el.getBoundingClientRect() : null
}

export type MarginOpen = (m: MarginMark | null, anchor: DOMRect | null, reason: 'hover' | 'click' | 'cursor') => void

export function marginMemory(onOpen: MarginOpen): Extension {
  // Dots that auto-popped: each dot shows itself only once, and once closed it stops bothering; a new set of marks (body edited) is recomputed
  const autoShown = new Set<string>()
  const find = (view: EditorView, lineFrom: number) => {
    const n = view.state.doc.lineAt(lineFrom).number
    return view.state.field(marginField).find((x) => x.line === n) ?? null
  }
  return [
    marginField,
    gutter({
      class: 'cm-memory-gutter',
      side: 'after',
      lineMarker(view, line) {
        const n = view.state.doc.lineAt(line.from).number
        const m = view.state.field(marginField).find((x) => x.line === n)
        return m ? new Dot(m) : null
      },
      lineMarkerChange: (u) => u.docChanged || u.transactions.some((t) => t.effects.some((e) => e.is(setMarginMarks))),
      domEventHandlers: {
        mousedown(view, line) {
          const m = find(view, line.from)
          if (!m) return false
          view.dispatch({ selection: { anchor: line.from }, effects: EditorView.scrollIntoView(line.from, { y: 'nearest' }) })
          onOpen(m, dotRect(view, m.line), 'click')
          return true
        },
        mouseover(view, line, event) {
          if (!(event.target as HTMLElement | null)?.classList?.contains('mm-dot')) return false
          const m = find(view, line.from)
          if (m) onOpen(m, (event.target as HTMLElement).getBoundingClientRect(), 'hover')
          return false
        },
      },
    }),
    // The cursor entered a paragraph where "the knowledge base has something to say": the card attaches to the line edge by itself (once)
    EditorView.updateListener.of((u) => {
      const marksChanged = u.transactions.some((t) => t.effects.some((e) => e.is(setMarginMarks)))
      if (!u.selectionSet && !marksChanged) return
      if (marksChanged) autoShown.clear()
      const head = u.state.selection.main.head
      const start = paragraphStartLine(u.state.doc, u.state.doc.lineAt(head).number)
      if (!start) return
      const m = u.state.field(marginField).find((x) => x.line === start)
      if (!m || !AUTO_SHOW.has(m.relation)) return
      const key = markKey(m)
      if (autoShown.has(key)) return
      autoShown.add(key)
      // The dot is only in the DOM once this update has been drawn
      requestAnimationFrame(() => { const r = dotRect(u.view, m.line); if (r) onOpen(m, r, 'cursor') })
    }),
  ]
}

/** Split the body into paragraphs on blank lines, giving each paragraph's first line number (1-based). Used together with the backend: paragraph text goes to query relations, line numbers come back to draw dots. */
export function paragraphsWithLines(content: string): { text: string; line: number }[] {
  const out: { text: string; line: number }[] = []
  const lines = content.split('\n')
  let i = 0
  while (i < lines.length) {
    if (!lines[i].trim()) { i++; continue }
    const start = i
    const buf: string[] = []
    while (i < lines.length && lines[i].trim()) { buf.push(lines[i]); i++ }
    out.push({ text: buf.join('\n'), line: start + 1 })
  }
  return out
}
