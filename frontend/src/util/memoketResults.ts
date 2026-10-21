export type RecordingMatch = { id: string; title: string }

/** Only use explicit conversation IDs; other hit IDs can identify transcript lines or summaries. */
export function memoketMatches(result: unknown): RecordingMatch[] {
  const matches = new Map<string, RecordingMatch>()
  function add(id: unknown, title = '') {
    if (typeof id !== 'string' || !id.trim()) return
    const previous = matches.get(id)
    matches.set(id, { id, title: title || previous?.title || '' })
  }
  function visit(value: unknown, depth: number) {
    if (depth > 12) return
    if (typeof value === 'string' && /^[\s]*[\[{]/.test(value)) {
      try { visit(JSON.parse(value), depth + 1) } catch { /* Plain source text. */ }
    } else if (Array.isArray(value)) {
      value.forEach((item) => visit(item, depth + 1))
    } else if (value && typeof value === 'object') {
      const obj = value as Record<string, unknown>
      add(obj.conversation_id, typeof obj.title === 'string' ? obj.title : '')
      if (Array.isArray(obj.conversation_ids)) obj.conversation_ids.forEach((id) => add(id))
      Object.values(obj).forEach((item) => visit(item, depth + 1))
    }
  }
  visit(result, 0)
  return Array.from(matches.values())
}
