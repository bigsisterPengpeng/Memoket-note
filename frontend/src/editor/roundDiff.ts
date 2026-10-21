import { StateEffect, StateField, type EditorState, type Range, type TransactionSpec } from '@codemirror/state'
import {
  Decoration, EditorView, WidgetType, showTooltip,
  type DecorationSet, type Tooltip,
} from '@codemirror/view'
import { t } from '../i18n'

/** "What this round changed" -- highlights + per-change accept/revert.
 *
 * The harness **auto-applies** changes: the body suddenly gains a few paragraphs or loses a few sentences, and the user has no idea
 * what was touched. This layer first adds visibility (insertions in green, deleted original text restored in place with strikethrough),
 * then adds control: hover any change and "Accept / Revert" appears right there.
 *
 * **Changes are managed as hunks, with positions mapped along with document edits** -- so the user can first
 * edit a few characters inside a green insertion and then click accept. The first version was "drop all highlights whenever the document changes",
 * which could not even do "edit then accept"; move the cursor and the whole round of changes became invisible.
 *
 * Distinct from revisions.ts: that one is revision suggestions **not yet applied**; this one is **already applied**,
 * and reverting must write the original text back.
 */

export type DiffPart = { type: 'keep' | 'ins' | 'del'; text: string }

/** Split into comparable pieces: CJK per character, English/digits per word, whitespace and punctuation each on their own.
 * Splitting CJK per character is deliberate -- splitting by whole sentence would mark a whole passage red and green for one changed word, hiding
 * what actually moved. */
function segment(s: string): string[] {
  return s.match(/[\u4e00-\u9fff]|[A-Za-z0-9_]+|\s+|[^\s\u4e00-\u9fff A-Za-z0-9_]/g) ?? []
}

/** Word-level diff. Trim the common prefix and suffix first, then LCS on the middle -- one round's changes usually take only
 * a small part of the note, so after trimming the LCS part is small and O(n·m) is no worry. */
