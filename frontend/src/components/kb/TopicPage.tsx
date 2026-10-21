import { useEffect, useState } from 'react'
import { entityIcon } from '../../util/entityIcon'
import { isSpeakerTag } from '../../util/kbNoise'

import { kbTopic, type KbTopicPage } from '../../api'
import { Chip, FactList, KbSection, MiniBars, Pager, type KbActions, MissingPage } from './KbBits'
import LocalGraph from './LocalGraph'
import Icon from '../Icon'
import { t } from '../../i18n'

export default function TopicPage({ code, actions }: { code: string; actions: KbActions }) {
  const [p, setP] = useState<KbTopicPage | null | undefined>(undefined)
  const [offset, setOffset] = useState(0)
  useEffect(() => { setOffset(0) }, [code])
  useEffect(() => {
    let alive = true
    kbTopic(code, 50, offset).then((d) => { if (alive) setP(d) }).catch(() => { if (alive) setP(null) })
    return () => { alive = false }
  }, [code, offset])
  if (p === undefined) return <p className="muted"><span className="spinner" /> {t('Loading…')}</p>
  if (p === null) return <MissingPage what={t('topic')} id={code} actions={actions} back="kb:topics" backLabel={t('Back to the topic list')} />
  return (
    <div className="kb-page">
      <div className="kb-head">
        <div className="kb-crumbs muted">
          <a href="#" onClick={(e) => { e.preventDefault(); actions.onOpen('kb:topics') }}>{t('Topics')}</a>
          {p.parents.map((pp) => <span key={pp}> / <a href="#" onClick={(e) => { e.preventDefault(); actions.onOpen('kb:topic:' + pp) }}>{pp}</a></span>)}
        </div>
        <h2 className="kb-note-title"><Icon n="bx-hash" className="muted" /> {p.code}</h2>
        <div className="muted" style={{ fontSize: 'var(--t-md)' }}>
          {t('{n} facts', { n: p.facts_total })}{p.aliases.length ? t(' · Aliases: ') + p.aliases.join(t(', ')) : ''}{p.status !== 'canonical' ? ' · ' + p.status : ''}
        </div>
      </div>
      {p.months.length > 1 && <KbSection title={t('By month')}><MiniBars data={p.months} /></KbSection>}
      {(p.children.length > 0 || p.entities.length > 0) && (
        <KbSection title={t('What’s around it')}
                   extra={<span className="muted" style={{ fontSize: 'var(--t-sm)' }}>
                     {p.children.length > 12 ? t('Only the strongest 12 subtopics are drawn ({n} in total) · ', { n: p.children.length }) : ''}{t('Click a node to open its page')}</span>}>
          <LocalGraph actions={actions}
            topics={[
              { code: p.code, parents: p.parents, status: 'canonical', aliases: p.aliases, fact_count: p.facts_total },
              ...p.parents.map((pp) => ({ code: pp, parents: [], status: 'canonical', aliases: [], fact_count: 0 })),

              ...p.children.slice(0, 12).map((c) => ({ code: c.code, parents: [p.code], status: 'canonical', aliases: [], fact_count: c.facts })),
            ]}
            entities={p.entities.filter((e) => !isSpeakerTag(e.name)).slice(0, 8).map((e) => ({ code: e.code, name: e.name, type: '', aliases: [], relations: [], fact_count: e.facts }))}
            links={p.entities.filter((e) => !isSpeakerTag(e.name)).slice(0, 8).map((e) => ({ topic: p.code, entity: e.code, weight: e.facts }))} />
        </KbSection>
      )}
      {p.children.length > 0 && (
        <KbSection title={t('Subtopics')}>
          <div className="chip-wrap">{p.children.map((c) => <Chip key={c.code} icon="bx-hash" count={c.facts} onClick={() => actions.onOpen('kb:topic:' + c.code)}>{c.code}</Chip>)}</div>
        </KbSection>
      )}
      {p.entities.length > 0 && (
        <KbSection title={t('Entities that often appear together')}>
          <div className="chip-wrap">{p.entities.filter((e) => !isSpeakerTag(e.name)).map((e) => <Chip key={e.code} icon={entityIcon(e.name)} count={e.facts} onClick={() => actions.onOpen('kb:entity:' + e.code)}>{e.name}</Chip>)}</div>
        </KbSection>
      )}
      <KbSection title={t('Facts')} extra={<span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('Incl. subtopics · newest first')}</span>}>
        <FactList facts={p.facts} actions={actions} />
        <Pager total={p.facts_total} limit={p.limit} offset={p.offset} onPage={setOffset}
               tail={<a href="#" className="kb-link-inline" onClick={(e) => { e.preventDefault(); actions.onOpen('kb:facts?topic=' + code) }}>{t('Filter by type / speaker / entity in the fact table')}</a>} />
      </KbSection>
    </div>
  )
}
