/** Knowledge-base home: search on the first screen, then numbers, the last 12 months, top topics, top entities, recently ingested. */
import { useEffect, useState } from 'react'
import { entityIcon } from '../../util/entityIcon'

import { kbDashboard, recall, type Fact, type FactDetail, type KbDashboard as Data } from '../../api'
import { Chip, ExampleFacts, FactList, KbSection, MiniBars, StatTile, type KbActions } from './KbBits'
import { isSpeakerTag } from '../../util/kbNoise'
import { takePendingKbQuery } from '../../util/pendingKbQuery'
import ConflictInbox from './ConflictInbox'
import Icon from '../Icon'
import { t } from '../../i18n'
import WritingFlow from '../WritingFlow'

const toDetail = (f: Fact): FactDetail => ({ id: f.id, text: f.text, when: f.when, kind: f.kind, who: '', conf: '', topics: [], entities: [], unit: '' })

export default function KbDashboard({ actions }: { actions: KbActions }) {
  const [data, setData] = useState<Data | null>(null)
  const [q, setQ] = useState(takePendingKbQuery)
  const [hits, setHits] = useState<{ facts: FactDetail[]; took: number; terms: string[] } | null>(null)
  const [searching, setSearching] = useState(false)

  useEffect(() => { kbDashboard().then(setData).catch(() => setData(null)) }, [])

  // When the sidebar note search finds nothing, it offers a way out: "search the same term in the knowledge base". The term goes through
  // `pendingKbQuery` (picked up on mount, no betting on timing); if this page is already open it goes through an event.
  // Stuffing a query string into the virtual id would touch a whole chain (knownVirtual / openVirtual / breadcrumb parent chain /

  useEffect(() => {
    const on = (e: Event) => setQ(String((e as CustomEvent).detail || ''))
    window.addEventListener('kb-search', on)
    return () => window.removeEventListener('kb-search', on)
  }, [])

  // Instant results: zero-LLM symbolic retrieval, in milliseconds
  useEffect(() => {
    if (!q.trim()) { setHits(null); return }
    setSearching(true)
    const timer = setTimeout(() => {
      recall(q, 20).then((r) => setHits({ facts: r.facts.map(toDetail), took: r.took_ms, terms: r.terms }))
        .catch(() => setHits({ facts: [], took: 0, terms: [] })).finally(() => setSearching(false))
    }, 250)
    return () => clearTimeout(timer)
  }, [q])

  return (
    <div className="kb-page">
      <div className="workspace-intro">
        <h2>{t('Your work, remembered')}</h2>
        <p className="muted">{t('Knowledge stays in your local library across notes and sessions. Inspect the original evidence, then bring it into your next draft.')}</p>
      </div>
      <WritingFlow current="memory" />
      {/* No search box on an empty library: with not a single fact, searching can only come up empty, and an autoFocused cursor sitting there looks like it's waiting for you to type */}
      {!(data && data.stats.facts === 0) && (
        <div className="kb-search">
          <Icon n="bx-search" />
          <input aria-label={t('Search the knowledge base')} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('Search the knowledge base: people, events, numbers, dates…')}
                 autoFocus onKeyDown={(e) => { if (e.key === 'Escape') setQ('') }} />
          {searching && <span className="spinner" />}
          {q && <button className="icon-btn" title={t('Clear')} aria-label={t('Clear search')} onClick={() => setQ('')}><Icon n="bx-x" /></button>}
        </div>
      )}

      {}
      {hits ? (
        <KbSection title={t('{n} results', { n: hits.facts.length })}
                   extra={<span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{Math.round(hits.took)} ms{hits.terms.length ? (hits.facts.length ? t(' · Matched terms: ') : t(' · Searched for: ')) + hits.terms.slice(0, 6).join(t(', ')) : ''}</span>}>
          <FactList facts={hits.facts} actions={actions} />
          {}
          {hits.facts.length === 0 && <p className="muted" style={{ fontSize: 'var(--t-sm)' }}>
            {data && data.stats.facts === 0
              ? t('The knowledge base is still empty — import meeting notes or notes first, then there will be something to search here.')
              : t('Try other wording, or filter by topic / entity in the “Fact table”.')}
          </p>}
        </KbSection>
      ) : !data ? (
        <p className="muted"><span className="spinner" /> {t('Loading…')}</p>
      ) : data.stats.facts === 0 ? (
        <div className="kb-empty">
          <Icon n="bx-brain" />
          <h3>{t('The knowledge base is still empty')}</h3>
          <p className="muted">{t('Import meeting notes, recordings or notes from other apps, or “Save to knowledge base” a finished note — topics, entities and a timeline will grow here, and related memories will surface automatically in the right pane as you write.')}</p>
          <div className="row" style={{ gap: 8 }}>
            <button className="primary" onClick={() => window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'app:import' }))}><Icon n="bx-import" /> {t('Import')}</button>
          </div>
          <ExampleFacts />
        </div>
      ) : (
        <>
          <div className="stat-row">
            <StatTile value={data.stats.facts.toLocaleString()} label={t('facts')} hint={t('Open the fact table')} onClick={() => actions.onOpen('kb:facts')} />
            <StatTile value={data.stats.topics} label={t('topics')} hint={t('Open the topic map')} onClick={() => actions.onOpen('kb:graph')} />
            <StatTile value={data.stats.entities.toLocaleString()} label={t('entities')} hint={t('View all entities')} onClick={() => actions.onOpen('kb:entities')} />
            <StatTile value={data.stats.units.toLocaleString()} label={t('meetings')} hint={t('View recently ingested')} onClick={() => actions.onOpen('kb:recent')} />
            {/* Trim 2% off each end: this number should answer "how long have I been collecting records", not "is there
                an outlier date". What's trimmed is written in the title — **what's trimmed must be visible**. */}
            <StatTile
              value={<span className="stat-span" style={{ fontSize: 'var(--t-lg)' }}
                           title={data.stats.full_start && data.stats.full_start !== data.stats.start_date
                             ? t('Counting the earliest and latest few too, it is {from} → {to} (2% trimmed off each end; those are mostly years mentioned inside sentences)', { from: data.stats.full_start.slice(0, 7), to: (data.stats.full_end ?? '').slice(0, 7) })
                             : undefined}>
                       {data.stats.start_date ? `${data.stats.start_date.slice(0, 7)} → ${data.stats.end_date.slice(0, 7)}` : '—'}
                     </span>}
              label={t('Span (by the dates in facts)')} hint={t('Open the full timeline')} onClick={() => actions.onOpen('kb:timeline')} />
            {}
            {data.quality && data.quality.unusable_rate >= 0.03 && (
              <StatTile
                value={<span title={Object.entries(data.quality.reasons)
                                     .map(([k, v]) => `${k} ${v}`).join(' · ')
                                     + t('; another {n} carry speaker labels. ', { n: data.quality.speaker_labels })
                                     + t('This is a signal about shape, not a claim that they are useless — among them are short, useful sentences like “this phone costs 2999 yuan”.')}>
                         {Math.round(data.quality.unusable_rate * 100)}%
                       </span>}
                label={t('Suspicious shape ({n} too short / questions / filler)', { n: data.quality.unusable.toLocaleString() })}
                hint={t('Check these in the fact table')} onClick={() => actions.onOpen('kb:facts')} />
            )}
          </div>

          <ConflictInbox actions={actions} />

          <KbSection title={t('Last 12 months')} note={t('By the dates in facts; future dates in plans are counted too.')} extra={<a href="#" className="muted" style={{ fontSize: 'var(--t-sm)' }} onClick={(e) => { e.preventDefault(); actions.onOpen('kb:timeline') }}>{t('Full timeline →')}</a>}>
            <MiniBars data={data.months} />
          </KbSection>

          <div className="kb-two-col">
            <KbSection title={t('Topics')} extra={<a href="#" className="muted" style={{ fontSize: 'var(--t-sm)' }} onClick={(e) => { e.preventDefault(); actions.onOpen('kb:topics') }}>{t('All →')}</a>}>
              <div className="chip-wrap">
                {data.top_topics.map((tp) => (
                  <Chip key={tp.code} icon="bx-hash" count={tp.facts} onClick={() => actions.onOpen('kb:topic:' + tp.code)}
                        title={tp.children ? t('{n} subtopics', { n: tp.children }) : undefined}>{tp.code}</Chip>
                ))}
              </div>
            </KbSection>
            <KbSection title={t('Entities')} extra={<a href="#" className="muted" style={{ fontSize: 'var(--t-sm)' }} onClick={(e) => { e.preventDefault(); actions.onOpen('kb:entities') }}>{t('All →')}</a>}>
              <div className="chip-wrap">
                {data.top_entities.filter((e) => !isSpeakerTag(e.name)).map((e) => (
                  <Chip key={e.code} icon={entityIcon(e.name)} count={e.facts} onClick={() => actions.onOpen('kb:entity:' + e.code)}>{e.name}</Chip>
                ))}
              </div>
            </KbSection>
          </div>

          <div className="kb-two-col">
            <KbSection title={t('Recently ingested')} extra={<a href="#" className="muted" style={{ fontSize: 'var(--t-sm)' }} onClick={(e) => { e.preventDefault(); actions.onOpen('kb:recent') }}>{t('All →')}</a>}>
              <div className="stack" style={{ gap: 4 }}>
                {data.recent_units.map((u) => (
                  <a key={u.id} href="#" className="kb-link" onClick={(e) => { e.preventDefault(); actions.onOpen('kb:unit:' + u.id) }} title={u.title || u.id}>
                    <Icon n="bx-conversation" className="muted" /> <span className="muted" style={{ flex: 'none' }}>{u.date}</span>
                    {}
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{u.title || u.id}</span>
                    <span className="muted" style={{ marginInlineStart: 'auto', flex: 'none', whiteSpace: 'nowrap' }}>{t('{n} items', { n: u.facts })}</span>
                  </a>
                ))}
              </div>
            </KbSection>
            <KbSection title={t('Types · speakers')}>
              <div className="chip-wrap">
                {data.kinds.map((k) => <Chip key={k.kind} count={k.facts} onClick={() => actions.onOpen('kb:facts?kind=' + k.kind)}>{k.kind}</Chip>)}
              </div>
              <div className="chip-wrap" style={{ marginTop: 6 }}>
                {data.speakers.map((s) => <Chip key={s.who} icon="bx-user-voice" count={s.facts} onClick={() => actions.onOpen('kb:facts?who=' + s.who)}>{s.who}</Chip>)}
              </div>
            </KbSection>
          </div>
        </>
      )}
    </div>
  )
}