export function diffParts(before: string, after: string): DiffPart[] {
  const a = segment(before)
  const b = segment(after)

  let head = 0
  while (head < a.length && head < b.length && a[head] === b[head]) head++
  let tail = 0
  while (tail < a.length - head && tail < b.length - head
    && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail++

  const am = a.slice(head, a.length - tail)
  const bm = b.slice(head, b.length - tail)

  const out: DiffPart[] = []
  const push = (type: DiffPart['type'], text: string) => {
    if (!text) return
    const last = out[out.length - 1]
    if (last && last.type === type) last.text += text
    else out.push({ type, text })
  }

  push('keep', a.slice(0, head).join(''))

  // When the middle is too large, word-by-word LCS freezes the UI (8000 characters ~ an 8000x8000 table). First align by **line**,
  // and compare by word only within line pairs that really changed -- formatting-style changes like "a few spaces added per line" used to
  // degrade into a whole-note delete+insert, green everywhere; now only the changed words are marked.
  if (am.length * bm.length > 400_000) {
    diffByLines(am.join(''), bm.join(''), push)
  } else {
    lcs(am, bm, push)
  }

  push('keep', a.slice(a.length - tail).join(''))
  // Insertions/deletions differing only in whitespace (spaces / blank lines added by formatting) are not marked green -- but **they must not be turned into keep here**:
  // once a del " " becomes keep, every later position assumes "this space is still there", the whole hunk chain is off by one,
  // and the restored text on revert is wrong (15% of check-hunks' 2000 random cases failed to restore, some lost characters).
  // The type stays exact; "not green" goes into toHunks' soft flag, and the decoration layer just skips it.
  const merged: DiffPart[] = []
  for (const part of out) {
    const last = merged[merged.length - 1]
    if (last && last.type === part.type) last.text += part.text
    else merged.push({ type: part.type, text: part.text })
  }
  return merged
}



type Push = (type: DiffPart['type'], text: string) => void

/** Standard per-token LCS comparison. The caller guarantees a.length * b.length is within computable range. */
function lcs(am: string[], bm: string[], push: Push) {
  const n = am.length
  const m = bm.length
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = am[i] === bm[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (am[i] === bm[j]) { push('keep', am[i]); i++; j++ }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { push('del', am[i]); i++ }
    else { push('ins', bm[j]); j++ }
  }
  while (i < n) { push('del', am[i]); i++ }
  while (j < m) { push('ins', bm[j]); j++ }
}


function diffByLines(before: string, after: string, push: Push) {
  const al = before.split('\n').map((l, i, arr) => (i < arr.length - 1 ? l + '\n' : l))
  const bl = after.split('\n').map((l, i, arr) => (i < arr.length - 1 ? l + '\n' : l))
  diffLineRange(al, 0, al.length, bl, 0, bl.length, push)
}

const LINE_LCS_CELLS = 400_000

function diffLineRange(al: string[], a0: number, a1: number, bl: string[], b0: number, b1: number, push: Push) {
  const n = a1 - a0
  const m = b1 - b0
  if (n === 0 && m === 0) return
  if (n * m <= LINE_LCS_CELLS) {
    const ops: DiffPart[] = []
    lcs(al.slice(a0, a1), bl.slice(b0, b1), (type, text) => ops.push({ type, text }))
    pairLineOps(ops, push)
    return
  }
  // Anchors: lines that appear exactly once on both sides within this block
  const ca = new Map<string, number>()
  const cb = new Map<string, number>()
  for (let i = a0; i < a1; i++) ca.set(al[i], (ca.get(al[i]) ?? 0) + 1)
  for (let j = b0; j < b1; j++) cb.set(bl[j], (cb.get(bl[j]) ?? 0) + 1)
  const posB = new Map<string, number>()
  for (let j = b0; j < b1; j++) if (cb.get(bl[j]) === 1 && ca.get(bl[j]) === 1) posB.set(bl[j], j)
  const cand: { ia: number; ib: number }[] = []
  for (let i = a0; i < a1; i++) { const ib = posB.get(al[i]); if (ib !== undefined && ca.get(al[i]) === 1) cand.push({ ia: i, ib }) }
  const anchors = longestIncreasing(cand)
  if (anchors.length === 0) {
    if (n === m) {                                  // same line count: pair line by line and compare by word
      for (let r = 0; r < n; r++) pairLineOps([{ type: 'del', text: al[a0 + r] }, { type: 'ins', text: bl[b0 + r] }], push)
    } else {
      push('del', al.slice(a0, a1).join('')); push('ins', bl.slice(b0, b1).join(''))
    }
    return
  }
  let pa = a0
  let pb = b0
  for (const { ia, ib } of anchors) {
    diffLineRange(al, pa, ia, bl, pb, ib, push)
    push('keep', al[ia])
    pa = ia + 1; pb = ib + 1
  }
  diffLineRange(al, pa, a1, bl, pb, b1, push)
}

/** Candidates come in increasing ia; take the longest subsequence with ib increasing too (standard LIS, O(k log k)). */
function longestIncreasing(cand: { ia: number; ib: number }[]): { ia: number; ib: number }[] {
  const tails: number[] = []          // tails[len-1] = index of the smallest ending ib among increasing subsequences of length len
  const prev = new Array<number>(cand.length).fill(-1)
  for (let k = 0; k < cand.length; k++) {
    let lo = 0
    let hi = tails.length
    while (lo < hi) { const mid = (lo + hi) >> 1; if (cand[tails[mid]].ib < cand[k].ib) lo = mid + 1; else hi = mid }
    if (lo > 0) prev[k] = tails[lo - 1]
    tails[lo] = k
  }
  const out: { ia: number; ib: number }[] = []
  for (let k = tails.length ? tails[tails.length - 1] : -1; k >= 0; k = prev[k]) out.push(cand[k])
  return out.reverse()
}

/** Pair "consecutive del lines" with the immediately following "consecutive ins lines": if the counts are equal, compare line by line, word by word */
function pairLineOps(ops: DiffPart[], push: Push) {
  let k = 0
  while (k < ops.length) {
    if (ops[k].type !== 'del') { push(ops[k].type, ops[k].text); k++; continue }
    const dels: string[] = []
    while (k < ops.length && ops[k].type === 'del') dels.push(ops[k++].text)
    const inss: string[] = []
    while (k < ops.length && ops[k].type === 'ins') inss.push(ops[k++].text)
    if (dels.length === inss.length) {
      for (let r = 0; r < dels.length; r++) {
        const sa = segment(dels[r])
        const sb = segment(inss[r])
        if (sa.length * sb.length > LINE_LCS_CELLS) { push('del', dels[r]); push('ins', inss[r]) }
        else lcs(sa, sb, push)
      }
    } else {
      for (const d of dels) push('del', d)
      for (const x of inss) push('ins', x)
    }
  }
}

// ---------------------------------------------------------------- hunk model

/** One change. ``from``/``to`` are **live positions in the document**: mapped through every document change,
 * so the user can edit inside a green insertion and accept afterwards. ``del`` is the deleted original text
 * (it is no longer in the document and can only be shown by a widget; it is also what gets written back on revert). */
export type Hunk = {
  id: number; from: number; to: number; del: string
  /** Only whitespace differs (spaces / blank lines added by formatting): position recorded, revert restores, but not drawn green and no hover bar. */
  soft?: boolean
  /** Which proposal layer it belongs to (see Layer). toHunks gives 0; rewritten to the current layer when entering the field. */
  layer?: number
  /** A layer turned off: this change has already been restored to the original (from..to now holds del), and ins is the new text taken off when turning it off,
   *  written back by position when turned on again. Turned-off ones are not drawn, get no hover bar, and do not count as pending. */
  off?: boolean
  ins?: string
}


export type Layer = { id: number; label: string; at: number; key?: string }


export type Settled = {
  layer: number; label: string; at: number
  state: 'accepted' | 'reverted'
  del: string; ins: string; soft?: boolean
}

/** The value the layer above uses to push a new proposal layer into the editor: dispatched only when seq changes (React prop comparison).
 *  replace = clear existing layers first, then add (Smart Continue recomputes from the start of the whole run every round, cumulatively, so layers must not stack). */
export type DiffPush = { label: string; parts: DiffPart[]; seq: number; replace?: boolean }

/** Two adjacent changes with no more than this many untouched characters between them are merged into one.
 * 8 characters is roughly "changed a word, a few characters later changed another" -- any larger would
 * tie two unrelated edits together, and the user could not accept just one of them. */
const MERGE_GAP = 8

/** Old interface: clear all layers and build one "Changes" layer from this diff. */
export const setRoundDiff = StateEffect.define<DiffPart[] | null>()
/** Add a proposal layer (existing layers untouched; their positions have already been mapped through the document changes before this transaction). */
export const addLayer = StateEffect.define<{ label: string; parts: DiffPart[]; replace?: boolean }>()
/** Accept a whole layer: remove all its hunks, keep the body as is. Reverting a whole layer is done by the caller dispatching each change + dropHunk. */
export const acceptLayer = StateEffect.define<number>()
/** Turn off one change (in the same transaction as restoring it): the position is given directly, not mapped -- this transaction changes exactly that. */
export const shelveHunk = StateEffect.define<{ id: number; from: number; ins: string }>()
/** Turn one change on again (in the same transaction as writing it back). */
export const unshelveHunk = StateEffect.define<{ id: number; from: number }>()
/** Accept: just remove this change from the pending list; the body stays as is. */
export const acceptHunk = StateEffect.define<number>()
/** Revert: dispatched together with a document change (from..to swapped back to del); this only removes the marker. */
export const dropHunk = StateEffect.define<number>()
export const acceptAllHunks = StateEffect.define<null>()


export const restoreLayers = StateEffect.define<{
  layers: { key: string; label: string; at: number }[]
  hunks: { key: string; from: number; to: number; del: string; ins?: string; off?: boolean; soft?: boolean }[]
  settled: { key: string; state: 'accepted' | 'reverted'; del: string; ins: string; soft?: boolean }[]
}>()

/** Diff result -> hunk list.
 *
 * **An adjacent del + ins merge into one change**: that is one "replacement", which the user wants to accept or revert
 * as one thing; split in two, clicking accept would leave half a strikethrough hanging there. */
export function toHunks(parts: DiffPart[] | null): Hunk[] {
  if (!parts?.length) return []
  const out: Hunk[] = []
  let pos = 0
  let id = 0
  // The "untouched" text since the previous change. CJK is diffed **per character** (splitting by whole sentence
  // would mark a whole passage red and green for one changed word, hiding what moved); the cost is that two nearby date phrases
  // split into two changes each covering one character -- too fine-grained for hover actions. Two changes very close together merge into
  // one: the merged del must include the untouched text in between, so revert can restore exactly.
  let gap = ''
  const push = (h: Omit<Hunk, 'id'>) => {
    const prev = out[out.length - 1]
    if (prev && gap.length <= MERGE_GAP && prev.to + gap.length === h.from) {
      prev.to = h.to
      prev.del = prev.del + gap + h.del
      prev.soft = !!(prev.soft && h.soft)
    } else {
      out.push({ id: id++, ...h })
    }
    gap = ''
  }
  const soft = (del: string, ins: string) => !del.trim() && !ins.trim()
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i]
    if (p.type === 'keep') { pos += p.text.length; gap += p.text; continue }
    if (p.type === 'del') {
      const next = parts[i + 1]
      if (next?.type === 'ins') {                 // replacement: merge into one change
        push({ from: pos, to: pos + next.text.length, del: p.text, soft: soft(p.text, next.text) })
        pos += next.text.length
        i++
      } else {
        push({ from: pos, to: pos, del: p.text, soft: soft(p.text, '') })
      }
      continue
    }
    push({ from: pos, to: pos + p.text.length, del: '', soft: soft('', p.text) })
    pos += p.text.length
  }
  return out
}

