

/** The body **last delivered to this note** by the server / stream, and how many changes the editor reported since. */
export interface Served {
  /** Which note this body belongs to. Written by `open()`; empty string = no anchor yet. */
  id: string
  /** That body itself. */
  text: string
  /** Number of changes the editor reported since that copy was delivered (**echoes do not count**). */
  edits: number
}

/** Whether the copy to save is "the user did nothing, and it got shorter". true = do not write it, write `served.text`. */
export function isStaleShrink(served: Served, noteId: string, content: string): boolean {
  if (!served.id || served.id !== noteId) return false     // (1) the anchor must be this note's
  if (served.edits !== 0) return false                     // (2) once the user touched anything, do not block
  return content.length < served.text.length               // (3) shorter than the copy just delivered
}
