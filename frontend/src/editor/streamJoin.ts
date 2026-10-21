
export function insertStreamed(content: string, cursor: number | null, text: string): { next: string; cursor: number } {
  const cur = cursor != null && cursor <= content.length ? cursor : content.length
  const joined = content.slice(0, cur) + text + content.slice(cur)
  const from = Math.max(0, cur - 2)
  const to = cur + text.length
  const window = joined.slice(from, to).replace(/\n{3,}/g, '\n\n')
  return { next: joined.slice(0, from) + window + joined.slice(to), cursor: from + window.length }
}

/** Squeeze consecutive blank lines back into one (copied from backend `revision.tidy_blank_lines`): the server runs it after applying each revision,
 *  and a delete leaves "before\n\n" + "\n\nafter" merged into three blank lines; the client must run it too after replaying revisions locally,
 *  or the two sides differ by a few newlines at round end. Blank lines inside code blocks (``` fences) are content and skipped; trailing whitespace outside fences is stripped too. */
export function tidyBlankLines(content: string): string {
  const out: string[] = []
  let inFence = false
  let blanks = 0
  for (const line of content.split('\n')) {
    if (line.trimStart().startsWith('```')) inFence = !inFence
    if (!inFence && !line.trim()) {
      blanks += 1
      if (blanks > 1) continue
    } else blanks = 0
    out.push(inFence ? line : line.replace(/\s+$/, ''))
  }
  return out.join('\n')
}


export function applyScrub(content: string, sentence: string): string {
  if (!content || !sentence || !content.includes(sentence)) return content
  const out: string[] = []
  let any = false
  for (const para of content.split(/(\n\s*\n)/)) {
    const t = para.trim()
    if (t.startsWith('|') || t.startsWith('```') || t.startsWith('#') || !para.includes(sentence)) { out.push(para); continue }
    const kept: string[] = []
    let hit = false
    for (const x of para.split(/(?<=[\u3002\uff01\uff1f])/)) {
      if (!x) continue
      if (x.trim() === sentence.trim()) { hit = true; continue }
      kept.push(x.trim() || x)
    }
    // The sentence sent by the server was cut by the same rules and then stripped (a leading citation id counts as part of the sentence); if no whole sentence matches, leave this paragraph alone
    if (hit) any = true
    out.push(hit ? kept.join('') : para)
  }
  if (!any) return content
  return out.join('').replace(/\n{3,}/g, '\n\n').trim()
}

/** The `insert_at` event arrived: make room at local body position pos for this round's continuation (per the server's `outline.insert_into`:
 *  collapse to one blank line before, start with one blank line after, drop stray punctuation right after the insertion point); returns the new body and where later deltas should land.
 *  The blank lines reserved at the end of the note for appending are taken back first. */
export function prepareInsert(content: string, pos: number): { next: string; cursor: number } {
  const base = content.replace(/\n+$/, '\n')
  const at = Math.min(pos, base.length)
  const head = base.slice(0, at).replace(/\n*$/, '\n\n')
  const tail = base.slice(at).replace(/^\n*/, '').replace(/^[\uff0c\u3001\u3002\uff1b\uff1a,;:]+\s*/, '')
  return { next: head + '\n\n' + tail, cursor: head.length }
}