// ---------------------------------------------------------------- decorations

/** The deleted original text -- no longer in the document, so a widget restores it in place. */
class DeletedWidget extends WidgetType {
  constructor(readonly text: string, readonly id: number) { super() }
  eq(other: DeletedWidget) { return other.text === this.text && other.id === this.id }
  toDOM() {
    const span = document.createElement('span')
    span.className = 'harness-del'
    // Large deletions (a whole outline rewritten) fold into a small tag, hover to see the original; stuffing hundreds of characters of struck-through original

    // six rounds the bottom of the body was piled with the whole deleted old outline).
    const txt = this.text.replace(/\s+/g, ' ').trim()
    if (txt.length > 40) {
      span.classList.add('harness-del-pill')
      span.textContent = t('{n} chars deleted', { n: txt.length })
      span.title = t('Deleted in this round:') + '\n' + this.text.slice(0, 600) + (this.text.length > 600 ? '…' : '')
    } else {
      span.textContent = txt
      span.title = t('Deleted in this round')
    }
    return span
  }
  ignoreEvent() { return true }
}

function build(hunks: Hunk[], layers: Layer[] = []): DecorationSet {
  const decos: Range<Decoration>[] = []
  const label = (h: Hunk) => { const l = layers.find((x) => x.id === h.layer)?.label; return l ? t(l) : t('This round') }
  for (const h of hunks) {
    if (h.soft || h.off) continue                 // whitespace only / turned-off layer: not drawn
    if (h.del) {
      decos.push(Decoration.widget({ widget: new DeletedWidget(h.del, h.id), side: -1 })
        .range(h.from))
    }
    if (h.to > h.from) {
      decos.push(Decoration.mark({
        class: 'harness-ins',
        attributes: { title: t('{label} · added content', { label: label(h) }) },
      }).range(h.from, h.to))
    }
  }
  return Decoration.set(decos, true)
}

