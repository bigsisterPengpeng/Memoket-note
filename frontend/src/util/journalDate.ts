/** Whether this note is **a day in the journal**, and if so which day.
 *
 * Used to hang a "today's screen activity" block on the journal note's ribbon
 * (`docs/daily-journey-plan.md` §8.4: each side can find the other, but **machine-written content
 * is not stuffed into the user's note body**).
 *
 * The check follows the chain built by backend `store.journal_node`:
 * `Journal / 2026 / month 09 / 09-14 Sun`. **Recognized by title, not by id** -- that tree is
 * looked up by title in the first place (the `journal_node` comment: without an attribute system, use the plainest way);
 * if the user renames "Journal", a new tree starts and this block stops recognizing the old one, consistent on both sides.
 *
 * The year must be read from **that level of the tree**, not filled in from today's year: when opening last year's journal entry,
 * screen activity would query a day that does not exist, and the page would say "no record for this day" --
 * worse than showing nothing (it looks like a fact).
 */
export type JournalRow = { note_id: string; parent_note_id: string; title: string }

const DAY = /^(\d{2})-(\d{2})(\s|$)/
const MONTH = /^(\d{2})\s*\u6708$/
const YEAR = /^(\d{4})$/
/** The journal root is created with the UI language's name; existing libraries have the Chinese one. */
const JOURNAL_ROOT_TITLES = new Set(['Journal', '\u65e5\u8bb0'])

export function journalDateOf(rows: JournalRow[], noteId: string): string | null {
  const by = new Map(rows.map((r) => [r.note_id, r]))
  const day = by.get(noteId)
  const d = day && DAY.exec(day.title)
  if (!day || !d) return null
  const month = by.get(day.parent_note_id)
  const m = month && MONTH.exec(month.title.trim())
  if (!month || !m) return null
  const year = by.get(month.parent_note_id)
  const y = year && YEAR.exec(year.title.trim())
  if (!year || !y) return null
  // The top level must really be called "Journal" -- otherwise any subtree shaped like `2026 / month 09 / 09-14`
  // would be taken as a journal (users may well number other things this way)
  if (!JOURNAL_ROOT_TITLES.has(by.get(year.parent_note_id)?.title ?? '')) return null
  // If the month level and the day level do not match (moved by hand), do not recognize it: better to show nothing
  // than to show a wrong day
  if (m[1] !== d[1]) return null
  return `${y[1]}-${d[1]}-${d[2]}`
}
