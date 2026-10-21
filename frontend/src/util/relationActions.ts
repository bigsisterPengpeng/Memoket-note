
import { mergeFacts, supersedeFact, type Fact, type MemoryRelationKind } from '../api'
import { toast } from '../toast'
import { friendlyError } from './friendlyError'
import { t } from '../i18n'

export type RelationLike = { relation: MemoryRelationKind; fact_ids: string[]; facts: Fact[] }

const IGNORED_KEY = 'memoket-note-ignored-relations'

export function relationKey(r: RelationLike): string { return r.relation + ':' + r.fact_ids.join(',') }

export function ignoredSet(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(IGNORED_KEY) || '[]')) } catch { return new Set() }
}

export function ignoreRelation(key: string): Set<string> {
  const next = ignoredSet(); next.add(key)
  try { localStorage.setItem(IGNORED_KEY, JSON.stringify([...next].slice(-200))) } catch { /* does not matter */ }
  window.dispatchEvent(new CustomEvent('relation-ignored', { detail: key }))
  return next
}

/** "New replaces old": when the library has two, mark the earlier one as superseded by the later. When this body sentence is not yet a record, say where to add it. */
export async function supersedeRelation(rel: RelationLike): Promise<boolean> {
  const old = rel.facts[0]
  const latest = rel.facts[rel.facts.length - 1]
  if (!old || !latest || old.id === latest.id) { toast(t('This sentence is not a knowledge base record yet — add one in the Citations tab first, then mark it as superseding')); return false }
  try { await supersedeFact(old.id, latest.id); toast(t('Marked: the old record is superseded by the new one')); ignoreRelation(relationKey(rel)); return true }

  catch (e) { toast(t('Could not mark: {err}', { err: friendlyError(e) }), 'error'); return false }
}

/** "Merge into one": keep the later one and mark the earlier as superseded by it (merged); remember the result so this pair is not raised again */
export async function mergeRelation(rel: RelationLike): Promise<boolean> {
  const [a, b] = rel.facts
  if (!a || !b) return false
  try { await mergeFacts(b.id, a.id); toast(t('Merged into one: kept {which}', { which: b.when || t('the later one') })); ignoreRelation(relationKey(rel)); return true }
  catch (e) { toast(t('Could not merge: {err}', { err: friendlyError(e) }), 'error'); return false }
}

/** "Add it": insert those conditions from the knowledge base into the body with citations */
export function fillInText(rel: RelationLike): string {
  return rel.facts.map((f) => `${f.text} [${f.id}]`).join('\n')
}

/** "Cite this": the latest one, with its source */
export function citeText(rel: RelationLike): string {
  const f = rel.facts[rel.facts.length - 1]
  return f ? `${f.text} [${f.id}]` : ''
}

/** The body already cites the latest one */
export function alreadyCited(rel: RelationLike, content: string): boolean {
  const f = rel.facts[rel.facts.length - 1]
  return !!f && content.includes(`[${f.id}]`)
}