let nextHunkId = 1
let nextLayerId = 1


function layerKey(): string {
  try {
    const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto
    if (c?.randomUUID) return c.randomUUID().replace(/-/g, '').slice(0, 12)
  } catch { /* none, never mind */ }
  return (Date.now().toString(36) + Math.random().toString(36).slice(2, 8)).slice(-12)
}

/** Build a batch of diffs into hunks with a layer id: positions clamped to the document length (the diff was computed from liveContentRef,
 *  and the editor may not have caught up -- an out-of-range position makes the next mapPos throw RangeError, unmounting the whole React tree,
 *  and the user sees a white screen); ids use a global counter (hunks from several layers mix, so they cannot each start at 0). */
function hunksForLayer(parts: DiffPart[] | null, layer: number, docLen: number): Hunk[] {
  return toHunks(parts)
    .map((h) => ({ ...h, id: nextHunkId++, layer, from: Math.min(h.from, docLen), to: Math.min(h.to, docLen) }))
    .filter((h) => h.to > h.from || h.del)
}

// ---------------------------------------------------------------- state

export const roundDiffField = StateField.define<{ hunks: Hunk[]; layers: Layer[]; decos: DecorationSet; settled: Settled[] }>({
  create() { return { hunks: [], layers: [], decos: Decoration.none, settled: [] } },
  update(value, tr) {
    for (const e of tr.effects) {
      if (e.is(setRoundDiff)) {
        const layer: Layer = { id: nextLayerId++, label: 'Changes', at: Date.now(), key: layerKey() }
        const hunks = hunksForLayer(e.value, layer.id, tr.newDoc.length)
        return { hunks, layers: hunks.length ? [layer] : [], decos: build(hunks, [layer]), settled: [] }
      }
      // "Accept all" = burn into the body; this note's layers end here: clear the handled-changes ledger too.

      if (e.is(acceptAllHunks)) return { hunks: [], layers: [], decos: Decoration.none, settled: [] }
      if (e.is(restoreLayers)) {
        const byKey = new Map<string, Layer>()
        const nextLayers: Layer[] = e.value.layers.map((l) => {
          const made: Layer = { id: nextLayerId++, label: l.label, at: l.at, key: l.key }
          byKey.set(l.key, made)
          return made
        })
        const len = tr.newDoc.length
        const nextHunks: Hunk[] = e.value.hunks
          .filter((h) => byKey.has(h.key))
          .map((h) => ({
            id: nextHunkId++, layer: byKey.get(h.key)!.id,
            from: Math.min(h.from, len), to: Math.min(h.to, len),
            del: h.del, ins: h.ins, off: h.off, soft: h.soft,
          }))
          .filter((h) => h.to > h.from || h.del || h.off)
        const nextSettled: Settled[] = e.value.settled
          .filter((s) => byKey.has(s.key))
          .map((s) => {
            const l = byKey.get(s.key)!
            return { layer: l.id, label: l.label, at: l.at, state: s.state, del: s.del, ins: s.ins, soft: s.soft }
          })
        // Layers with no live change and no handled-changes ledger are not put in (an empty card means nothing)
        const useful = new Set([...nextHunks.map((h) => h.layer), ...nextSettled.map((s) => s.layer)])
        const keptLayers = nextLayers.filter((l) => useful.has(l.id))
        return { hunks: nextHunks, layers: keptLayers, decos: build(nextHunks, keptLayers), settled: nextSettled }
      }
    }
    let hunks = value.hunks
    let layers = value.layers
    let settled = value.settled
    const shelve = new Map<number, { from: number; ins: string }>()
    const unshelve = new Map<number, number>()

    const settle = (h: Hunk, state: 'accepted' | 'reverted') => {
      const l = layers.find((x) => x.id === h.layer)
      settled = [...settled, {
        layer: h.layer ?? 0, label: l?.label ?? 'Changes', at: l?.at ?? Date.now(), state,
        del: h.del, ins: h.off ? (h.ins ?? '') : tr.startState.doc.sliceString(
          Math.min(h.from, tr.startState.doc.length), Math.min(h.to, tr.startState.doc.length)),
        soft: h.soft,
      }]
    }
    for (const e of tr.effects) {
      if (e.is(acceptHunk)) { const h = hunks.find((x) => x.id === e.value); if (h) settle(h, 'accepted') }
      if (e.is(dropHunk)) { const h = hunks.find((x) => x.id === e.value); if (h) settle(h, 'reverted') }
      if (e.is(acceptLayer)) for (const h of hunks.filter((x) => x.layer === e.value)) settle(h, 'accepted')
      if (e.is(acceptHunk) || e.is(dropHunk)) hunks = hunks.filter((h) => h.id !== e.value)
      if (e.is(acceptLayer)) hunks = hunks.filter((h) => h.layer !== e.value)
      if (e.is(shelveHunk)) shelve.set(e.value.id, e.value)
      if (e.is(unshelveHunk)) unshelve.set(e.value.id, e.value.from)
    }
    if (shelve.size || unshelve.size) {
      // The change turned off / on: this transaction changes exactly that, so the position comes from the effect, not from mapping
      hunks = hunks.map((h) => {
        const s = shelve.get(h.id)
        if (s) return { ...h, from: s.from, to: s.from + h.del.length, off: true, ins: s.ins }
        const u = unshelve.get(h.id)
        if (u !== undefined) return { ...h, from: u, to: u + (h.ins ?? '').length, off: false, ins: undefined }
        return h
      })
    }
    if (tr.docChanged && hunks.length) {
      // **Map through document changes rather than dropping highlights.** When the user types inside a green insertion this change
      // must grow with it, so both ends use assoc 1:
      //   from=1 -> text inserted exactly at the start goes **outside** this change (typing before a change is not part of it)
      //   to  =1 -> text inserted exactly at the end goes **inside** this change (continuing at the end is part of it)
      // The first version used -1 for to, with a comment saying "let insertions land inside the range" -- the code was backwards:
      // adding a character at the end of a green insertion excluded that character, so accepting after editing accepted only part.
      // By the same logic: a hunk positioned past the pre-change document length makes mapPos throw. Clamp to the old document length first.
      const oldLen = tr.startState.doc.length
      hunks = hunks
        .map((h) => (shelve.has(h.id) || unshelve.has(h.id) ? h : {
          ...h,
          from: tr.changes.mapPos(Math.min(h.from, oldLen), 1),
          to: tr.changes.mapPos(Math.min(h.to, oldLen), 1),
        }))
        // The insertion was entirely deleted by the user and there is no original to revert to -- this change no longer exists (turned-off layers stay: their ins can still be written back)
        .filter((h) => h.to >= h.from && (h.to > h.from || h.del || h.off))
    }
    // Adding a layer: after document mapping -- the new layer's positions are computed against the document after this transaction, old layers were just mapped,
    // so both share the same coordinates. replace = the cumulative diff of Smart Continue: clear first, then add.
    for (const e of tr.effects) {
      if (e.is(addLayer)) {
        if (e.value.replace) { hunks = []; layers = []; settled = [] }
        const layer: Layer = { id: nextLayerId++, label: e.value.label, at: Date.now(), key: layerKey() }
        const fresh = hunksForLayer(e.value.parts, layer.id, tr.newDoc.length)
        if (fresh.length) { hunks = [...hunks, ...fresh]; layers = [...layers, layer] }
      }
    }

    // should not vanish from the panel; it still carries "2 accepted · 1 reverted", three decisions the user really made.
    const live = new Set<number | undefined>([
      ...hunks.map((h) => h.layer),
      ...settled.map((s) => s.layer),
    ])
    if (layers.some((l) => !live.has(l.id))) layers = layers.filter((l) => live.has(l.id))
    if (hunks === value.hunks && layers === value.layers && settled === value.settled) return value
    return { hunks, layers, decos: build(hunks, layers), settled }
  },
  provide: (f) => EditorView.decorations.from(f, (v) => v.decos),
})

