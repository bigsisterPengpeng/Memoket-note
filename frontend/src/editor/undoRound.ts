
import { diffParts, toHunks, type DiffPart } from './roundDiff'
import { t } from '../i18n'

export type UndoRoundResult = {
  text: string
  /** How many changes were reverted */
  undone: number
  /** How many changes this round had in total */
  total: number
  /** The ones that could not be reverted: which change, and why */
  conflicts: string[]
}

const CTX = [24, 12, 6, 0]

/** Position of the unique hit; -1 = none, -2 = more than one */
function findUnique(hay: string, needle: string): number {
  const at = hay.indexOf(needle)
  if (at < 0) return -1
  return hay.indexOf(needle, at + 1) >= 0 ? -2 : at
}

const snippet = (s: string) => { const t = s.replace(/\s+/g, ' ').trim(); return t.length > 24 ? t.slice(0, 24) + '…' : t }


export const conflictLead = (s: string, k: number) => { const lead = snippet(s); return lead ? t('“{text}”', { text: lead }) : t('Change {k} (only blank lines, nothing to quote)', { k }) }

/** How alike two passages are: Dice coefficient of character 2-grams (0-1). Used to pair "edited paragraphs". */
export function similarity(a: string, b: string): number {
  if (a === b) return 1
  if (a.length < 2 || b.length < 2) return 0
  const grams = (s: string) => { const m = new Map<string, number>(); for (let i = 0; i + 1 < s.length; i++) { const g = s.slice(i, i + 2); m.set(g, (m.get(g) ?? 0) + 1) } return m }
  const ga = grams(a); const gb = grams(b)
  let hit = 0
  for (const [g, n] of ga) hit += Math.min(n, gb.get(g) ?? 0)
  return (2 * hit) / (a.length - 1 + b.length - 1)
}

/** Two passages must be at least this alike to pair; below that, treat it as one deleted and another newly written */
const PAIR_MIN = 0.4


export function paragraphDiff(a: string, b: string): DiffPart[] {
  const split = (s: string) => s.split(/(\n{2,})/).filter((t) => t.length > 0)
  const ta = split(a); const tb = split(b)
  // LCS on paragraph tokens
  const n = ta.length; const m = tb.length
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = ta[i] === tb[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
  const out: DiffPart[] = []
  const push = (type: DiffPart['type'], text: string) => {
    if (!text) return
    const last = out[out.length - 1]
    if (last && last.type === type) last.text += text
    else out.push({ type, text })
  }
  const flush = (dels: string[], inss: string[]) => {
    // Pair edited paragraphs by similarity (keeping order); compare paired ones by character, the rest are whole-paragraph deletes / inserts
    let j = 0
    for (const d of dels) {
      let best = -1; let bestSim = PAIR_MIN
      for (let k = j; k < inss.length; k++) { const s = similarity(d, inss[k]); if (s > bestSim) { best = k; bestSim = s } }
      if (best < 0) { push('del', d); continue }
      for (let k = j; k < best; k++) push('ins', inss[k])
      for (const p of diffParts(d, inss[best])) push(p.type, p.text)
      j = best + 1
    }
    for (let k = j; k < inss.length; k++) push('ins', inss[k])
  }
  let i = 0; let j = 0
  let dels: string[] = []; let inss: string[] = []
  while (i < n || j < m) {
    if (i < n && j < m && ta[i] === tb[j]) {
      flush(dels, inss); dels = []; inss = []
      push('keep', ta[i]); i++; j++
    } else if (j < m && (i >= n || dp[i][j + 1] >= dp[i + 1][j])) {
      inss.push(tb[j]); j++
    } else {
      dels.push(ta[i]); i++
    }
  }
  flush(dels, inss)
  return out
}

/**
 * Position in a -> position in b (by the parts of `paragraphDiff(a, b)` / `diffParts(a, b)`). Landing on a passage deleted in b sticks to its left (collapses).
 * `bias`: 'start' is the start of a span -- resting exactly on an insertion point counts as after the insertion (text a later round inserted before it is not part of it);
 * 'end' is the end of a span -- resting on an insertion point counts as before the insertion (text a later round appended after it is not part of it either).
 */
export function mapPos(parts: DiffPart[], pos: number, bias: 'start' | 'end'): number {
  let a = 0
  let b = 0
  for (const p of parts) {
    const n = p.text.length
    if (p.type === 'keep') {
      if (pos < a + n || (bias === 'end' && pos === a + n)) return b + (pos - a)
      a += n; b += n
    } else if (p.type === 'del') {
      if (pos < a + n) return b
      a += n
    } else {
      b += n
    }
  }
  return b
}

/**
 * @param before  the body before round N
 * @param after   the body after round N (= before round N+1)
 * @param current the current body
 * @param later   snapshots of every round after round N, in chronological order (after round N+1, ..., the wrap-up); without them, locate by text only
 */
export function undoRound(before: string, after: string, current: string, later: string[] = []): UndoRoundResult {
  const hunks = toHunks(diffParts(before, after))
  // The diff chain of the later rounds: each link is the parts of (previous version -> this version)
  const chain: DiffPart[][] = []
  let prev = after
  for (const snap of later) {
    chain.push(paragraphDiff(prev, snap))
    prev = snap
  }
  const latest = prev
  let text = current
  let undone = 0
  const conflicts: string[] = []
  // From back to front: an earlier change's context is not polluted by the original text just swapped back
  for (let k = hunks.length - 1; k >= 0; k--) {
    const h = hunks[k]
    const ins0 = after.slice(h.from, h.to)
    // Map this change of round N along the later rounds to its position in the final version
    let from = h.from
    let to = h.to
    for (const parts of chain) {
      from = mapPos(parts, from, 'start')
      to = Math.max(from, mapPos(parts, to, 'end'))
    }
    const ins = latest.slice(from, to)
    if (ins0 && !ins && h.del) {
      conflicts.push(conflictLead(ins0, k + 1) + t(' was deleted entirely by a later round; unclear whether the original should come back'))
      continue
    }
    let why = ''
    let done = false
    for (const n of CTX) {
      const pre = latest.slice(Math.max(0, from - n), from)
      const post = latest.slice(to, to + n)
      const needle = pre + ins + post
      if (!needle) { why = t('original position not found (surrounding text changed)'); break }
      const at = findUnique(text, needle)
      if (at === -2) { why = ins ? t('appears more than once in the current text; unclear which to revert') : t('original position is ambiguous; unclear where to restore'); break }
      if (at < 0) { why = ins ? t('not found in the current text (edited since)') : t('original position not found (context changed)'); continue }
      text = text.slice(0, at + pre.length) + h.del + text.slice(at + pre.length + ins.length)
      done = true
      break
    }
    if (done) undone++
    else conflicts.push(t('{lead} {why}', { lead: conflictLead(ins0 || h.del, k + 1), why }))
  }
  return { text, undone, total: hunks.length, conflicts: conflicts.reverse() }
}
