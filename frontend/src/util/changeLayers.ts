
import type { EditorState } from '@codemirror/state'
import { ZH } from '../i18n/zh'
import { roundDiffField, type Hunk, type Settled } from '../editor/roundDiff'
import { SLASH_ITEMS } from '../editor/slashMenu'
import { t } from '../i18n'

/** What a stored change looks like. The four values of `state` match backend `store.HUNK_STATES` verbatim. */
export type SavedHunk = {
  k: number
  from: number
  to: number
  del: string
  ins: string
  state: 'pending' | 'off' | 'accepted' | 'reverted'
  soft?: boolean
  /** A short piece of body **before / after** this change when this version was stored. Used to relocate after the body was edited elsewhere. */
  before?: string
  after?: string
}

/** What a stored layer looks like. Columns map one to one to backend `note_change_layers`. */
export type SavedLayer = {
  id: string
  label: string
  source: string
  run_id?: string
  round_no?: number
  seq: number
  state: 'on' | 'off'
  at: string
  content_tag: string
  hunks: SavedHunk[]
}

/** How many characters of context to take. The same numbers as `editor/undoRound` (24 / 12 / 6 / 0, shortening step by step) --
 *  both solve the same problem: **only text can locate across a restart, coordinates cannot**. */
const CONTEXT = 24
const FALLBACKS = [24, 12, 6, 0]

/** Fingerprint of the body: length + FNV-1a.
 *
 * **Not a cryptographic hash**, and it need not be: its only use is answering "is the body still the one from when this version was stored".
 * With `crypto.subtle` this step would become async, while it sits in the middle of a synchronous dispatch.
 * Length goes along: the cost of one FNV collision is "highlights marked on other text by old coordinates", and adding the length all but closes it. */
export function contentTag(s: string): string {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return `${s.length}:${h.toString(36)}`
}


export function appendedTo(savedTag: string, doc: string): boolean {
  const i = (savedTag || '').indexOf(':')
  if (i <= 0) return false
  const n = Number(savedTag.slice(0, i))
  if (!Number.isInteger(n) || n < 0 || n > doc.length) return false
  return contentTag(doc.slice(0, n)) === savedTag
}

/** Machine code of a layer's source. The value table is backend `store.CHANGE_LAYER_SOURCES`, matching verbatim on both sides
 *  (watched by `scripts/check-change-layers.mts`).
 *
 *  **Unrecognized ones become `other`, not dropped** -- dropping would be another silent "Accept". */
export function layerSource(label: string): string {
  const raw = (label ?? '').trim()
  // Layers stored before the English source text (and labels made in the Chinese UI) carry the Chinese label: map it back to its English key
  // Persisted labels remain valid even if the current UI dictionary changes wording.
  const s = raw === '\u683c\u5f0f\u5316' ? 'Format' : (LEGACY_LABELS.get(raw) ?? raw)
  if (s.startsWith('Undo round') || s.startsWith('\u64a4\u6389\u7b2c')) return 'undo_round'
  if (s === 'Smart Continue' || s === 'Polish pass') return 'round'
  if (s === 'Continue') return 'continue'
  if (s === 'Rewrite') return 'rewrite'
  if (s === 'Polish') return 'polish'
  if (s === 'Expand context' || s === 'Expand') return 'expand'
  if (s === 'Format') return 'format'
  if (s === 'Smart layout') return 'restructure'
  if (s === 'Voice input' || s === 'Insert audio') return 'voice'
  if (s === 'Image to table') return 'table'
  if (BLOCK_LABELS.has(s)) return 'block'
  return 'other'
}

/** The items in the `/` menu that produce a layer. **Computed directly from `SLASH_ITEMS`**, not a separate copy of the list:
 *  with a copy, a new menu item forgotten here would quietly fall into `other` --
 *  an outdated list is worse than no list (the opening line of `check-api-wired`). */
export const BLOCK_LABELS = new Set(
  SLASH_ITEMS.filter((i) => i.group === 'AI').map((i) => i.label))

