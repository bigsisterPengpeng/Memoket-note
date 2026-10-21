/** How "open some day's screen activity" works.
 *
 * Both paths are used together, because **that page may not be mounted yet, or may already be open**:
 *   · not open yet: `open-virtual` opens it, and `JourneyPage` **takes** this date when mounting
 *   · already open: `openVirtual` returns early (the same virtual id is not reopened), the page is not remounted,
 *     so there must also be an event to make it flip over on the spot
 *
 * Missing either one, the second click from the journal ribbon does nothing -- this kind of "the second click does nothing" bug
 * is the hardest to notice, because the first time always works.
 */
export const JOURNEY_DAY_EVENT = 'journey-day'

let pending = ''

/** Today is the empty string: the page's "today" and "some day" are two states (the header's "recording"
 *  is said only for today); passing a date equal to today would downgrade it to "flipped to some past day". */
export function openJourneyDay(date: string, today = new Date()): void {
  const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  pending = date === iso ? '' : date
  window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'app:journey' }))
  window.dispatchEvent(new CustomEvent(JOURNEY_DAY_EVENT, { detail: pending }))
}

/** Take the day pending to open (**take** = takes effect once: afterwards the user flips days themselves,
 *  and a refresh should not drag them back). */
export function takePendingJourneyDay(): string {
  const d = pending
  pending = ''
  return d
}

// ---------------------------------------------------------------- ⌘K's "this week's screen activity"


export const JOURNEY_SPAN_EVENT = 'journey-span'
/** How many days the ⌘K item means. Changing this number means changing the name of that command in `CommandPalette` too. */
export const JOURNEY_SPAN_DAYS = 7

let pendingSpan = 0

export function openJourneySpan(days = JOURNEY_SPAN_DAYS): void {
  pendingSpan = days
  window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'app:journey' }))
  window.dispatchEvent(new CustomEvent(JOURNEY_SPAN_EVENT, { detail: days }))
}

/** Take the pending range (the same rule as `takePendingJourneyDay`: takes effect once). */
export function takePendingJourneySpan(): number {
  const d = pendingSpan
  pendingSpan = 0
  return d
}
