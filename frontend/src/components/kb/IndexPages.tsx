/** The three category pages: topics / entities / recently ingested. The data is just those tree rows — no extra request
 *  (in libraries with many entities the tree carries none, so the entity page fetches once itself). */
import { useEffect, useMemo, useState } from 'react'
import { entityIcon } from '../../util/entityIcon'
import { entityMergeCandidates } from '../../api'

import { kbTreeChildren, type TreeRow } from '../../api'
import { Chip, KbSection, type KbActions } from './KbBits'
import { isSpeakerTag } from '../../util/kbNoise'
import Icon from '../Icon'
import { t } from '../../i18n'

export function TopicsIndex({ rows, actions }: { rows: TreeRow[]; actions: KbActions }) {
  const roots = rows.filter((r) => r.parent_note_id === 'kb:topics').sort((a, b) => b.fact_count - a.fact_count)
  const kids = (code: string) => rows.filter((r) => r.parent_note_id === 'kb:topic:' + code).sort((a, b) => b.fact_count - a.fact_count)
  return (
    <div className="kb-page">
      <div className="kb-head">
        <h2 className="kb-note-title"><Icon n="bx-hash" className="muted" /> {t('Topics')}</h2>
        <div className="muted" style={{ fontSize: 'var(--t-md)' }}>{roots.length ? t('{n} top-level topics. Counts include subtopics.', { n: roots.length }) : t('No topics yet.')}</div>
      </div>
      {roots.length === 0 && (
        <p className="muted" style={{ fontSize: 'var(--t-md)' }}>{t('After importing meeting notes or saving notes to the knowledge base, extracted facts are filed under topics automatically, and they will grow here.')}</p>
      )}
      <div className="topic-grid">
        {roots.map((tp) => (
          <div key={tp.id} className="topic-card">
            <a href="#" className="topic-card-title" onClick={(e) => { e.preventDefault(); actions.onOpen(tp.note_id) }}>
              <Icon n="bx-hash" className="muted" /> {tp.title}<span className="muted" style={{ marginInlineStart: 'auto', fontSize: 'var(--t-sm)' }}>{tp.fact_count}</span>
            </a>
            <div className="chip-wrap">
              {kids(tp.title).slice(0, 8).map((k) => <Chip key={k.id} count={k.fact_count} onClick={() => actions.onOpen(k.note_id)}>{k.title}</Chip>)}
              {kids(tp.title).length > 8 && (
                <a href="#" className="muted" style={{ fontSize: 'var(--t-sm)' }} title={t('Open this topic page to see all subtopics')}
                   onClick={(e) => { e.preventDefault(); actions.onOpen(tp.note_id) }}>{t('…{n} more →', { n: kids(tp.title).length - 8 })}</a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ASR speaker labels (Speaker A / speaker_c…) get extracted as "entities", and have the most facts —
// the top twenty on the entity page were all them. Hidden by default, with a toggle to show them (util/kbNoise.ts).

/** Display names of entity-type nodes (consistent with the backend's virtual_tree.ETYPE_LABELS); data, translated at display */
const ETYPE_LABELS: Record<string, string> = { person: 'Person', org: 'Organization', product: 'Product', place: 'Place', event: 'Event', project: 'Project', other: 'Other' }   // i18n-ignore


export function EntitiesIndex({ rows, actions, node = 'kb:entities' }: { rows: TreeRow[]; actions: KbActions; node?: string }) {
  const [q, setQ] = useState('')
  const [showSpeakers, setShowSpeakers] = useState(false)
  const etype = node.startsWith('kb:etype:') ? node.slice(9) : ''

  useEffect(() => {
    if (!etype) return

    const timer = setTimeout(() => window.dispatchEvent(new CustomEvent('virtual-title', { detail: { id: node, title: t('Entities · {type}', { type: ETYPE_LABELS[etype] ? t(ETYPE_LABELS[etype]) : etype }) } })), 0)
    return () => clearTimeout(timer)
  }, [etype, node])
  const fromTree = useMemo(() => rows.filter((r) => r.note_id.startsWith('kb:entity:') && (!etype || r.parent_note_id === node)), [rows, etype, node])
  // Libraries with over 200 entities don't carry them in the tree (358KB per tree refresh is too heavy): this page fetches once itself
  const [fetched, setFetched] = useState<TreeRow[] | null>(null)
  useEffect(() => {
    if (fromTree.length > 0) { setFetched(null); return }
    let alive = true
    kbTreeChildren(node).then((r) => { if (alive) setFetched(r) }).catch(() => { if (alive) setFetched([]) })
    return () => { alive = false }
  }, [fromTree.length, node])
  const all = useMemo(() => [...(fromTree.length ? fromTree : (fetched ?? []))].sort((a, b) => b.fact_count - a.fact_count), [fromTree, fetched])
  const speakers = useMemo(() => all.filter((r) => isSpeakerTag(r.title)).length, [all])
  const base = showSpeakers ? all : all.filter((r) => !isSpeakerTag(r.title))
  const list = q ? base.filter((r) => (r.title + ' ' + r.preview).toLowerCase().includes(q.toLowerCase())) : base.slice(0, 200)
  return (
    <div className="kb-page">
      <div className="kb-head">
        <h2 className="kb-note-title"><Icon n="bx-group" className="muted" /> {etype ? t('Entities · {type}', { type: ETYPE_LABELS[etype] ? t(ETYPE_LABELS[etype]) : etype }) : t('Entities')}</h2>
        <div className="muted" style={{ fontSize: 'var(--t-md)' }}>{!etype && all.length === 0 ? t('No entities yet.') : t('{n} in total, sorted by fact count{more}.', { n: all.length, more: !q && all.length > 200 ? t('; showing the first 200 — search to find the rest') : '' })}{etype && fetched !== null && all.length === 0 ? t('Entities in this library aren\'t grouped by type — see all under “Entities”.') : ''}</div>
      </div>
      {!etype && all.length === 0 && (
        <p className="muted" style={{ fontSize: 'var(--t-md)' }}>{t('After importing meeting notes or saving notes to the knowledge base, the people, companies and products mentioned in facts are collected here automatically.')}</p>
      )}
      {/* The entry to the merge inbox. **It's on the entity page** because this is where the problem is seen:
          the list is sorted by fact count, and those numbers are now partial truths (MemoCat really 189, shown 93). */}
      {!etype && all.length > 0 && <MergeEntry onOpen={() => actions.onOpen('kb:merges')} />}
      {all.length > 0 && <div className="kb-search">
        <Icon n="bx-search" />
        <input aria-label={t('Search entity names or aliases')} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('Search entity names or aliases…')} />
      </div>}
      {speakers > 0 && (
        <label className="row muted" style={{ gap: 6, fontSize: 'var(--t-sm)', alignItems: 'center', margin: '-2px 0 8px' }}>
          <input type="checkbox" checked={showSpeakers} onChange={(e) => setShowSpeakers(e.target.checked)} />
          {t('Show {n} speaker labels (ones like Speaker A are role names from recording transcripts, not real entities)', { n: speakers })}
        </label>
      )}
      <div className="chip-wrap">
        {list.map((e) => <Chip key={e.id} icon={entityIcon(e.title)} count={e.fact_count} onClick={() => actions.onOpen(e.note_id)} title={e.preview || undefined}>{e.title}</Chip>)}
      </div>
    </div>
  )
}

/** The "N pairs may be duplicates" line. It fetches its own number — **an entry without a number gets no clicks**. */
function MergeEntry({ onOpen }: { onOpen: () => void }) {
  const [n, setN] = useState<number | null>(null)
  // One item is enough — what's wanted is `total` (total pending), not how many are on this page
  useEffect(() => { entityMergeCandidates(1).then((d) => setN(d.total)).catch(() => setN(0)) }, [])
  if (!n) return null
  return (
    <p className="muted" style={{ fontSize: 'var(--t-md)', margin: '-2px 0 8px' }}>
      {t('There are ')}<b>{t('{n} pairs', { n })}</b>{t(' that may be the same thing (like `Anker` and its transliterations) — ')}
      {t('only after merging are the fact counts in this column true. ')}<a className="link" onClick={onOpen}>{t('Take a look →')}</a>
    </p>
  )
}

export function RecentIndex({ rows, actions }: { rows: TreeRow[]; actions: KbActions }) {
  const units = rows.filter((r) => r.parent_note_id === 'kb:recent').sort((a, b) => a.position - b.position)
  return (
    <div className="kb-page">
      <div className="kb-head">
        <h2 className="kb-note-title"><Icon n="bx-time-five" className="muted" /> {t('Recently ingested')}</h2>
        <div className="muted" style={{ fontSize: 'var(--t-md)' }}>{units.length ? t('The last {n} meetings. Open one to see the facts extracted from it.', { n: units.length }) : t('Nothing ingested yet.')}</div>
      </div>
      {units.length === 0 && (
        <p className="muted" style={{ fontSize: 'var(--t-md)' }}>{t('Import a meeting recording, a batch of notes, or “Save to knowledge base” a finished note — every material will be listed here afterwards.')}</p>
      )}
      {units.length > 0 && <KbSection title={t('Meetings')}>
        <div className="stack" style={{ gap: 4 }}>
          {units.map((u) => (
            <a key={u.id} href="#" className="kb-link" onClick={(e) => { e.preventDefault(); actions.onOpen(u.note_id) }}>
              <Icon n="bx-conversation" className="muted" /> {u.title}
              <span className="muted" style={{ marginInlineStart: 'auto', whiteSpace: 'nowrap', flexShrink: 0 }}>{t('{n} items', { n: u.fact_count })}</span>
            </a>
          ))}
        </div>
      </KbSection>}
    </div>
  )
}
