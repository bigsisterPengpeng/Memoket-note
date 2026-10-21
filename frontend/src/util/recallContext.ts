
import { stripForRecall } from './wordCount'
import { t } from '../i18n'

export const RECALL_TAIL_CHARS = 500
export const RECALL_MIN_CHARS = 8
/** How many characters of context come before the cursor paragraph (only the previous paragraph, never further back across blank lines) */
export const RECALL_CONTEXT_BEFORE = 200


export type RecallQuery = { query: string; mode: 'cursor' | 'tail'; before: string }

export function recallQuery(content: string, paragraph: string, tailChars = RECALL_TAIL_CHARS): RecallQuery {
  const para = (paragraph || '').trim()
  const p = stripForRecall(para).trim()
  if (p.length >= RECALL_MIN_CHARS && !/^#{1,6}\s/.test(p)) {
    const idx = content.indexOf(para)
    let before = (idx > 0 ? content.slice(Math.max(0, idx - RECALL_CONTEXT_BEFORE), idx) : '').replace(/\s+$/, '')
    const cut = before.lastIndexOf('\n\n')
    if (cut >= 0) before = before.slice(cut + 2)
    before = before.trim()
    if (/^#{1,6}\s/.test(before)) before = ''
    const q = stripForRecall((before ? before + '\n' : '') + para).trim()
    return { query: q, mode: 'cursor', before: stripForRecall(before).trim() }
  }
  return { query: stripForRecall(content.slice(-tailChars)).trim(), mode: 'tail', before: '' }
}


export function termFromBefore(term: string, paragraph: string, before: string): boolean {
  if (!term || !before) return false
  const inPara = stripForRecall(paragraph || '').includes(term)
  return !inPara && before.includes(term)
}


export const FROM_BEFORE_NOTE = 'From the previous paragraph'


export function evidencePool(
  evidence: { term: string; why: string; units: number }[] | null | undefined,
  terms: string[],
): string[] {
  if (evidence && evidence.length) return evidence.map((e) => e.term)
  if (evidence) return []
  return terms
}


export function cardFromBefore(factText: string, pool: string[], paragraph: string, before: string): boolean {
  const body = stripForRecall(factText || '').toLowerCase()
  if (!body || !before) return false
  const inPara = stripForRecall(paragraph || '')
  let fromBefore = false
  for (const t of pool) {
    if (!t || !body.includes(t)) continue
    if (termFromBefore(t, paragraph, before)) fromBefore = true
    else if (inPara.includes(t)) return false     // (1) veto
  }
  return fromBefore
}

/** Whether this card has hit words from the current paragraph that **can be checked verbatim**.
 *
 * `!cardFromBefore` does not imply "from the current paragraph": it also includes cards "recalled by segmentation / semantics, where the frontend cannot explain
 * why with substrings". Only when a hit word appears in both the current paragraph and the fact text is the "current paragraph" mark applied. */
export function cardFromCurrent(factText: string, pool: string[], paragraph: string): boolean {
  const body = stripForRecall(factText || '').toLowerCase()
  const para = stripForRecall(paragraph || '').toLowerCase()
  if (!body || !para) return false
  return pool.some((term) => {
    const t = (term || '').toLowerCase()
    return !!t && para.includes(t) && body.includes(t)
  })
}

const norm = (s: string) => (s || '').toLowerCase().replace(/[\s\p{P}\p{S}]+/gu, '')
const grams = (s: string) => { const g = new Set<string>(); for (let i = 0; i < s.length - 1; i++) g.add(s.slice(i, i + 2)); return g }

export const IN_BODY_MIN_OVERLAP = 0.8
const IN_BODY_MIN_GRAMS = 8

/** Whether this fact is original words the user already wrote in the body. A whole-sentence substring counts directly; otherwise bigram overlap >= 0.8 with **any paragraph** of the body.
 *  Compared per paragraph, not against the whole note: in a 26k-character note almost any bigram can be found somewhere, and a whole-note comparison would judge every fact "already in body". */
export function factInBody(fact: string, content: string): boolean {
  const f = norm(fact)
  if (f.length < 6) return false
  const c = norm(content)
  if (c.includes(f)) return true
  const fg = grams(f)
  if (fg.size < IN_BODY_MIN_GRAMS) return false
  for (const para of content.split(/\n\s*\n/)) {
    const pg = grams(norm(para))
    if (pg.size === 0) continue
    let hit = 0
    for (const g of fg) if (pg.has(g)) hit++
    if (hit / fg.size >= IN_BODY_MIN_OVERLAP) return true
  }
  return false
}


export function evidenceWhy(e: { why: string; units: number }): string {
  const why = e.why === 'vocab' ? t('a term in your knowledge base')
    : e.why === 'span' ? t('exact phrase match')
      : t('counts only together with other terms')
  return e.units > 0 ? `${why} · ` + t('mentioned in {n} records', { n: e.units }) : why
}


export function traceRecallHint(factCount: number, recalled?: number | null): string {
  if (factCount > 0) return ''
  const n = recalled ?? 0
  if (n <= 0) return ''
  return t('Those {n} records are visible in the Memory tab for the same passage — Trace needs a time order, and that step did not come together.', { n })
}


export const NO_EVIDENCE_LINE = 'no evidence to show for this paragraph'


export function evidenceLine(
  mode: 'cursor' | 'tail',
  evidence: { term: string; why: string; units: number }[] | null | undefined,
  terms: string[],
  ctx?: { paragraph: string; before: string } | null,
): string {
  const head = mode === 'cursor' ? t('Searched by the paragraph at the cursor') : t('Searched by the end of the note')
  const why = (e: { term: string; why: string; units: number }) => {
    const base = evidenceWhy(e)
    return ctx && termFromBefore(e.term, ctx.paragraph, ctx.before) ? `${t(FROM_BEFORE_NOTE)} · ${base}` : base
  }
  if (evidence && evidence.length) {
    return head + t(', hits: ') + evidence.slice(0, 3).map((e) => e.term + t(' ({why})', { why: why(e) })).join(t(', '))
  }
  if (evidence) return head + t(', {note}', { note: t(NO_EVIDENCE_LINE) })
  if (!terms.length) return head
  const shown = terms.slice(0, 6).map((term) =>
    ctx && termFromBefore(term, ctx.paragraph, ctx.before) ? term + t(' ({why})', { why: t(FROM_BEFORE_NOTE) }) : term)
  return head + t(', hits: ') + shown.join(t(', '))
}
