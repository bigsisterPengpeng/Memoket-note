
import { wordCount } from './wordCount'
import { parseHeadings } from '../components/DocumentOutline'
import { t } from '../i18n'

export type DoneStatus = 'pass' | 'fail' | 'manual'
export type DoneItem = {
  text: string
  status: DoneStatus
  /** For code-judged ones: why it passed / failed ("3 of 5 items have no date"); for user-judged ones: empty */
  why: string
  /** Ticked by the user (meaningful only for manual) */
  checked: boolean
}

/** The single source of the rule regexes (`String.raw`, matching backend `checks/done.py::RULES` entry for entry, character for character). */
export const DONE_RULES = {
  max: String.raw`(?:\u2264|<=|\u4e0d\u8d85\u8fc7|\u4e0d\u591a\u4e8e|\u5c11\u4e8e|\u63a7\u5236\u5728|\u6700\u591a|atmost|nomorethan|within|maximum(?:of)?)(\d+)(?:\u5b57|characters?|chars?)`,
  max2: String.raw`(\d+)(?:\u5b57(?:\u4ee5\u5185|\u4ee5\u4e0b|\u4e4b\u5185|\u5185)|(?:characters?|chars?)(?:orless|maximum))`,
  min: String.raw`(?:\u2265|>=|\u81f3\u5c11|\u4e0d\u5c11\u4e8e|\u4e0d\u4f4e\u4e8e|\u6700\u5c11|atleast|minimum(?:of)?)(\d+)(?:\u5b57|characters?|chars?)`,
  min2: String.raw`(\d+)(?:\u5b57(?:\u4ee5\u4e0a|\u8d77)|(?:characters?|chars?)(?:ormore|minimum))`,
  nonempty: String.raw`\u5199\u4e0b\u6765\u5c31\u7b97\u5b8c|\u5199\u4e86\u5c31\u7b97|^(?:non-?empty(?:note|body)|writeanything)$`,
  sections_en: String.raw`^(?:sections:\s*(.+)|(.+?)\s+each\s+(?:have|has)\s+(?:a\s+)?section)$`,
  sections: String.raw`^(.+?)\u5404\u6709\u4e00\u8282`,
  sections2: String.raw`^(.+?)(?:\u5404|\u90fd)?(?:\u5355\u72ec)?(?:\u6709|\u6210)\u4e00\u8282`,
  section_split: String.raw`[\u3001\uff0c,\u548c\u4e0e\u53ca]`,
  section_lead: String.raw`^(?:\u8981|\u9700\u8981|\u5f97)`,
  conclusion: String.raw`\u7ed3\u8bba\u5728\u524d|\u5148\u8bf4\u7ed3\u8bba|\u7ed3\u8bba\u5148\u884c|\u5f00\u5934.*\u7ed3\u8bba|conclusionfirst|startwith(?:the)?conclusion|leadwith(?:the)?conclusion`,
  conclusion_head: String.raw`\u7ed3\u8bba|\u603b\u7ed3|\u6458\u8981|TL;?DR|\u4e00\u53e5\u8bdd|conclusion|summary|recommendation`,
  conclusion_open: String.raw`\u7ed3\u8bba|\u603b\u4e4b|\u4e00\u53e5\u8bdd|\u5224\u65ad\u662f|\u5efa\u8bae|^\s*(?:conclusion|in summary|we recommend|recommendation)\b`,
  date_want: String.raw`\u6709\u65e5\u671f|\u6709\u65f6\u95f4|\u5e26\u65e5\u671f|\u6807\u65e5\u671f|(?:has|have|include|with|show|add|and)(?:a)?dates?|dates?for(?:each|every)|(?:each|every)(?:item|bullet|paragraph)(?:is)?dated`,
  cite_want: String.raw`\u6709\u4f9d\u636e|\u6709\u51fa\u5904|\u6709\u5f15\u7528|\u4e8b\u5b9e\u652f\u6491|\u6709\u6765\u6e90|\u6709\u8bc1\u636e|\u5f15\u7528\u6216\u51fa\u5904|\u6807\u51fa\u5904|\u6ce8\u660e\u51fa\u5904|(?:has|have|include|with|show|add|and)(?:a)?(?:sources?|citations?|references?|evidence)|(?:sources?|citations?)for(?:each|every)|(?:is|are|be)?grounded|supportedbyfacts`,
  numeric_only: String.raw`\u6570\u5b57|\u6570\u636e|numeric(?:al)?(?:claims?|items?)|numbers?|data`,
  date: String.raw`\d{1,2}\s*[\u6708/.-]\s*\d{1,2}|\d{4}\s*[-/\u5e74]\s*\d{1,2}|\d{1,2}\s*\u6708(?:\u5e95|\u521d|\u672b|\u4e2d)?|\u4eca\u5929|\u6628\u5929|\u524d\u5929|\u660e\u5929|\u672c\u5468|\u4e0a\u5468|\u4e0b\u5468|\u5468[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u65e5\u5929]|\u661f\u671f[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u65e5\u5929]|Q[1-4]\b|\d+\s*\u53f7|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?\b|\b(?:today|yesterday|tomorrow|this week|last week|next week|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b`,
  link: String.raw`\[[^\]\n]*\]\([^)\s]+\)|https?://\S+`,
  cite: String.raw`\[((?:[A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9_-]*-manualF[1-9]\d*))\]`,
  note_link: String.raw`\]\(note://([0-9a-f]{12})\)`,
  item: String.raw`^\s*(?:[-*+]|\d+[.)])\s+\S`,
  item_strip: String.raw`^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?`,
  fence: String.raw`^\s*(\x60{3,}|~{3,})`,
  split: String.raw`[\uff1b;\u3002\n]+|\.(?=\s+[A-Z])`,
} as const
/** The wording of "why" -- matching backend `checks/done.py::WHY` word for word (`{x}` are placeholders). */
export const DONE_WHY = {
  max_ok: 'Now {words} chars',
  max_over: 'Now {words} chars, {over} over',
  min_ok: 'Now {words} chars',
  min_short: 'Now {words} chars, {short} short',
  nonempty_ok: '{words} chars written',
  nonempty_no: 'The note is still empty',
  sections_missing: 'Missing headings: {missing}',
  sections_ok: 'All {n} sections present',
  conclusion_ok: 'Opens with the conclusion',
  conclusion_no: 'No conclusion at the start',
  no_units: 'No items in the note yet',
  no_numbers: 'No numbers in the note',
  date_miss: '{miss} of {n} {unit} have no date',
  date_ok: 'All {n} {unit} have a date',
  cite_miss: '{miss} of {n} {unit} have no source',
  cite_ok: 'All {n} {unit} have a source',
} as const
const IGNORE_CASE = new Set(["cite_want", "conclusion", "conclusion_head", "conclusion_open", "date", "date_want", "max", "max2", "min", "min2", "nonempty", "numeric_only", "sections_en"])
const R = Object.fromEntries(Object.entries(DONE_RULES).map(([k, v]) => [k, new RegExp(v, IGNORE_CASE.has(k) ? 'i' : '')])) as Record<keyof typeof DONE_RULES, RegExp>
const HEAD_I = new RegExp(DONE_RULES.conclusion_head, 'i')
const HEADING = /^#{1,6}\s/
/** Without lists, by paragraph; paragraphs shorter than this many characters do not count as "an item" */
export const PARA_MIN = 20

