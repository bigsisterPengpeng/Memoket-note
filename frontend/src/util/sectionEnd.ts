/** Where the section titled title ends in the body: before the next heading of no deeper level, or the end of the note if none.
 *  Same rule as backend editor/outline.section_end -- the landing point of targeted continue is computed by the frontend from its own body,
 *  and the backend's pos is only a fallback when the heading cannot be found here. */
export function sectionEnd(content: string, title: string): number | null {
  const marks: { level: number; title: string; start: number }[] = []
  let inFence = false
  let offset = 0
  // A # inside a fenced code block is not a heading -- scan line by line
  for (const line of content.split('\n')) {
    if (/^\s*(`{3,}|~{3,})/.test(line)) inFence = !inFence
    else if (!inFence) {
      const h = /^(#{1,6})\s+(\S.*?)\s*$/.exec(line)
      if (h) marks.push({ level: h[1].length, title: h[2].trim(), start: offset })
    }
    offset += line.length + 1
  }
  const want = title.trim()
  for (let i = 0; i < marks.length; i++) {
    if (marks[i].title !== want) continue
    for (let j = i + 1; j < marks.length; j++) if (marks[j].level <= marks[i].level) return marks[j].start
    return content.length
  }
  return null
}
