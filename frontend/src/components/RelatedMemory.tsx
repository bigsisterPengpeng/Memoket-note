import { useEffect, useRef, useState } from 'react'
import { clickable } from '../util/clickable'
import { memoryRelations, memoryScope, recall, SCOPE_LABEL, setMemoryScope, type MemoryScope } from '../api'
import type { Fact, MemoryRelation, RecallEvidence } from '../api'
import { stripForRecall } from '../util/wordCount'
import { cardFromBefore, cardFromCurrent, evidenceLine, evidencePool, factInBody, FROM_BEFORE_NOTE, recallQuery, RECALL_TAIL_CHARS } from '../util/recallContext'
import { KB_EMPTY_NOTE, MARGIN_RULE, noRecordNote, RECALL_FAILED_NOTE, RELATION_LABEL } from '../editor/marginMemory'
import { citeText, fillInText, ignoreRelation, ignoredSet, mergeRelation, relationKey, supersedeRelation } from '../util/relationActions'
import Icon from './Icon'
import { requestTrayAdd } from '../util/tray'
import { t } from '../i18n'

const REL_LABEL: Record<MemoryRelation['relation'], { text: string; cls: string; icon: string }> = {
  conflict: { text: 'Conflict', cls: 'rel-conflict', icon: 'bx-error' },
  continuation: { text: 'Continuation', cls: 'rel-continuation', icon: 'bx-trending-up' },
  corroborated: { text: 'Corroborated', cls: 'rel-corroborated', icon: 'bx-check-shield' },
  unsupported: { text: 'Unsupported', cls: 'rel-unsupported', icon: 'bx-question-mark' },
  accumulation: { text: 'Accumulation', cls: 'rel-accumulation', icon: 'bx-layer-plus' },
  merge: { text: 'Merge', cls: 'rel-merge', icon: 'bx-git-merge' },
}

const REL_HELP: Record<MemoryRelation['relation'], string> = {
  conflict: 'inconsistent with an existing record', continuation: 'follows on from an existing record', corroborated: 'an existing record supports it',
  unsupported: 'no support found yet', accumulation: 'can be added to an existing record', merge: 'two records can be merged into one',
}

/** Recall is local zero-model retrieval, a short debounce is enough; relation judgment is heavier and still waits until the user really rests on a paragraph. */
const RECALL_IDLE_MS = 450
const RELATION_IDLE_MS = 900
const TAIL_CHARS = RECALL_TAIL_CHARS
const MIN_CHARS = 8

const LIST_MAX = 5
/** Ask for a few more, so that after folding the "already in body" ones there are still LIST_MAX */
const RECALL_LIMIT = 8

/**
 * Ambient recall: related facts surface on their own while you write, no
 * query typed -- the "Heads Up"/"Connections pane" pattern several
 * competitors use (Mem, Obsidian's Smart Connections) instead of only
 * offering search-on-demand. Cheap to run this aggressively: /api/memory/recall
 * is a zero-LLM keyword lookup (observed ~30ms), unlike skeleton/edit/magic-tap
 * which hit the LLM and need long debounce windows.
 */