/** Split the one-line "done criteria" into items: by semicolon / full stop / newline; commas do not split ("has a date, has grounding" is two things in one item). */
export function splitDone(done: string): string[] {
  return (done || '').split(R.split).map((s) => s.trim()).filter(Boolean)
}


export function units(content: string): { kind: 'item' | 'paragraph'; texts: string[] } {
  const lines = (content || '').split('\n')
  const items: string[] = []
  const paras: string[] = []
  let fenced = false
  let cur: string[] = []
  let lastItem = -1
  const flush = () => { if (cur.length) { paras.push(cur.join('\n')); cur = [] } }
  for (const l of lines) {
    if (R.fence.test(l)) { fenced = !fenced; flush(); continue }
    if (fenced) continue
    const isHead = HEADING.test(l)
    if (!l.trim() || isHead) { flush(); if (isHead) lastItem = -1; continue }
    if (R.item.test(l)) { items.push(l.replace(R.item_strip, '')); lastItem = items.length - 1 }
    else if (lastItem >= 0) items[lastItem] += '\n' + l
    cur.push(l)
  }
  flush()
  if (items.length) return { kind: 'item', texts: items }
  return { kind: 'paragraph', texts: paras.filter((p) => p.replace(/\s/g, '').length >= PARA_MIN) }
}

const hasCite = (s: string) => R.cite.test(s) || R.note_link.test(s) || R.link.test(s)
const halfwidth = (s: string) => s.replace(/[\uff10-\uff19]/g, (c) => String(c.charCodeAt(0) - 0xff10))
const opening = (content: string) => (content || '').split('\n').filter((l) => l.trim() && !HEADING.test(l)).slice(0, 2).join('\n')