/** How many changes remain unhandled. Used upstream to show "N changes this round". Turned-off layers count too -- they still wait to be accepted / discarded;
 *  if not counted, turning off a whole layer would make the "Changes" tag disappear, and the user could not find where to turn it back on. */
export function pendingHunks(view: EditorView): number {
  return view.state.field(roundDiffField, false)?.hunks.filter((h) => !h.soft).length ?? 0
}


export function layersOf(host: Host): (Layer & { count: number; off: boolean })[] {
  const st = host.state.field(roundDiffField, false)
  if (!st) return []
  return st.layers
    .filter((l) => st.hunks.some((h) => h.layer === l.id))
    .map((l) => {
      const mine = st.hunks.filter((h) => h.layer === l.id)
      return { ...l, count: mine.filter((h) => !h.soft).length, off: mine.length > 0 && mine.every((h) => h.off) }
    })
}


export function settledOf(host: Host): { id: number; key?: string; label: string; at: number; accepted: number; reverted: number; live: number }[] {
  const st = host.state.field(roundDiffField, false)
  if (!st) return []
  return st.layers
    .map((l) => {
      const mine = st.settled.filter((s) => s.layer === l.id)
      return {
        id: l.id, key: l.key, label: l.label, at: l.at,
        accepted: mine.filter((s) => s.state === 'accepted').length,
        reverted: mine.filter((s) => s.state === 'reverted').length,
        live: st.hunks.filter((h) => h.layer === l.id && !h.soft).length,
      }
    })
    .filter((x) => x.accepted || x.reverted)
}

