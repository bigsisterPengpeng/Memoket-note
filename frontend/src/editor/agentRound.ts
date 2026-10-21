/** The things that "accumulate" on a round card.
 *
 * **Why a separate pure function rather than one line in App.tsx** (batch 24 / plan 12.1):
 * that line used to be `{ ...last, checkHit: d }` -- **the later one overwrote the earlier one**.
 * Several `check_hit`s can arrive in one round: the ones released after being stuck for consecutive rounds (the backend still sends them,
 * see `middleware/checks.STUCK_ROUNDS`) + the last one that really short-circuited. So
 * "the criterion hit, but it is invisible in the UI" -- the same shape as "having a criterion is not the same as using it".
 *
 * A setState callback written in App.tsx is **reachable by no test**: changed back to overwriting,
 * every frontend gate stayed green (measured). Only a pure function can be pinned.
 */

/** One code-criterion hit. `check` is **the criterion's own name** -- `dimension` cannot answer
 * "which criterion hit", because five criteria all land on `factual_grounding`. */
export type CheckHit = {
  round?: number
  check?: string
  /** Which check this round reached (the denominator `checksTotal` is in round_summary) */
  ran?: number
  dimension: string
  note: string
  stuck_rounds?: number

  stopped?: boolean

  advisory?: boolean
  /** Several rounds in a row without a single real scoring, so this round is **released** (reported but not short-circuited).
   * Backend `middleware/checks.JUDGE_FLOOR`; carries that consecutive round count. */
  judge_floor?: number
}


export type CheckHitKind = 'stopped' | 'stuck' | 'released' | 'shortCircuit'

export function checkHitKind(h: CheckHit): CheckHitKind {
  if (h.stopped) return 'stopped'                       // stop notice, the whole run stopped
  if (h.stuck_rounds) return 'stuck'                    // stuck for consecutive rounds -> released
  if (h.advisory || h.judge_floor) return 'released'    // reminder / starvation release -> released
  return 'shortCircuit'                                 // real short circuit: this round was not scored
}

/** Record a hit on this round, **without dropping the earlier ones**. */
export function withCheckHit<T extends { checkHits?: CheckHit[] }>(
  round: T, hit: CheckHit,
): T {
  return { ...round, checkHits: [...(round.checkHits ?? []), hit] }
}
