/** When the whole body is pushed in from outside, compute the smallest single change.
 *
 * It used to be "replace the whole note + move the cursor to the end": every streamed continuation chunk replaced the whole note, and the cursor and viewport
 * were dragged to the end together -- inserting in the middle (continue from the cursor, targeted continue) was unwatchable; round highlights,
 * folding and other position-mapped decorations were all fully recomputed too. Here we take the common prefix / suffix and dispatch only
 * the middle part; CodeMirror maps the selection itself. */
export function minimalChange(oldText: string, newText: string): { from: number; to: number; insert: string } | null {
  if (oldText === newText) return null
  const minLen = Math.min(oldText.length, newText.length)
  let start = 0
  while (start < minLen && oldText.charCodeAt(start) === newText.charCodeAt(start)) start++
  let endOld = oldText.length
  let endNew = newText.length
  while (endOld > start && endNew > start && oldText.charCodeAt(endOld - 1) === newText.charCodeAt(endNew - 1)) { endOld--; endNew-- }
  // Do not cut a surrogate pair in half (emoji and other 4-byte characters)
  if (start > 0 && start < minLen && (oldText.charCodeAt(start - 1) & 0xfc00) === 0xd800) start--
  return { from: start, to: endOld, insert: newText.slice(start, endNew) }
}
