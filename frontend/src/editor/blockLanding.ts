

/** The version "Revert all" returns to: replace blocks put the cleared selection back at `at`; insert blocks use the current body. */
export function diffBaseForBlock(doc: string, at: number, key: string, selection: string): string {
  if (key !== 'custom' || !selection) return doc
  const i = Math.max(0, Math.min(at, doc.length))
  return doc.slice(0, i) + selection + doc.slice(i)
}

/** The text actually written into the body: insert blocks add a blank line to separate what follows; replace blocks land back in the sentence as-is. */
export function textToLand(key: string, text: string): string {
  return key === 'custom' ? text : text + '\n\n'
}
