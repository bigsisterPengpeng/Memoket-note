import { isSpeakerTag } from '../../util/kbNoise'
import { entityIcon } from '../../util/entityIcon'
import { useEffect, useState } from 'react'

import { kbUnit, type KbUnitPage } from '../../api'
import { Chip, FactList, KbSection, Pager, type KbActions, MissingPage } from './KbBits'
import Icon from '../Icon'
import { t } from '../../i18n'

/** One meeting (a KITE unit): the facts extracted from this meeting. */
export default function UnitPage({ id, actions }: { id: string; actions: KbActions }) {
  const [p, setP] = useState<KbUnitPage | null | undefined>(undefined)
  const [offset, setOffset] = useState(0)
  useEffect(() => { setOffset(0) }, [id])
  useEffect(() => {
    let alive = true
    kbUnit(id, 50, offset).then((d) => {
      if (!alive) return
      setP(d)

      window.dispatchEvent(new CustomEvent('virtual-title', { detail: { id: 'kb:unit:' + id, title: d.title || t('Meeting notes') } }))
    }).catch(() => { if (alive) setP(null) })
    return () => { alive = false }
  }, [id, offset])
  if (p === undefined) return <p className="muted"><span className="spinner" /> {t('Loading…')}</p>
  if (p === null) return <MissingPage what={t('meeting')} id={id} actions={actions} back="kb:recent" backLabel={t('Back to recently ingested')} />
  return (
    <div className="kb-page">
      <div className="kb-head">
        <div className="kb-crumbs muted"><a href="#" onClick={(e) => { e.preventDefault(); actions.onOpen('kb:recent') }}>{t('Recently ingested')}</a></div>
        <h2 className="kb-note-title"><Icon n="bx-conversation" className="muted" /> {p.title || p.id}</h2>
        <div className="muted" style={{ fontSize: 'var(--t-md)' }}>{p.date} · {t('{n} facts', { n: p.facts_total })}{p.speakers.length ? ' · ' + p.speakers.join(t(', ')) : ''}</div>
        {}
        {(p.part_total ?? 1) > 1 && p.parts && (
          <div className="row" style={{ gap: 6, fontSize: 'var(--t-sm)', marginTop: 6, alignItems: 'center' }}>
            <span className="muted">{t('Part {i}/{n}', { i: p.part_index ?? '', n: p.part_total ?? '' })}</span>
            {p.parts.map((x) => (
              <button key={x.id} className={'chip' + (x.id === p.id ? ' active' : '')} disabled={x.id === p.id}
                      onClick={() => actions.onOpen('kb:unit:' + x.id)}>{x.k}</button>
            ))}
          </div>
        )}
      </div>
      {(p.topics.length > 0 || p.entities.length > 0) && (
        <KbSection title={t('What this meeting is about')}>
          <div className="chip-wrap">
            {p.topics.map((tp) => <Chip key={tp.code} icon="bx-hash" count={tp.facts} onClick={() => actions.onOpen('kb:topic:' + tp.code)}>{tp.code}</Chip>)}
            {p.entities.filter((e) => !isSpeakerTag(e.name)).map((e) => <Chip key={e.code} icon={entityIcon(e.name)} count={e.facts} onClick={() => actions.onOpen('kb:entity:' + e.code)}>{e.name}</Chip>)}
          </div>
        </KbSection>
      )}
      {p.facts_total === 0 && p.lines && p.lines.length > 0 ? (
        <KbSection title={t('No facts extracted from this part · {n} lines of original text', { n: p.lines.length })}>
          <div className="stack" style={{ gap: 6 }}>
            {p.lines.map((l, i) => (
              <p key={i} className="muted" style={{ margin: 0, fontSize: 'var(--t-md)' }}>{l.who ? <b style={{ marginInlineEnd: 6 }}>{l.who}</b> : null}{l.text}</p>
            ))}
          </div>
        </KbSection>
      ) : (
        <KbSection title={t('Facts')}>
          <FactList facts={p.facts} actions={actions} showTopics />
          <Pager total={p.facts_total} limit={p.limit} offset={p.offset} onPage={setOffset} />
        </KbSection>
      )}
    </div>
  )
}
