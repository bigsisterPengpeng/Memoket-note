
import { EditorView, keymap } from '@codemirror/view'

export type AltHoverRange = { from: number; to: number; focus?: number }
export type AltHoverOpen = (phrase: string, anchor: DOMRect | null, reason: 'hover' | 'key', range: AltHoverRange) => void

export const HOVER_MS = 400
export const MAX_PHRASE = 24
/** Words the segmenter does not know (a two-character CJK word missing from ICU's dictionary gets split into two single characters): join adjacent single-character segments into a run for the knowledge base to recognize, at most this many characters */
export const MAX_RUN = 6
/** `focus` = the offset in text of the character the mouse rests on: only given for "runs of single characters"; the knowledge base uses it to pick the real word (`util/traceCard.pickTerm`) */
export type Phrase = { from: number; to: number; text: string; focus?: number }

let seg: Intl.Segmenter | null | undefined
function segmenter(): Intl.Segmenter | null {
  if (seg === undefined) {
    try { seg = new Intl.Segmenter('zh-Hans', { granularity: 'word' }) } catch { seg = null }
  }
  return seg
}

const isCjk = (s: string) => /^[\u4e00-\u9fff]$/.test(s)

/** Which word the col-th character of a line of text falls on (pure function, testable). Returns null on punctuation / whitespace; word length capped at MAX_PHRASE.
 *
 *  When the segmenter yields a **single CJK character** (the word is not in its dictionary: measured on several common two-character words, all split),
 *  join the adjacent single-character segments left and right into a run (stopping at multi-character words / non-CJK / punctuation, capped at MAX_RUN), and hand it with focus to the knowledge base to recognize the whole word. */
export function phraseAt(line: string, col: number): Phrase | null {
  if (col < 0 || col >= line.length) return null
  const s = segmenter()
  if (s) {
    const parts = [...s.segment(line)]
    const k = parts.findIndex((p) => col >= p.index && col < p.index + p.segment.length)
    if (k < 0 || !parts[k].isWordLike) return null
    const hit = parts[k]
    if (!isCjk(hit.segment)) {
      const text = hit.segment.slice(0, MAX_PHRASE)
      return { from: hit.index, to: hit.index + text.length, text }
    }
    const single = (p: Intl.SegmentData | undefined) => !!p && !!p.isWordLike && isCjk(p.segment)
    let a = k
    let b = k
    while (b + 1 < parts.length && single(parts[b + 1]) && b - a + 1 < MAX_RUN) b++
    while (a > 0 && single(parts[a - 1]) && b - a + 1 < MAX_RUN) a--
    const from = parts[a].index
    const to = parts[b].index + parts[b].segment.length
    return { from, to, text: line.slice(from, to), focus: col - from }
  }
  const re = /[\p{L}\p{N}_]+/gu
  let m: RegExpExecArray | null
  while ((m = re.exec(line))) {
    if (col >= m.index && col < m.index + m[0].length) {
      const text = m[0].slice(0, MAX_PHRASE)
      return { from: m.index, to: m.index + text.length, text }
    }
  }
  return null
}

/** The word at document position pos: inside a selection it is the selection (within one line, <= 80 characters), otherwise by segmentation; resting at the end of a word (cursor right after it) also counts as that word. */
export function phraseAtPos(view: EditorView, pos: number): Phrase | null {
  const sel = view.state.selection.main
  if (!sel.empty && pos >= sel.from && pos <= sel.to) {
    const text = view.state.doc.sliceString(sel.from, sel.to).trim()
    if (text && text.length <= 80 && !text.includes('\n')) return { from: sel.from, to: sel.to, text }
  }
  const line = view.state.doc.lineAt(pos)
  const col = pos - line.from
  const p = phraseAt(line.text, col) ?? (col > 0 ? phraseAt(line.text, col - 1) : null)
  return p && { from: line.from + p.from, to: line.from + p.to, text: p.text, focus: p.focus }
}

function anchorOf(view: EditorView, p: Phrase): DOMRect | null {
  const a = view.coordsAtPos(p.from)
  if (!a) return null
  const b = view.coordsAtPos(p.to, -1)
  const right = b && Math.abs(b.top - a.top) < 2 ? b.right : a.right
  return new DOMRect(a.left, a.top, Math.max(1, right - a.left), a.bottom - a.top)
}

export function altHover(onOpen: AltHoverOpen) {
  let timer: ReturnType<typeof setTimeout> | null = null
  let pending: Phrase | null = null
  const cancel = () => { if (timer) { clearTimeout(timer); timer = null } pending = null }
  const open = (view: EditorView, p: Phrase, reason: 'hover' | 'key') =>
    onOpen(p.text, anchorOf(view, p), reason, { from: p.from, to: p.to, focus: p.focus })

  const handlers = EditorView.domEventHandlers({
    mousemove(e, view) {
      if (!e.altKey) { cancel(); return false }
      const pos = view.posAtCoords({ x: e.clientX, y: e.clientY })
      const p = pos == null ? null : phraseAtPos(view, pos)
      if (!p) { cancel(); return false }
      if (pending && pending.from === p.from && pending.to === p.to) return false   // still resting on the same word: let the timer finish
      cancel()
      pending = p
      timer = setTimeout(() => {
        timer = null
        if (pending) { open(view, pending, 'hover'); pending = null }
      }, HOVER_MS)
      return false
    },
    mouseleave() { cancel(); return false },
    keyup(e) { if (e.key === 'Alt') cancel(); return false },
  })
  // ⌥↩: the word at the cursor. Runs before defaultKeymap (mounted early in MarkdownEditor)
  const keys = keymap.of([{ key: 'Alt-Enter', run: (view) => {
    const p = phraseAtPos(view, view.state.selection.main.head)
    if (!p) return false
    open(view, p, 'key')
    return true
  } }])
  return [handlers, keys]
}