/** Something that can dispatch: an EditorView, or a state-only shell in tests. */
export type Host = { state: EditorState; dispatch: (spec: TransactionSpec) => void }

/** Revert a whole layer: restore each of its changes (back to front, so positions do not shift). */
export function dropLayer(host: Host, layerId: number) {
  const st = host.state.field(roundDiffField, false)
  if (!st) return
  const hunks = st.hunks.filter((h) => h.layer === layerId).sort((a, b) => b.from - a.from)
  for (const h of hunks) {
    const cur = host.state.field(roundDiffField).hunks.find((x) => x.id === h.id)
    if (!cur) continue
    if (cur.off) { host.dispatch({ effects: dropHunk.of(h.id) }); continue }   // turned off: the body already holds the original, just forget it
    host.dispatch({ changes: { from: cur.from, to: cur.to, insert: cur.del }, effects: dropHunk.of(h.id) })
  }
}

/** Turn off a layer: restore each change to the original, but remember what it changed to -- "turn off and on again" (agent-native-editor §3.2:
 *  proposals are toggleable layers, not one-shot accept / revert). */
export function turnLayerOff(host: Host, layerId: number) {
  const st = host.state.field(roundDiffField, false)
  if (!st) return
  const hunks = st.hunks.filter((h) => h.layer === layerId && !h.off).sort((a, b) => b.from - a.from)
  for (const h of hunks) {
    const cur = host.state.field(roundDiffField).hunks.find((x) => x.id === h.id)
    if (!cur || cur.off) continue
    const ins = host.state.doc.sliceString(cur.from, cur.to)
    host.dispatch({ changes: { from: cur.from, to: cur.to, insert: cur.del }, effects: shelveHunk.of({ id: h.id, from: cur.from, ins }) })
  }
}

