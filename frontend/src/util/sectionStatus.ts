
import { citedFactIds, linkedNoteIds, wordCount } from './wordCount'
import { t } from '../i18n'

export type SectionState = 'empty' | 'draft' | 'sourced'
export type SectionStatus = {
  pos: number
  state: SectionState
  words: number
  cites: number
  links: number
}
export const SECTION_LABEL: Record<SectionState, string> = { empty: 'Empty', draft: 'Draft', sourced: 'Sourced' }

type Heading = { level: number; text: string; pos: number }

/** Each heading -> the body between it and the next heading of the same or higher level (subsections count toward the parent: a parent with no text of its own but subsections with text is not empty). */
export function sectionStatuses(content: string, headings: Heading[]): SectionStatus[] {
  const out: SectionStatus[] = []
  for (let i = 0; i < headings.length; i++) {
    const h = headings[i]
    let end = content.length
    for (let j = i + 1; j < headings.length; j++) if (headings[j].level <= h.level) { end = headings[j].pos; break }
    // Drop the heading line itself
    const nl = content.indexOf('\n', h.pos)
    const bodyStart = nl === -1 ? content.length : nl + 1
    const body = bodyStart < end ? content.slice(bodyStart, end)
      // Drop subsection heading lines too (count body characters only)
      .replace(/^#{1,6}\s.*$/gm, '') : ''
    const words = wordCount(body)
    const cites = citedFactIds(body).length
    const links = linkedNoteIds(body).length
    const state: SectionState = words === 0 ? 'empty' : cites + links > 0 ? 'sourced' : 'draft'
    out.push({ pos: h.pos, state, words, cites, links })
  }
  return out
}

export function sectionSummary(s: SectionStatus[]): { empty: number; draft: number; sourced: number } {
  return {
    empty: s.filter((x) => x.state === 'empty').length,
    draft: s.filter((x) => x.state === 'draft').length,
    sourced: s.filter((x) => x.state === 'sourced').length,
  }
}

/** A section's "what materials it used" sentence: "3 sources · 1 linked note". */
export function materialsText(s: SectionStatus): string {
  const parts: string[] = []
  if (s.cites) parts.push(t('{n} sources', { n: s.cites }))
  if (s.links) parts.push(t('links {n} notes', { n: s.links }))
  return parts.join(' · ')
}

// The various spellings of status labels (consistent with backend skeleton.py::_STATUS: "written:", bracketed "written", "written, needs tightening", "to fill", "missing"...).
// One step stricter than the backend: the label must be followed by punctuation / a bracket / "(body line" / end of line -- a sentence starting with the word "written" (real library 574f item 2) is the start of a sentence, not a label;

const BEAT_STATUS = /^\s*[\u3010[\uff08(]?\s*(?:(?<w>written|completed|\u5df2\u5199(?:\u5e76\u9700\u7ee7\u7eed\u6536\u7d27|\u5e76\u9700\u6536\u7d27|\u4f46\u9700\u6536\u7d27)?|\u5df2\u6709|\u5df2\u5b8c\u6210)|(?<m>missing|to fill|\u5f85\u8865\u5145|\u5f85\u8865|\u5c1a\u7f3a|\u7f3a\u5931|\u672a\u5199|\u5f85\u5199|\u5c1a\u672a\u5199|\u5f85\u5199\u5165))(?=\s*(?:[\u3011\]\uff09):\uff1a,\uff0c\u3001—-]|\(from body line|\uff08\u6b63\u6587\u7b2c|$))/i
const BEAT_TAIL = /^\s*[\u3011\]\uff09)]?\s*(?:(?:\(from body line\s*(\d+)\s*\)|\uff08\u6b63\u6587\u7b2c\s*(\d+)\s*\u884c\u8d77\uff09))?\s*[:\uff1a,\uff0c\u3001—-]*\s*/i

export type BeatLabel = { status: 'written' | 'missing' | null; text: string; line: number | null }

/** "written (from body line 12): xxx" -> { written, 'xxx', 12 }; unlabeled -> { null, original, null }. */
export function splitBeatLabel(beat: string): BeatLabel {
  const m = BEAT_STATUS.exec(beat || '')
  if (!m) return { status: null, text: (beat || '').trim(), line: null }
  const rest = (beat || '').slice(m[0].length)
  const t = BEAT_TAIL.exec(rest)
  const lineNumber = t?.[1] ?? t?.[2]
  const line = lineNumber ? Number(lineNumber) : null
  return { status: m.groups?.w ? 'written' : 'missing', text: rest.slice(t?.[0].length ?? 0).trim(), line }
}
