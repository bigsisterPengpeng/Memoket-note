
export type Snippet = { before: string; hit: string; after: string }


export function matchSnippet(content: string, query: string, span = 28, before = span): Snippet | null {
  const q = query.trim()
  if (!q) return null

  const text = content.replace(/^\s*(#{1,6}|[-*>]|\d+\.)\s+/gm, '').replace(/\s+/g, ' ')
  const i = text.toLowerCase().indexOf(q.toLowerCase())
  if (i < 0) return null
  const start = Math.max(0, i - before)
  const end = Math.min(text.length, i + q.length + span)
  return {
    before: (start > 0 ? '…' : '') + text.slice(start, i),
    hit: text.slice(i, i + q.length),
    after: text.slice(i + q.length, end) + (end < text.length ? '…' : ''),
  }
}
