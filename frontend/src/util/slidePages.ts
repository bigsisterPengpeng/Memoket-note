/** Slides markdown -> pages. **The same rule as backend `checks/slides.split_pages`**;
 *  if the two drift, "the criterion says 24 pages, the preview draws 26".
 *
 *  `---` splits pages, but **`---` inside code blocks does not count** -- rules are common in mermaid / yaml blocks,
 *  and one wrong split scrambles the whole deck (the same trap as `util/sectionEnd`). Front-matter at the start
 *  is not a page. */
export type Page = { title: string; body: string; at: number; cited: boolean }

const CITE = /\[(?:[A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12,64})-[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9_-]*-manualF[1-9]\d*)\]/

export function isSlides(md: string): boolean {
  return /^---\s*\n([\s\S]*?)\n---\s*(\n|$)/.test(md || '') && /\bslides:\s*true\b/.test(md || '')
}

export function slidePages(md: string): Page[] {
  const lines = (md || '').split('\n')
  let start = 0
  if (lines[0]?.trim() === '---') {
    const end = lines.findIndex((l, i) => i > 0 && l.trim() === '---')
    if (end > 0) start = end + 1
  }
  const pages: Page[] = []
  let buf: string[] = []
  let at = lines.slice(0, start).join('\n').length + (start ? 1 : 0)
  let bufAt = at
  let fenced = false
  const flush = () => {
    const raw = buf.join('\n').trim()
    if (raw) {
      const m = /^#{1,6}\s+(.*)$/m.exec(raw)
      pages.push({
        title: (m?.[1] ?? '').trim(),
        body: raw.replace(/^#{1,6}\s+.*$/m, '').trim(),
        at: bufAt,
        cited: CITE.test(raw),
      })
    }
    buf = []
  }
  for (let i = start; i < lines.length; i++) {
    const ln = lines[i]
    if (ln.trim().startsWith('```')) fenced = !fenced
    if (!fenced && ln.trim() === '---') { flush(); at += ln.length + 1; bufAt = at; continue }
    if (!buf.length) bufAt = at
    buf.push(ln)
    at += ln.length + 1
  }
  flush()
  return pages
}
