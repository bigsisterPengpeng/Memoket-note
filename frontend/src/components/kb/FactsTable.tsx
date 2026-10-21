import { useEffect, useState } from 'react'

import { kbDashboard, memoryFacts, type FactsFilter, type FactsPage, type KbDashboard } from '../../api'
import { ExampleFacts, FactList, KbSection, Pager, type KbActions } from './KbBits'
import Icon from '../Icon'
import { t } from '../../i18n'

const LIMIT = 50

/** Fact table: a row of filters + list + paging. Filter conditions come from the id's query string (kb:facts?kind=plan). */
export default function FactsTable({ query, actions }: { query: string; actions: KbActions }) {
  const [filter, setFilter] = useState<FactsFilter>(() => Object.fromEntries(new URLSearchParams(query)) as FactsFilter)
  const [page, setPage] = useState<FactsPage | null>(null)
  const [meta, setMeta] = useState<KbDashboard | null>(null)
  useEffect(() => { setFilter(Object.fromEntries(new URLSearchParams(query)) as FactsFilter) }, [query])
  useEffect(() => { kbDashboard().then(setMeta).catch(() => {}) }, [])
  useEffect(() => {
    let alive = true
    memoryFacts({ ...filter, limit: LIMIT, offset: filter.offset ?? 0 }).then((p) => { if (alive) setPage(p) }).catch(() => {})
    return () => { alive = false }
  }, [filter])
  const set = (k: keyof FactsFilter, v: string) => setFilter((f) => ({ ...f, [k]: v || undefined, offset: 0 }))

  return (
    <div className="kb-page">
      <div className="kb-head">
        <h2 className="kb-note-title"><Icon n="bx-table" className="muted" /> {t('Fact table')}</h2>
        {/* On an empty library this line talks about a row of filters that doesn't exist below — the explanation must follow what's in front of you */}
        {!(meta && meta.stats.facts === 0) && (
          <div className="muted" style={{ fontSize: 'var(--t-md)' }}>{t('Filter by type / speaker / topic / entity / confidence. To find by keyword, use the search on the home page or ⌘K.')}</div>
        )}
      </div>
      {}
      {meta && meta.stats.facts === 0 ? (
        <div className="kb-empty">
          <Icon n="bx-table" />
          <h3>{t('The knowledge base is still empty, so the fact table is empty too')}</h3>
          <p className="muted">{t('Import a meeting recording or a batch of notes, and every extracted sentence lands in this table, filterable by type / speaker / topic / entity.')}</p>
          <div className="row" style={{ gap: 8 }}>
            <button className="primary" onClick={() => window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'app:import' }))}><Icon n="bx-import" /> {t('Import')}</button>
            <button onClick={() => actions.onOpen('kb')}><Icon n="bx-left-arrow-alt" /> {t('Back to knowledge base overview')}</button>
          </div>
          <ExampleFacts />
        </div>
      ) : (<>
      <div className="filter-row">
        <select aria-label={t('Type')} value={filter.kind ?? ''} onChange={(e) => set('kind', e.target.value)}>
          <option value="">{t('All types')}</option>
          {meta?.kinds.map((k) => <option key={k.kind} value={k.kind}>{k.kind} · {k.facts}</option>)}
        </select>
        <select aria-label={t('Speaker')} value={filter.who ?? ''} onChange={(e) => set('who', e.target.value)}>
          <option value="">{t('All speakers')}</option>
          {meta?.speakers.map((s) => <option key={s.who} value={s.who}>{s.who} · {s.facts}</option>)}
        </select>
        <input aria-label={t('Filter by topic')} placeholder={t('Topic (incl. subtopics)')} value={filter.topic ?? ''} onChange={(e) => set('topic', e.target.value)} />
        <input aria-label={t('Filter by entity')} placeholder={t('Entity')} value={filter.entity ?? ''} onChange={(e) => set('entity', e.target.value)} />
        <select aria-label={t('Confidence')} value={filter.conf_min ?? ''} onChange={(e) => set('conf_min', e.target.value)}>
          <option value="">{t('Any confidence')}</option>
          <option value="med">{t('≥ medium')}</option>
          <option value="high">{t('high')}</option>
        </select>
        {(filter.kind || filter.who || filter.topic || filter.entity || filter.conf_min) && (
          <button className="icon-btn" title={t('Clear filters')} onClick={() => setFilter({})}><Icon n="bx-x" /></button>
        )}
      </div>
      {!page ? <p className="muted"><span className="spinner" /> {t('Loading…')}</p> : (
        <KbSection title={t('{n} items', { n: page.total })}>
          <FactList facts={page.facts} actions={actions} showTopics />
          <Pager total={page.total} limit={page.limit} offset={page.offset} onPage={(o) => setFilter((f) => ({ ...f, offset: o }))} />
        </KbSection>
      )}
      </>)}
    </div>
  )
}