/** Turn a layer on again: write each remembered new text back. A change whose original was edited by the user (no longer matches del)
 *  cannot be replayed; it is dropped and counted -- the caller uses that to say "N changes could not be replayed because the original was edited". */
export function turnLayerOn(host: Host, layerId: number): { replayed: number; lost: number } {
  const st = host.state.field(roundDiffField, false)
  if (!st) return { replayed: 0, lost: 0 }
  const hunks = st.hunks.filter((h) => h.layer === layerId && h.off).sort((a, b) => b.from - a.from)
  let replayed = 0
  let lost = 0
  for (const h of hunks) {
    const cur = host.state.field(roundDiffField).hunks.find((x) => x.id === h.id)
    if (!cur || !cur.off) continue
    const ok = cur.to <= host.state.doc.length && host.state.doc.sliceString(cur.from, cur.to) === cur.del
    if (!ok) { host.dispatch({ effects: dropHunk.of(h.id) }); lost++; continue }
    host.dispatch({ changes: { from: cur.from, to: cur.to, insert: cur.ins ?? '' }, effects: unshelveHunk.of({ id: h.id, from: cur.from }) })
    replayed++
  }
  return { replayed, lost }
}

// ---------------------------------------------------------------- hover toolbar

/** Why "Accept / Revert" uses a tooltip rather than a widget in the body shown by a CSS adjacent
 * selector:
 *
 * **CM6 inserts `<img class="cm-widgetBuffer">` on both sides of a non-editable inline widget**
 * (working around a browser bug when the cursor hugs the widget), so the real DOM is
 * `…<span class="harness-ins">…</span><img class="cm-widgetBuffer"><span class="harness-actions">`,
 * and `.harness-ins:hover + .harness-actions` never matches -- the buttons never appear.
 * And the buffer is inserted case by case, so `+ img + span` is just as fragile.
 *
 * Switched to JS deciding which change is hovered + tooltip positioning, independent of what the DOM looks like.
 */
/** Exported only for testing: this UI broke in two versions (build passed, buttons never appeared),
 * and scripts/check-diff-ui.mts needs to construct hover state directly to verify the tooltip. */
export const setHover = StateEffect.define<number | null>()

const hoverField = StateField.define<number | null>({
  create: () => null,
  update(v, tr) {
    for (const e of tr.effects) if (e.is(setHover)) return e.value
    // Once this change has been accepted/reverted, the toolbar should no longer hang around
    for (const e of tr.effects) {
      if ((e.is(acceptHunk) || e.is(dropHunk)) && e.value === v) return null
    }
    if (tr.effects.some((e) => e.is(setRoundDiff) || e.is(acceptAllHunks) || e.is(acceptLayer))) return null
    return v
  },
})

function actionsDom(view: EditorView, h: Hunk): HTMLElement {
  const wrap = document.createElement('div')
  wrap.className = 'harness-actions'
  const mk = (label: string, title: string, cls: string, run: () => void) => {
    const b = document.createElement('button')
    b.type = 'button'
    b.className = cls
    b.textContent = label
    b.title = title
    // mousedown + preventDefault: before click the editor would move focus and selection to the button,
    // and the cursor position in the body would be lost.
    b.addEventListener('mousedown', (e) => {
      e.preventDefault()
      e.stopPropagation()
      pinned = false
      keepHover = false
      run()
    })
    return b
  }
  wrap.append(
    mk('✓ ' + t('Accept'), t('Keep this change'), 'harness-accept',
      () => view.dispatch({ effects: acceptHunk.of(h.id) })),
    mk(h.del ? '↩ ' + t('Revert') : '↩ ' + t('Remove'), h.del ? t('Restore the original text') : t('Remove this addition'), 'harness-reject',
      () => {
        const cur = view.state.field(roundDiffField).hunks.find((x) => x.id === h.id)
        if (!cur) return
        // Revert is a real document change: swap from..to back to the deleted original. In the same transaction
        // include dropHunk, and the remaining hunks are mapped through this change.
        view.dispatch({
          changes: { from: cur.from, to: cur.to, insert: cur.del },
          effects: dropHunk.of(h.id),
        })
      }),
  )
  wrap.addEventListener('mouseenter', () => { keepHover = true; cancelClear() })
  wrap.addEventListener('mouseleave', () => { keepHover = false; scheduleClear(view) })
  return wrap
}

