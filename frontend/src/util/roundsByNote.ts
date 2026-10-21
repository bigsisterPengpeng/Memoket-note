
import type { AgentRound } from '../components/AgentActivity'

/** What is returned when this note has not run a single round.
 *
 *  **A module-level constant, not a fresh `[]` each time**: it is passed straight as the prop of `<AgentActivity rounds={…}>`,
 *  and a new reference each time would make "this note did not change" look like a change on the React side.
 *  **Never `push` into it** -- all writes go through {@link writeRoundsIn}, which only builds new arrays. */
export const NO_ROUNDS: AgentRound[] = []

/** note id -> that note's round cards. **The key is the note id, not the title, not an index.** */
export type RoundsByNote = Record<string, AgentRound[]>


export function roundsFor(m: RoundsByNote, noteId: string | null | undefined): AgentRound[] {
  if (!noteId) return NO_ROUNDS
  return m[noteId] ?? NO_ROUNDS
}

/** Write onto **a given note's** round cards. `noteId` is required -- "write onto the current note" was exactly the hole.
 *
 *  If `fn` returns its input unchanged => the whole table is returned unchanged, no new object:
 *  `setState` receiving the same reference does not re-render for nothing. */
export function writeRoundsIn(
  m: RoundsByNote, noteId: string, fn: (rs: AgentRound[]) => AgentRound[],
): RoundsByNote {
  const prev = m[noteId] ?? NO_ROUNDS
  const next = fn(prev)
  if (next === prev) return m
  return { ...m, [noteId]: next }
}
