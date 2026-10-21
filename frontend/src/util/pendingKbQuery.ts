/**
 * The word carried over by "Search the knowledge base for this".
 *
 * When the sidebar note search finds nothing it offers a destination; clicking it must first open the knowledge-base page and then fill the word into its
 * search box. Delivering the word with `setTimeout` + an event **bets that the panel is already mounted**: a bit slow and it
 * is lost, with no hint at all. Now it waits here instead -- the panel takes it when it mounts (taking it
 * clears it; it is returned only once), and the already-mounted case still receives the event.
 */
let pending = ''

export function setPendingKbQuery(q: string): void { pending = q }

export function takePendingKbQuery(): string {
  const q = pending
  pending = ''
  return q
}