// Whether the mouse is resting on the toolbar right now. There is only one editor instance, so module-level state is enough.
let keepHover = false
let clearTimer: ReturnType<typeof setTimeout> | null = null

function cancelClear() {
  if (clearTimer) { clearTimeout(clearTimer); clearTimer = null }
}

/** Close the toolbar **with a delay** after the mouse leaves a change.
 *
 * Without the delay it could never be clicked: the toolbar floats **above** the change, and moving the mouse up first passes over the previous line
 * of ordinary text; that mousemove decides "not on any change" and closes it immediately -- what the user sees
 * is "it floats up, but vanishes the moment you reach for it". 220ms is enough to cover that short distance, yet short enough not to
 * drag an unshakable overlay across the body. */
function scheduleClear(view: EditorView) {
  cancelClear()
  clearTimer = setTimeout(() => {
    clearTimer = null
    if (keepHover || pinned) return
    if (view.state.field(hoverField, false) != null) view.dispatch({ effects: setHover.of(null) })
  }, 220)
}

const hunkTooltip = showTooltip.compute([roundDiffField, hoverField], (state): Tooltip | null => {
  const id = state.field(hoverField)
  if (id == null) return null
  const h = state.field(roundDiffField).hunks.find((x) => x.id === id)
  if (!h) return null
  return {
    pos: h.from,
    end: h.to,
    above: true,
    arrow: false,
    create: (view) => ({ dom: actionsDom(view, h) }),
  }
})

/** Pin: click a change and the toolbar no longer disappears by itself.
 *
 * The hover path depends on timing along the way "from text to overlay"; the grace period only widens the window,
 * it is still a timing problem. Pinning by click depends on no timing -- the buttons can always be clicked.
 * Esc, clicking elsewhere, or finishing accept/revert all unpin. */
let pinned = false

/** Hover detection. posAtCoords asks directly "where in the document is the mouse", more reliable than reading DOM structure. */
const hoverWatcher = EditorView.domEventHandlers({
  mousedown(e, view) {
    if (e.button !== 0) return false
    const hunks = view.state.field(roundDiffField, false)?.hunks
    if (!hunks?.length) return false
    const pos = view.posAtCoords({ x: e.clientX, y: e.clientY })
    const hit = pos == null ? null : hunks.find((h) => !h.soft && !h.off && pos >= h.from - 1 && pos <= h.to + 1)
    cancelClear()
    pinned = !!hit
    const next = hit ? hit.id : null
    if (next !== view.state.field(hoverField)) view.dispatch({ effects: setHover.of(next) })
    return false                                   // do not intercept: the cursor lands where it should
  },
  keydown(e, view) {
    if (e.key !== 'Escape') return false
    if (view.state.field(hoverField) == null) return false
    pinned = false
    view.dispatch({ effects: setHover.of(null) })
    return true
  },
  mousemove(e, view) {
    const hunks = view.state.field(roundDiffField, false)?.hunks
    if (!hunks?.length) return false
    const pos = view.posAtCoords({ x: e.clientX, y: e.clientY })
    // Widen by one character on each side: resting exactly on a change boundary also counts as a hit, otherwise edges are hard to hover
    const hit = pos == null ? null : hunks.find((h) => !h.soft && !h.off && pos >= h.from - 1 && pos <= h.to + 1)
    const next = hit ? hit.id : null
    if (next != null) {
      cancelClear()
      if (next !== view.state.field(hoverField)) view.dispatch({ effects: setHover.of(next) })
      return false
    }
    if (pinned) return false                       // pinned: do not follow the mouse
    // Left the change: **do not close immediately**; allow enough time to move the mouse onto the toolbar
    if (view.state.field(hoverField) != null && !keepHover) scheduleClear(view)
    return false
  },
  mouseleave(_e, view) {
    // Also delayed: CM6's tooltip hangs outside the editor DOM, so moving the mouse from the body to the toolbar
    // first fires this mouseleave; closing immediately would make the buttons forever out of reach.
    if (!keepHover) scheduleClear(view)
    return false
  },
})

/** The complete extension installed in the editor: highlights + hover toolbar. */
export const roundDiff = [roundDiffField, hoverField, hunkTooltip, hoverWatcher]
