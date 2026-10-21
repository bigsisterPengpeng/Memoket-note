
import type { AgentRound, RestoredMark } from '../components/AgentActivity'
import { t } from '../i18n'

/** One round as returned by backend `GET /api/notes/<id>/rounds` (`schemas.RestoredRound`). */
export type RestoredRoundRow = {
  round: number
  scores: Record<string, number>
  status: string
  weakest: string
  contentLen: number
  toolCalls: number
  repeatCalls: number
  revisionsProposed: number
  revisionsDropped: number
  depthDropped: number
  factsNew: number
  factsTotal: number
  citeLocated: number
  citeMarked: number
  citeMatched: number
  firedChecks: string
  at: string
}

/** The whole response (`schemas.NoteRoundsOut`). */
export type NoteRoundsPayload = {
  runId: string
  at: string
  status: string
  stopped: string
  rounds: RestoredRoundRow[]
  reason: string
  runsTotal: number
  roundsTotal: number
  missing: string[]
}

/** When the latest run ended in an abnormal interruption, an actionable sentence for the right pane.
 *
 * `status=continue` only means the last scoring did not reach the bar; it cannot explain why it stopped; the real
 * reason is read only from `stopped`. The ten normal stops are already explained in the live RUN_FINISHED; this only covers
 * the abnormal exits that never receive RUN_FINISHED. */
export function restoredStopStatus(p: NoteRoundsPayload | null | undefined): string {
  if (!p || !['ok', 'run_without_rounds'].includes(p.reason)) return ''
  if (p.stopped === 'client_disconnected') {
    return t('The last Smart Continue stopped because the editor disconnected; the text was saved at that point. Common causes: pressing Stop, closing the page or a network interruption.')
  }
  if (p.stopped === 'interrupted') {
    return t('The last Smart Continue was interrupted by the runtime; the text was saved at that point. You can continue from here.')
  }
  if (p.stopped === 'error') {
    return t('The last Smart Continue stopped on a runtime error; the text was saved at that point. Review the last round and retry.')
  }
  return ''
}

/** The three `cite_*` columns: **`-1` is "this round never reached that step"**, `0` is "computed, not a single citable sentence".
 *
 *  In `AgentActivity` that cell's condition is `r.citeLocated !== undefined`
 *  (the comment says outright "`0` is a tier to show; a truthiness check would hide it"),
 *  so `-1` must turn back into `undefined`, **not into 0** -- two different things must not become the same number. */
export const citeOrUndefined = (n: number): number | undefined => (n < 0 ? undefined : n)

/** The numbers the library **does** have, laid out in one line. Empty ones are not written (`0 times` and "not recorded" are two different things on this line). */
export function restoredFactsLine(r: RestoredRoundRow): string {
  const bits: string[] = []
  bits.push(t('{n} chars at the end of this round', { n: r.contentLen }))
  if (r.toolCalls > 0) bits.push(t('agent searched {n} times', { n: r.toolCalls }) + (r.repeatCalls > 0 ? t(' ({n} of them repeated)', { n: r.repeatCalls }) : ''))
  if (r.revisionsProposed > 0) bits.push(t('{n} revisions proposed', { n: r.revisionsProposed }) + (r.revisionsDropped > 0 ? t(', {n} dropped', { n: r.revisionsDropped }) : ''))
  if (r.depthDropped > 0) bits.push(t('{n} searches dropped by the depth gate', { n: r.depthDropped }))
  if (r.factsTotal > 0) bits.push(t('{n} materials', { n: r.factsTotal }) + (r.factsNew > 0 ? t(' ({n} new this round)', { n: r.factsNew }) : ''))
  return bits.join(' · ')
}

/** The `fired_checks` column (a JSON array string). **Treat as empty if it cannot be parsed**, without throwing:
 *  this column is for analysis, and one bad row should not stop the whole stack of cards from being read back. */
export function parseFiredChecks(s: string): string[] {
  if (!s) return []
  try {
    const v = JSON.parse(s)
    return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : []
  } catch { return [] }
}

/** The "read back" mark of this round (its shape is defined only in `AgentActivity.RestoredMark`). */
export function restoredMark(p: NoteRoundsPayload, r: RestoredRoundRow): RestoredMark {
  return {
    at: p.at || r.at,
    missing: p.missing ?? [],
    facts: restoredFactsLine(r),
    firedChecks: parseFiredChecks(r.firedChecks),
  }
}

/** Response -> a stack of **skeleton cards**. `reason !== 'ok'` / no rounds at all => empty array. */
export function restoredRounds(p: NoteRoundsPayload | null | undefined): AgentRound[] {
  if (!p || p.reason !== 'ok' || !p.rounds?.length) return []
  return p.rounds.map((r) => ({
    round: r.round,
    cleanupOnly: false,
    // **Not filled**: the library stores `revisions_proposed` / `revisions_dropped`,
    // while the card's "N revisions" is `revisions_applied` (given by onRoundStart).
    // Subtracting the first two to make up the latter would be **fabricated** -- the two numbers' real names are shown in the `facts` line.
    revisions: 0,
    toolCalls: [],            // the library has not a character of per-call arguments / results
    toolTruncated: false,
    // The levels are real, **the verdicts are not in the library** => empty string. In `AgentActivity` the
    // "weakest is 'X': verdict" block's condition is `r.scores[r.weakest]?.note`; empty string => not rendered.
    scores: Object.fromEntries(Object.entries(r.scores ?? {}).map(([k, lv]) => [k, { level: lv, note: '' }])),
    status: r.status,
    weakest: r.weakest || null,
    policyReasons: [],
    policy: null,
    errors: [],
    dropped: [],
    citeLocated: citeOrUndefined(r.citeLocated),
    citeMarked: citeOrUndefined(r.citeMarked),
    citeMatched: citeOrUndefined(r.citeMatched),
    restored: restoredMark(p, r),
  }))
}

/** Whether the rebuilt stack should be put on this note.
 *
 *  **Not a single live card may be covered**: the copy from this trip (or switched away and back while running) carries the details,
 *  the read-back one is only a skeleton. `cur.length > 0` => return `cur` unchanged (not even a new reference,
 *  so React does not re-render for nothing). */
export function mergeRestored(cur: AgentRound[], restored: AgentRound[]): AgentRound[] {
  if (cur.length) return cur
  if (!restored.length) return cur
  return restored
}
