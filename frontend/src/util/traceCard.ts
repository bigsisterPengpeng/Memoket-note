
import type { Fact } from '../api'
import { t } from '../i18n'

export type TraceSummary = { count: number; first: Fact | null; last: Fact | null; related: Fact[] }

const dated = (f: Fact) => /^\d{4}/.test(f.when || '')

export function summarizeTrace(facts: Fact[]): TraceSummary {
  const withDate = facts.filter(dated).sort((a, b) => (a.when < b.when ? -1 : a.when > b.when ? 1 : 0))
  const first = withDate[0] ?? null
  const lastCand = withDate[withDate.length - 1] ?? null
  const last = lastCand && first && lastCand.id !== first.id ? lastCand : null
  const used = new Set([first?.id, last?.id].filter(Boolean))
  const related = facts.filter((f) => !used.has(f.id)).slice(0, 2)
  return { count: facts.length, first, last, related }
}

/** Words the segmenter does not know (a two-character CJK word split into two single characters): the editor joins adjacent single characters into a run (e.g. three characters) + the character the mouse rests on.
 *  Most CJK words are two characters: first query the knowledge base with each **two-character window covering that character** (left, right), use whichever has records (the one with more if both);
 *  only if neither does, query the whole run. Measured: the `terms` returned by `/recall` are unreliable -- when both two-character grams of a three-character run are in the library it merges them into the whole run. */
export function candidates(run: string, focus: number): string[] {
  const out: string[] = []
  if (run.length >= 2) {
    if (focus >= 1) out.push(run.slice(focus - 1, focus + 1))
    if (focus + 2 <= run.length) out.push(run.slice(focus, focus + 2))
  }
  if (!out.includes(run)) out.push(run)
  return out
}


export function emptyReason(phrase: string, why?: '' | 'no_terms' | 'weak', kbEmpty?: boolean): string {
  if (kbEmpty) return t('The knowledge base is still empty — save notes or meeting records into it first.')
  if (why === 'no_terms') return t('“{phrase}” is too short or too generic to look up.', { phrase })
  return t('No “{phrase}” in the knowledge base.', { phrase })
}