/** Chinese label -> English key for every label `layerSource` recognizes (from the zh dictionary, so the two cannot drift). */
const LEGACY_LABELS = new Map(
  ['Smart Continue', 'Polish pass', 'Continue', 'Rewrite', 'Polish', 'Expand context', 'Expand', 'Format', 'Smart layout',
    'Voice input', 'Insert audio', 'Image to table', ...BLOCK_LABELS]
    .filter((k) => ZH[k]).map((k) => [ZH[k], k] as const))

function ctxBefore(doc: string, pos: number): string {
  return doc.slice(Math.max(0, pos - CONTEXT), pos)
}
function ctxAfter(doc: string, pos: number): string {
  return doc.slice(pos, pos + CONTEXT)
}

/** The layers the editor currently has -> rows that can be stored.
 *
 * Three things go together: **every live change** (`pending` / `off`), **every change the user already handled**
 * (`accepted` / `reverted`, from the `settled` ledger of `roundDiffField`), and the layer order and `at`.
 * Without that last ledger, "the per-change clicks" could never be written to the library -- exactly the bug this batch fixes. */
export function serializeLayers(state: EditorState): SavedLayer[] {
  const st = state.field(roundDiffField, false)
  if (!st) return []
  const doc = state.doc.toString()
  const tag = contentTag(doc)
  const out: SavedLayer[] = []
  st.layers.forEach((l, i) => {
    const live: Hunk[] = st.hunks.filter((h) => h.layer === l.id)
    const done: Settled[] = st.settled.filter((s) => s.layer === l.id)
    if (!live.length && !done.length) return
    const hunks: SavedHunk[] = []
    live.forEach((h, k) => {
      const ins = h.off ? (h.ins ?? '') : doc.slice(h.from, h.to)
      hunks.push({
        k, from: h.from, to: h.to, del: h.del, ins,
        state: h.off ? 'off' : 'pending',
        soft: h.soft,
        before: ctxBefore(doc, h.from),
        after: ctxAfter(doc, h.to),
      })
    })
    done.forEach((s, k) => {
      hunks.push({ k: live.length + k, from: 0, to: 0, del: s.del, ins: s.ins, state: s.state, soft: s.soft })
    })
    out.push({
      // `key` is fixed when the layer is born and stable across restarts; falling back to `l${id}` is only a safety net (a module-level counter
      // as primary key adds a row on every save); today all three layer-creating paths fill in `key`.
      id: l.key ?? `l${l.id}`,
      label: l.label,
      source: layerSource(l.label),
      seq: i,
      // Whole layer on / off: the whole layer is off only when every change is off, word for word the same rule as `layersOf`
      state: live.length > 0 && live.every((h) => h.off) ? 'off' : 'on',
      at: new Date(l.at).toISOString(),
      content_tag: tag,
      hunks,
    })
  })
  return out
}

/** What to say when a change cannot be found in the body again. **No guessing** -- a wrong guess marks highlights on other text. */
export type Relocation =
  | { ok: true; from: number; to: number }
  | { ok: false; why: string }

/** Relocate a change by text (after the body was edited elsewhere).
 *
 * The same approach as `editor/undoRound`: search the body for "before context + what this change should look like now + after context",
 * **only a unique hit counts**; if not found, shorten the context one step and search again (24 -> 12 -> 6 -> 0);
 * multiple hits / no hit both count as conflicts. Pure deletions (where this change is now an empty string) **may not use 0 context**,
 * since an empty string has countless positions in any body. */
export function relocate(doc: string, h: SavedHunk): Relocation {
  const want = h.state === 'off' ? h.del : h.ins
  const before = h.before ?? ''
  const after = h.after ?? ''
  for (const n of FALLBACKS) {
    if (n === 0 && !want) break
    const lead = n ? before.slice(-n) : ''
    const tail = n ? after.slice(0, n) : ''
    const needle = lead + want + tail
    if (!needle) continue
    let first = -1
    let count = 0
    let at = doc.indexOf(needle)
    while (at >= 0) {
      count++
      if (first < 0) first = at
      if (count > 1) break
      at = doc.indexOf(needle, at + 1)
    }
    if (count === 1) return { ok: true, from: first + lead.length, to: first + lead.length + want.length }
  }
  const shown = (want || h.del).replace(/\s+/g, ' ').trim().slice(0, 18)
  return { ok: false, why: shown ? `“${shown}”` : t('an empty change') }
}

