

/** The single source of the citation id regex (with a capture group). Synced with backend store._CITE / checks/citations / prompts/fragments;
 *  the frontend factCite.ts highlights and App's "which facts are cited" all take it from here instead of each copying one. */
export const CITE_RE_SOURCE = String.raw`\[((?:[A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9_-]*-manualF[1-9]\d*))\]`
export const CITATION_RE = new RegExp(CITE_RE_SOURCE, 'g')
/** Which fact ids the body cites (deduplicated, in order of first appearance). The same regex as backend `store.cited_fact_ids` --
 *  if the two recognized different sets, the ribbon badge and the ◆ in the tree would disagree. */
export const citedFactIds = (s: string): string[] => Array.from(new Set(Array.from(s.matchAll(CITATION_RE), (m) => m[1])))
export const stripCitations = (s: string) => s.replace(CITATION_RE, '').replace(/[ \t]{2,}/g, ' ')


export const stripForRecall = (s: string) => stripCitations(
  s.replace(/!\[[^\]]*\]\([^)]*\)/g, '').replace(/\[([^\]]*)\]\([^)]*\)/g, '$1'))

export function wordCount(content: string): number {
  return content

    // links count only their display text, not the address
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(CITATION_RE, '')
    // Table separator rows |---|:--:| are all markers (after formatting aligned and widened them the count once jumped from 7760 to 8241)
    .replace(/^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/gm, '')
    .replace(/^\s*(#{1,6}|[-*>+]|\d+\.)\s+/gm, '')
    .replace(/[*_`|~]/g, '')
    .replace(/\s+/g, '').length
}

export function readingMinutes(words: number): number {
  return Math.max(1, Math.round(words / 400))
}

/** Position ranges of certain citations in the body (`[id]` together with the space before it), for the editor to delete in one go --
 *  only the id in brackets is removed, the sentence stays (the sentence is not wrong, its grounding is gone). Ranges are in ascending position order and do not overlap. */
export function citationRanges(text: string, ids: string[]): { from: number; to: number }[] {
  const want = new Set(ids)
  const out: { from: number; to: number }[] = []
  for (const m of text.matchAll(CITATION_RE)) {
    if (!want.has(m[0].slice(1, -1))) continue
    let from = m.index
    if (from > 0 && text[from - 1] === ' ') from -= 1
    out.push({ from, to: m.index + m[0].length })
  }
  return out
}

/** The single source of the `[title](note://id)` note link (m[1] title, m[2] id). Synced with backend store._NOTE_LINK. */
export const NOTE_LINK_RE = /\[([^\]\n]*)\]\(note:\/\/([0-9a-f]{12})\)/g
/** Only looks at the `](note://id)` tail -- the same rule as backend store._NOTE_LINK (the backend also counts links whose title contains a newline;
 *  computing by the titled regex above, the frontend would miss them; scripts/check-regex-parity watches it with samples). */
export const NOTE_LINK_TAIL_RE = /\]\(note:\/\/([0-9a-f]{12})\)/g
/** Which note ids the body links to (deduplicated, in order of first appearance). The links panel's "outgoing" and "linked notes gone", and the ribbon badge, are all computed from this. */
export const linkedNoteIds = (s: string): string[] => Array.from(new Set(Array.from(s.matchAll(NOTE_LINK_TAIL_RE), (m) => m[1])))

/** `[title](note://id)` links to certain notes in the body: ranges + the plain text (title) they are replaced with. When the linked note is gone,
 *  the link becomes plain text and the words stay. */
export function noteLinkRanges(text: string, ids: string[]): { from: number; to: number; insert: string }[] {
  const want = new Set(ids)
  const out: { from: number; to: number; insert: string }[] = []
  for (const m of text.matchAll(NOTE_LINK_RE)) {
    if (!want.has(m[2])) continue
    out.push({ from: m.index, to: m.index + m[0].length, insert: m[1] })
  }
  return out
}