export default function RelatedMemory({ content, paragraph = '', onInsert, kbEmpty = false, noRecordDots = 0 }: {
  /** The paragraph at the cursor: relations are queried for it (not the last 500 characters) */
  paragraph?: string
  content: string
  onInsert: (text: string) => void
  /** The knowledge base has no facts at all: "nothing related found" makes first-time users think it is broken, so show guidance instead */
  kbEmpty?: boolean

  noRecordDots?: number
}) {
  const [facts, setFacts] = useState<Fact[]>([])
  const [loading, setLoading] = useState(false)

  const [terms, setTerms] = useState<string[]>([])

  // described correctly what it was doing, and the thing it did was itself wrong.

  // `null` = this trip was not judged (old backend / the criterion itself threw). Collapsed, the "judged" tier would

  const [evidence, setEvidence] = useState<RecallEvidence[] | null>(null)
  const [whyEmpty, setWhyEmpty] = useState<'' | 'no_terms' | 'weak'>('')
  const [canExpand, setCanExpand] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [mode, setMode] = useState<'cursor' | 'tail'>('tail')

  // Whether a displayed word "came from the previous paragraph" is judged against these two, **not the `paragraph` at render time**

  const [qCtx, setQCtx] = useState<{ paragraph: string; before: string } | null>(null)
  const lastQueried = useRef('')

  // this tier is **the client's own**: no answer arrived at all. Do not collapse the two --
  // collapsed, "the query failed" would be reported as "the knowledge base has nothing related", which is a different lie.
  const [failed, setFailed] = useState(false)

  // the cursor moves from paragraph 1 to paragraph 2 with both requests in flight; if request 1 **arrived later** it used to overwrite paragraph 2's
  // answer with paragraph 1's, and since `lastQueried` was already request 2 -> **it never fixed itself**.
  const recallSeq = useRef(0)
  // Memory scope: when it changes, clear both cache keys so recall and relations both rerun
  const [scope, setScope] = useState<MemoryScope>(() => memoryScope())
  useEffect(() => {
    const on = (e: Event) => { setScope((e as CustomEvent<MemoryScope>).detail); lastQueried.current = ''; lastPara.current = ''; setFacts([]); setRels([]) }
    window.addEventListener('memory-scope-changed', on)
    return () => window.removeEventListener('memory-scope-changed', on)
  }, [])

  // Relations: query once the cursor rests on a paragraph for 900ms. Only meaningful for paragraphs with concrete numbers / dates (the backend returns empty when there are none).
  const [rels, setRels] = useState<MemoryRelation[]>([])
  const [relBusy, setRelBusy] = useState(false)
  const [ignored, setIgnored] = useState<Set<string>>(() => ignoredSet())
  const lastPara = useRef('')
  const relSeq = useRef(0)
  useEffect(() => {
    const p = stripForRecall(paragraph).trim()
    if (p.length < MIN_CHARS || !/\d/.test(p)) {
      ++relSeq.current; lastPara.current = ''; setRels([]); setRelBusy(false); return
    }
    if (p === lastPara.current) return
    // When the paragraph changes, the previous paragraph's relations are void immediately. Old cards must not hang under the new paragraph during the 900ms debounce.
    lastPara.current = p
    const seq = ++relSeq.current
    setRels([])
    setRelBusy(true)
    let started = false
    const t = setTimeout(() => {
      started = true
      memoryRelations(p)
        .then((r) => { if (seq === relSeq.current) setRels(r.relations) })

        // This used to be an empty `catch` too, so "this paragraph's relation to the knowledge base" showed the previous paragraph's cards.
        .catch(() => { if (seq === relSeq.current) { lastPara.current = ''; setRels([]) } })
        .finally(() => { if (seq === relSeq.current) setRelBusy(false) })
    }, RELATION_IDLE_MS)
    return () => {
      clearTimeout(t)
      // When dependencies changed but the cleaned paragraph did not, cleanup cancels the timer first; release the cache key so the next pass re-arms.
      if (!started && lastPara.current === p) lastPara.current = ''
    }
  }, [paragraph, scope])

  // ignore there and it goes out here, and vice versa (the `relation-ignored` event)
  useEffect(() => {
    const on = () => setIgnored(ignoredSet())
    window.addEventListener('relation-ignored', on)
    return () => window.removeEventListener('relation-ignored', on)
  }, [])
  function ignore(key: string) { setIgnored(ignoreRelation(key)) }
  const supersede = (rel: MemoryRelation) => supersedeRelation(rel)
  const merge = (rel: MemoryRelation) => mergeRelation(rel)
  function fillIn(rel: MemoryRelation) { onInsert(fillInText(rel)); ignore(relationKey(rel)) }
  const visibleRels = rels.filter((r) => !ignored.has(relationKey(r)))


  // the user was writing about Huawei chips at the top while the right pane showed memories about the Hengrui translation at the tail). Zero model, ~100ms each.
  useEffect(() => {
    const q = recallQuery(content, paragraph)
    if (q.query.length < MIN_CHARS) {
      ++recallSeq.current; lastQueried.current = ''; setFacts([]); setTerms([]); setEvidence(null)
      setWhyEmpty(''); setCanExpand(false); setExpanded(false); setQCtx(null); setFailed(false); setLoading(false); return
    }
    if (q.query === lastQueried.current) return
    // Withdraw the old answer as soon as the new paragraph starts searching, instead of waiting for the new request to succeed/fail.
    // That way during the debounce and network wait, the screen never passes off the previous paragraph's memories as the current one's.
    lastQueried.current = q.query
    const seq = ++recallSeq.current
    setFacts([]); setTerms([]); setEvidence(null); setWhyEmpty(''); setQCtx(null); setFailed(false); setCanExpand(false); setExpanded(false)
    setMode(q.mode); setLoading(true)
    let started = false
    const t = setTimeout(() => {
      started = true
      recall(q.query, RECALL_LIMIT)
        .then((r) => {
          if (seq !== recallSeq.current) return       // not the latest request's answer: drop it, do not overwrite with the previous paragraph's
          setFacts(r.facts); setTerms(r.terms ?? []); setEvidence(r.evidence ?? null)
          setWhyEmpty(r.why_empty ?? ''); setCanExpand(!!r.can_expand); setExpanded(!!r.relaxed)
          setMode(q.mode); setQCtx({ paragraph, before: q.before }); setFailed(false)
        })
        .catch(() => {
          if (seq !== recallSeq.current) return
          // **The previous paragraph's answer is void on the spot**: this used to be an empty `catch`, so the "searched by this paragraph,

          // on the real shell (a five-paragraph note; paragraph 2's line was identical to paragraph 1's).
          lastQueried.current = ''                    // cleared, so the next dependency change can still ask
          setFacts([]); setTerms([]); setEvidence(null); setWhyEmpty(''); setCanExpand(false); setExpanded(false); setMode(q.mode); setQCtx(null); setFailed(true)
        })
        .finally(() => { if (seq === recallSeq.current) setLoading(false) })
    }, RECALL_IDLE_MS)
    return () => {
      clearTimeout(t)
      // When content changed but the effective query did not, we must not "cancel the old timer and then return early on the same key".
      if (!started && lastQueried.current === q.query) lastQueried.current = ''
    }
  }, [content, paragraph, scope])
  const expandRecall = () => {
    const q = recallQuery(content, paragraph)
    if (q.query.length < MIN_CHARS) return
    const seq = ++recallSeq.current
    setLoading(true); setFailed(false)
    recall(q.query, RECALL_LIMIT, true)
      .then((r) => {
        if (seq !== recallSeq.current) return
        setFacts(r.facts); setTerms(r.terms ?? []); setEvidence(r.evidence ?? null)
        setWhyEmpty(r.why_empty ?? ''); setCanExpand(false); setExpanded(true)
        setMode(q.mode); setQCtx({ paragraph, before: q.before })
      })
      .catch(() => { if (seq === recallSeq.current) setFailed(true) })
      .finally(() => { if (seq === recallSeq.current) setLoading(false) })
  }

  const candidates = facts.filter((f) => !factInBody(f.text, content))
  const inBody = facts.filter((f) => factInBody(f.text, content))

  // Recall and `out[:8]` are untouched -- only "how it is said" changed, not "what is fetched".
  const pool = evidencePool(evidence, terms)
  const fromBefore = (text: string) => !!qCtx && cardFromBefore(text, pool, qCtx.paragraph, qCtx.before)
  const fromCurrent = (text: string) => !!qCtx && cardFromCurrent(text, pool, qCtx.paragraph)
  // Adding the previous paragraph helps short paragraphs with context, but with mixed hits show the current paragraph's results first, so old context does not take the first screen.
  // Only move cards the criterion explicitly identifies as "brought back by the previous paragraph"; unclear ones keep the backend's original order.
  const fresh = [
    ...candidates.filter((f) => fromCurrent(f.text)),
    ...candidates.filter((f) => !fromCurrent(f.text) && !fromBefore(f.text)),
    ...candidates.filter((f) => fromBefore(f.text)),
  ]
    .slice(0, LIST_MAX)

  // Before, when facts were empty the whole component (title included) returned null -- this is the
  // panel's only content across the "Writing"/"Related memory"/"Knowledge base" tabs; clicking into the "Related memory"
  // tab showed a completely blank area, and users could not tell "not enough written to trigger a search yet" from "the panel
  // is broken". Keep the title, and use different copy for "content too short to trigger yet" and "searched but found nothing",
  // the two different empty states.
  const tooShort = stripForRecall(content.slice(-TAIL_CHARS)).trim().length < MIN_CHARS

  return (
    <div>
      <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '4px 0 8px', display: 'flex', gap: 6, alignItems: 'center' }}>
        {}
        <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t('Automatically finds records related to the current paragraph.')}</span>
        {loading && <span className="spinner" style={{ flexShrink: 0 }} />}
        {/* Memory scope: one library mixes meeting records / notes / imports; when writing your own retrospective, keep other people's reports out */}
        <select className="select-sm" value={scope} onChange={(e) => setMemoryScope(e.target.value as MemoryScope)} title={t('Recall, relations, Continue, Expand, Verify, digests and writing-plan materials all use only this scope')}
                style={{ marginInlineStart: 'auto', flexShrink: 0 }}>
          {(Object.keys(SCOPE_LABEL) as MemoryScope[]).map((k) => <option key={k} value={k}>{t(SCOPE_LABEL[k])}</option>)}
        </select>
      </p>
      {kbEmpty ? (
        <div className="muted mem-legend" style={{ fontSize: 'var(--t-xs)', margin: '0 0 8px', lineHeight: 1.7 }}>
          {t(KB_EMPTY_NOTE)}
          <button className="primary" style={{ fontSize: 'var(--t-sm)', padding: '2px 8px', marginInlineStart: 6 }}
                  onClick={() => window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'app:import' }))}>
            <Icon n="bx-import" /> {t('Import')}
          </button>
        </div>
      ) : (
        <div className="mem-legend" style={{ margin: '0 0 8px' }}>
          <details className="mem-help">
            <summary>{t('About the margin dots')}</summary>
            <p>{t(MARGIN_RULE)}.</p>
            <div className="mem-rel-help">
              {(Object.keys(RELATION_LABEL) as (keyof typeof RELATION_LABEL)[]).map((k) => (
                <span key={k}><span className={'mm-dot mm-' + k} />{t(RELATION_LABEL[k])}: {t(REL_HELP[k])}</span>
              ))}
            </div>
          </details>
          {noRecordDots > 0 && <p className="muted mem-no-record-note">{noRecordNote(noRecordDots)}</p>}
        </div>
      )}
      {(visibleRels.length > 0 || relBusy) && (
        <div className="stack" style={{ gap: 6, marginBottom: 10 }}>
          <div className="muted" style={{ fontSize: 'var(--t-xs)' }}>{t('How the paragraph at the cursor relates to the knowledge base')}{relBusy && <> <span className="spinner" /></>}</div>
          {visibleRels.map((r) => {
            const L = REL_LABEL[r.relation]
            const key = relationKey(r)
            return (
              <div key={key} className={'card rel-card ' + L.cls}>
                <div className="row" style={{ gap: 6, alignItems: 'center' }}>
                  <span className={'badge ' + L.cls}><Icon n={L.icon} /> {t(L.text)}</span>
                  <span style={{ fontSize: 'var(--t-md)', flex: 1 }}>{r.say}</span>
                </div>
                {r.facts.length > 0 && (
                  <div className="stack" style={{ gap: 2, marginTop: 4 }}>
                    {r.facts.map((f) => (
                      <div key={f.id} className="muted" style={{ fontSize: 'var(--t-sm)', cursor: 'pointer' }} title={t('Open this record')}
                           {...clickable(() => window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:fact:' + f.id })))}>
                        <span className="badge" style={{ marginInlineEnd: 4 }}>{f.when || '—'}</span>{f.text}
                      </div>
                    ))}
                  </div>
                )}
                <div className="row" style={{ gap: 4, marginTop: 6 }}>
                  {r.facts.length > 0 && (content.includes(`[${r.facts[r.facts.length - 1].id}]`)
                    ? <span className="badge ok" title={t('Already cited in the note')}>{t('Cited')}</span>
                    : <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} onClick={() => onInsert(citeText(r))}>{t('Cite this')}</button>)}
                  {r.relation === 'conflict' && <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} onClick={() => void supersede(r)}>{t('New supersedes old')}</button>}
                  {r.relation === 'accumulation' && r.facts.length > 0 && <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} onClick={() => fillIn(r)}>{t('Fill in')}</button>}
                  {r.relation === 'merge' && r.facts.length === 2 && <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} onClick={() => void merge(r)}>{t('Merge into one')}</button>}
                  {r.facts.length > 0 && <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} title={t('Add to materials; the AI prioritizes them when writing this note')}
                          onClick={() => r.facts.forEach((f) => requestTrayAdd({ kind: 'fact', ref_id: f.id, title: f.when || '', excerpt: f.text }))}>{t('Add to materials')}</button>}
                  <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} onClick={() => ignore(key)}>{t('Ignore')}</button>
                </div>
              </div>
            )
          })}
        </div>
      )}
      {/* Why I am shown these (step one of A5): which words it searched by, cursor paragraph or tail */}
      {facts.length > 0 && !loading && (
        <p className="muted mem-terms" style={{ fontSize: 'var(--t-xs)', margin: '0 0 6px' }}>
          {expanded ? t('Weak matches from the expanded search — check each before citing.') : evidenceLine(mode, evidence, terms, qCtx)}
        </p>
      )}
      {facts.length === 0 && !loading && !kbEmpty && (
        <p className={'muted' + (failed ? ' mem-failed' : '')} style={{ fontSize: 'var(--t-md)' }}>
          {}
          {failed ? t(RECALL_FAILED_NOTE)
            : tooShort ? t('Write a few more characters and the search starts automatically.')

            : whyEmpty === 'no_terms' ? t('{where} has no searchable keywords (specific terms such as names, projects, dates or numbers).', { where: mode === 'cursor' ? t('The paragraph at the cursor') : t('The end of the note') })
            : whyEmpty === 'weak' ? t('No knowledge base record matches two of the keywords from {where} at once — unrelated records are not forced in.', { where: mode === 'cursor' ? t('The paragraph at the cursor') : t('The end of the note') })
            : t('Nothing related found in the knowledge base yet.')}
          {!failed && canExpand && <>{' '}<button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} onClick={expandRecall}>{t('Expand search')}</button></>}
        </p>
      )}
      {facts.length > 0 && fresh.length === 0 && !loading && (
        <p className="muted" style={{ fontSize: 'var(--t-md)' }}>{t('All {n} recalled records are already quoted in the note (collapsed below).', { n: inBody.length })}</p>
      )}
      {fresh.map((f) => (
        <div
          className="card memory-card"
          key={f.id}
        >
          <div style={{ fontSize: 'var(--t-md)' }}>{f.text}</div>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
            <span className="row" style={{ gap: 4 }}>
              {f.when ? <span className="badge">{f.when}</span> : null}
              {}
              {fromBefore(f.text) && (
                <span className="badge mem-card-from-before" title={t('This record comes from the paragraph before the cursor, not the current one')}>
                  {t(FROM_BEFORE_NOTE)}
                </span>
              )}
              {fromCurrent(f.text) && mode === 'cursor' && (
                <span className="badge mem-card-from-current" title={t('This record was recalled from the current paragraph')}>{t('Current paragraph')}</span>
              )}
              {}
              {content.includes(`[${f.id}]`) && <span className="badge ok" title={t('Already cited in the note')}>{t('Cited')}</span>}
            </span>
            <span className="memory-card-actions">
              <button title={t('Open this fact')}
                      onClick={(e) => { e.stopPropagation(); window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:fact:' + f.id })) }}>
                <Icon n="bx-link-external" /> {t('View')}
              </button>
              <button title={t('Insert the original text with a verifiable source at the cursor')} onClick={(e) => { e.stopPropagation(); onInsert(`${f.text} [${f.id}]`) }}>
                <Icon n="bx-link" /> {t('Quote')}
              </button>
              {}
              <button className="icon-btn" title={t('Add to materials; the AI prioritizes them when writing this note')}
                      onClick={(e) => { e.stopPropagation(); requestTrayAdd({ kind: 'fact', ref_id: f.id, title: f.when || '', excerpt: f.text }) }}>
                <Icon n="bx-layer-plus" />
              </button>
            </span>
          </div>
        </div>
      ))}
      {inBody.length > 0 && (
        <details className="mem-inbody" style={{ marginTop: 8 }}>
          <summary className="muted" style={{ fontSize: 'var(--t-sm)', cursor: 'pointer' }}>{t('{n} already in the note (your own words, collapsed)', { n: inBody.length })}</summary>
          {inBody.map((f) => (
            <div key={f.id} className="muted" style={{ fontSize: 'var(--t-sm)', margin: '6px 0 0 8px', cursor: 'pointer' }} title={t('Open this record')}
                 {...clickable(() => window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:fact:' + f.id })))}>
              {f.when ? <span className="badge" style={{ marginInlineEnd: 4 }}>{f.when}</span> : null}{f.text}
            </div>
          ))}
        </details>
      )}
    </div>
  )
}