export type Restored = {
  layers: { key: string; label: string; at: number }[]
  hunks: { key: string; from: number; to: number; del: string; ins?: string; off?: boolean; soft?: boolean }[]
  settled: { key: string; state: 'accepted' | 'reverted'; del: string; ins: string; soft?: boolean }[]
  /** The changes that did not match and were not put back. **Must be said**, not quietly a few fewer. */
  conflicts: string[]

  stuck: { id: string; label: string; why: string[] }[]
}

/** Rows from the library -> something that can go into the editor.
 *
 * If the body is still the one from when this version was stored (`content_tag` matches), put it back by coordinates directly -- that is **exact**;
 * only when it does not match (this note was edited elsewhere, or the last version was not saved in time) relocate change by change by text.
 * A change neither path can place is **not put back**, and `conflicts` says which one. */
export function restoreLayers(saved: SavedLayer[], doc: string): Restored {
  const tag = contentTag(doc)
  const out: Restored = { layers: [], hunks: [], settled: [], conflicts: [], stuck: [] }
  for (const l of saved ?? []) {
    const at = Date.parse(l.at)
    out.layers.push({ key: l.id, label: l.label, at: Number.isFinite(at) ? at : Date.now() })
    // The body is untouched, or **only appended to at the end** (`appendedTo`): existing coordinates are all still accurate.

    const coordsValid = l.content_tag === tag || appendedTo(l.content_tag, doc)
    const why: string[] = []
    for (const h of l.hunks ?? []) {
      if (h.state === 'accepted' || h.state === 'reverted') {
        out.settled.push({ key: l.id, state: h.state, del: h.del, ins: h.ins, soft: h.soft })
        continue
      }
      const want = h.state === 'off' ? h.del : h.ins
      const exact = coordsValid && doc.slice(h.from, h.from + want.length) === want
      const at2: Relocation = exact
        ? { ok: true, from: h.from, to: h.from + want.length }
        : relocate(doc, h)
      if (!at2.ok) {
        out.conflicts.push(`${l.label}: ${at2.why}`)
        why.push(at2.why)
        continue
      }
      out.hunks.push({
        key: l.id, from: at2.from, to: at2.to, del: h.del,
        ins: h.state === 'off' ? h.ins : undefined,
        off: h.state === 'off' ? true : undefined,
        soft: h.soft,
      })
    }
    if (why.length) out.stuck.push({ id: l.id, label: l.label, why })
  }
  return out
}

/** Whether two stored layers differ. **Ask this before writing**: if no position drifted and no state changed, not a byte is sent. */
export function sameLayers(a: SavedLayer[], b: SavedLayer[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}


export function reopenedLayersNotice(r: Restored): { text: string; kind: 'info' | 'error' } | null {
  const live = new Set(r.hunks.map((h) => h.key)).size
  if (r.conflicts.length) {
    const head = live ? t('Reopened {n} layers of unresolved changes; ', { n: live }) : ''
    return {
      kind: 'error',
      text: head + t('{n} could not be placed back because the text has changed', { n: r.conflicts.length })
        + t(' — recompute or discard them in the Changes tab: {list}', { list: r.conflicts.slice(0, 2).join('; ') }),
    }
  }
  return live ? { kind: 'info', text: t('{n} layers of changes left unresolved last time are still in the Changes tab', { n: live }) } : null
}


export function changesTabHasContent(x: { layers: number; settled: number; runs: number; stuck: number; feedback?: number }): boolean {
  return x.layers > 0 || x.settled > 0 || x.runs > 0 || x.stuck > 0 || (x.feedback ?? 0) > 0
}