/** Judge one item. Returns null = code cannot judge it (for you to judge). */
export function checkDoneItem(item: string, content: string): { status: 'pass' | 'fail'; why: string } | null {
  // Match English heading names before removing spaces for the legacy CJK rules.
  const englishSections = R.sections_en.exec((item || '').trim())
  if (englishSections) {
    const listed = englishSections[1] || englishSections[2]
    const names = (englishSections[2] ? listed.split(/,|\band\b/i) : listed.split(',')).map((s) => s.trim()).filter(Boolean)
    const normalize = (s: string) => s.replace(/\s+/g, '').toLowerCase()
    const heads = parseHeadings(content).map((h) => normalize(h.text))
    const missing = names.filter((n) => !heads.some((h) => h.includes(normalize(n))))
    return missing.length
      ? { status: 'fail', why: t(DONE_WHY.sections_missing, { missing: missing.join(t(', ')) }) }
      : { status: 'pass', why: t(DONE_WHY.sections_ok, { n: names.length }) }
  }
  const txt = halfwidth((item || '').replace(/\s+/g, ''))
  const words = wordCount(content)
  let m: RegExpMatchArray | null
  if ((m = txt.match(R.max)) || (m = txt.match(R.max2))) {
    const n = Number(m[1])
    return words <= n ? { status: 'pass', why: t(DONE_WHY.max_ok, { words }) } : { status: 'fail', why: t(DONE_WHY.max_over, { words, over: words - n }) }
  }
  if ((m = txt.match(R.min)) || (m = txt.match(R.min2))) {
    const n = Number(m[1])
    return words >= n ? { status: 'pass', why: t(DONE_WHY.min_ok, { words }) } : { status: 'fail', why: t(DONE_WHY.min_short, { words, short: n - words }) }
  }
  if (R.nonempty.test(txt)) {
    return words > 0 ? { status: 'pass', why: t(DONE_WHY.nonempty_ok, { words }) } : { status: 'fail', why: t(DONE_WHY.nonempty_no) }
  }
  if ((m = txt.match(R.sections)) || (m = txt.match(R.sections2))) {
    const names = m[1].split(R.section_split).map((s) => s.replace(R.section_lead, '').trim()).filter((s) => s && s.length <= 8)
    if (names.length) {
      const heads = parseHeadings(content).map((h) => h.text)
      const missing = names.filter((n) => !heads.some((h) => h.includes(n)))
      return missing.length ? { status: 'fail', why: t(DONE_WHY.sections_missing, { missing: missing.join(t(', ')) }) } : { status: 'pass', why: t(DONE_WHY.sections_ok, { n: names.length }) }
    }
  }
  if (R.conclusion.test(txt)) {
    const heads = parseHeadings(content)
    const firstHead = heads[0]?.text ?? ''
    const ok = HEAD_I.test(firstHead) || R.conclusion_open.test(opening(content))
    return ok ? { status: 'pass', why: t(DONE_WHY.conclusion_ok) } : { status: 'fail', why: t(DONE_WHY.conclusion_no) }
  }
  // "every item / each ... has a date", "... has grounding / source / citation / factual support" -- the two may be written in the same item ("has a date, has grounding"); judge each separately
  const wantDate = R.date_want.test(txt)
  const wantCite = R.cite_want.test(txt)
  if (wantDate || wantCite) {
    const u = units(content)
    // The unit is spliced into the key before lookup (one dictionary entry per unit): the Chinese wording repeats the unit word
    const unit = u.kind === 'item' ? 'items' : 'paragraphs'
    const tu = (tpl: string, p: Record<string, number>) => t(tpl.replace('{unit}', unit), p)
    if (!u.texts.length) return { status: 'fail', why: t(DONE_WHY.no_units) }
    // "numbers have sources": only units containing digits
    const scope = R.numeric_only.test(txt) && wantCite ? u.texts.filter((s) => /\d/.test(s)) : u.texts
    if (!scope.length) return { status: 'pass', why: t(DONE_WHY.no_numbers) }
    const parts: string[] = []
    let fail = false
    if (wantDate) {
      const miss = scope.filter((s) => !R.date.test(s)).length
      if (miss) { fail = true; parts.push(tu(DONE_WHY.date_miss, { n: scope.length, miss })) } else parts.push(tu(DONE_WHY.date_ok, { n: scope.length }))
    }
    if (wantCite) {
      const miss = scope.filter((s) => !hasCite(s)).length
      if (miss) { fail = true; parts.push(tu(DONE_WHY.cite_miss, { n: scope.length, miss })) } else parts.push(tu(DONE_WHY.cite_ok, { n: scope.length }))
    }
    return { status: fail ? 'fail' : 'pass', why: parts.join(t('; ')) }
  }
  return null
}

/** The whole "done criteria" sentence -> per-item status. `checked` is the item texts the user ticked. */
export function checkDone(done: string, content: string, checked: string[] = []): DoneItem[] {
  return splitDone(done).map((text) => {
    const r = checkDoneItem(text, content)
    if (r) return { text, status: r.status, why: r.why, checked: false }
    return { text, status: 'manual', why: '', checked: checked.includes(text) }
  })
}

/** For the badge: how many passed / how many in total (user-judged ones count as passed only when ticked). */
export function doneSummary(items: DoneItem[]): { ok: number; total: number; failing: number } {
  const ok = items.filter((i) => i.status === 'pass' || (i.status === 'manual' && i.checked)).length
  return { ok, total: items.length, failing: items.filter((i) => i.status === 'fail').length }
}
