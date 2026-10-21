
export type PlanTabIn = {
  /** Is a real note open now (false on virtual pages). */
  hasNote: boolean
  /** Is a harness running at this moment (`loading === 'note-harness' || harness?.running`). */
  running: boolean
  /** How many round cards this run has (`agentRounds.length`). */
  rounds: number
  /** How many beats this note's skeleton has (`beats.length`). */
  beats: number
}

export type PlanTabOut = {
  /** Can **at least one** of the four body blocks draw this time. false => `RightPane` shows `emptyHint`. */
  has: boolean
  /** What the tab badge shows. **0 means no badge** (that line in `App.tsx` turns 0 into `undefined`). */
  badge: number
}

/** The sentence said when the "Plan" cell is empty.
 *
 * **The same sentence pattern** as the "Memory" cell's fallback ("After you open a note, here..."),
 * because when users switch tabs left and right on a virtual page they should see one kind of explanation, not two tones. */
export const PLAN_EMPTY_HINT = 'Open a note to see its done criteria, outline, writing skeleton and every round here.'

export function planTabContent(x: PlanTabIn): PlanTabOut {
  // The condition of the execution-record block, copied verbatim from that line in `App.tsx`.
  const activity = x.hasNote || x.running
  // Done criteria / outline / skeleton all need `current`; the outline block draws a line `<h2>Outline</h2>`
  // even when the body is empty, so "a note is open" by itself is enough for this cell to have something.
  const has = x.hasNote || activity
  // The badge follows **the blocks that can really draw this time**: when the execution record cannot draw, the previous note's leftover
  // `rounds` count for nothing; the skeleton's beats still only count when a note is open (that is how the original line was written).
  const badge = (activity ? x.rounds : 0) || (x.hasNote ? x.beats : 0)
  return { has, badge }
}
