
import { Annotation } from '@codemirror/state'
import type { ViewUpdate } from '@codemirror/view'

/** This transaction is "React's content synced in"; value = the body that was synced. */
export const syncedFromApp = Annotation.define<string>()

/** This update is exactly the copy we just synced, unchanged character for character -- so do not echo it back to React. */
export function isAppEcho(update: ViewUpdate, text: string): boolean {
  return update.transactions.some((t) => t.annotation(syncedFromApp) === text)
}
