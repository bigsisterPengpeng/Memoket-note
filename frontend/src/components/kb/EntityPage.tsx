import { useEffect, useState } from 'react'
import { entityIcon } from '../../util/entityIcon'

import { kbEntity, type KbEntityPage } from '../../api'
import { Chip, FactList, KbSection, MiniBars, Pager, type KbActions, MissingPage } from './KbBits'
import LocalGraph from './LocalGraph'
import Icon from '../Icon'
import { t } from '../../i18n'

export default function EntityPage({ code, actions }: { code: string; actions: KbActions }) {
  const [p, setP] = useState<KbEntityPage | null | undefined>(undefined)
  const [offset, setOffset] = useState(0)
  useEffect(() => { setOffset(0) }, [code])
  useEffect(() => {
    let alive = true
    kbEntity(code, 50, offset).then((d) => {
      if (!alive) return
      setP(d)
      // Entity tabs opened from a page / citation only know the code (facebook): rename the tab once the name arrives
      window.dispatchEvent(new CustomEvent('virtual-title', { detail: { id: 'kb:entity:' + code, title: d.name || code } }))
    }).catch(() => { if (alive) setP(null) })
    return () => { alive = false }
  }, [code, offset])
  if (p === undefined) return <p className="muted"><span className="spinner" /> {t('Loading…')}</p>
  if (p === null) return <MissingPage what={t('entity')} id={code} actions={actions} back="kb:entities" backLabel={t('Back to the entity list')} />
  return (
    <div className="kb-page">
      <div className="kb-head">
        <div className="kb-crumbs muted"><a href="#" onClick={(e) => { e.preventDefault(); actions.onOpen('kb:entities') }}>{t('Entities')}</a></div>
        <h2 className="kb-note-title"><Icon n={entityIcon(p.name, (p as { etype?: string }).etype)} className="muted" /> {p.name}</h2>
        <div className="muted" style={{ fontSize: 'var(--t-md)' }}>
          {t('{n} facts', { n: p.facts_total })}{p.type ? ' · ' + p.type : ''}{p.aliases.length ? t(' · Aliases: ') + p.aliases.join(t(', ')) : ''}{p.variants?.length ? t(' · Spellings of the same entity: ') + p.variants.join(t(', ')) : ''}
        </div>
      </div>
      {p.relations.length > 0 && (
        <KbSection title={t('Relations')}>
          <div className="chip-wrap">
            {p.relations.map((r, i) => (
              <Chip key={i} icon="bx-right-arrow-alt" onClick={() => actions.onOpen('kb:entity:' + r.target)}>{r.rel} → {r.target_name}</Chip>
            ))}
          </div>
        </KbSection>
      )}
      {p.months.length > 1 && <KbSection title={t('By month')}><MiniBars data={p.months} /></KbSection>}
      {(p.topics.length > 0 || p.relations.length > 0) && (
        <KbSection title={t('What’s around it')} extra={<span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('Click a node to open its page')}</span>}>
          <LocalGraph actions={actions}
            topics={p.topics.map((tp) => ({ code: tp.code, parents: [], status: 'canonical', aliases: [], fact_count: tp.facts }))}
            entities={[
              { code: p.code, name: p.name, type: p.type, aliases: p.aliases, relations: p.relations.map((r) => [r.rel, r.target] as [string, string]), fact_count: p.facts_total },
              ...p.relations.map((r) => ({ code: r.target, name: r.target_name, type: '', aliases: [], relations: [], fact_count: 0 })),
            ]}
            links={p.topics.map((tp) => ({ topic: tp.code, entity: p.code, weight: tp.facts }))} />
        </KbSection>
      )}
      {p.topics.length > 0 && (
        <KbSection title={t('Related topics')}>
          <div className="chip-wrap">{p.topics.map((tp) => <Chip key={tp.code} icon="bx-hash" count={tp.facts} onClick={() => actions.onOpen('kb:topic:' + tp.code)}>{tp.code}</Chip>)}</div>
        </KbSection>
      )}
      {(p.chains?.length ?? 0) > 0 && (
        // "How these things changed": with 20406 facts laid flat, three contradicting dates can't tell which counts; strung into lines by object at least the order shows
        <KbSection title={t('How these things changed')} extra={<span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('Lines strung together by object · newest at the bottom')}</span>}>
          {p.chains.map((c) => (
            <div key={c.obj} className="card" style={{ padding: '6px 10px' }}>
              <div className="muted" style={{ fontSize: 'var(--t-xs)', marginBottom: 4 }}><Icon n="bx-trending-up" /> {c.obj} · {t('{n} items', { n: c.total })}</div>
              <ol className="chain">
                {c.facts.map((f) => (
                  <li key={f.id} className={f.superseded_by ? 'muted' : ''} onClick={() => actions.onOpen('kb:fact:' + f.id)}>
                    <span className="chain-when">{f.when}</span> {f.text}
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </KbSection>
      )}
      <KbSection title={t('Facts')}>
        <FactList facts={p.facts} actions={actions} />
        <Pager total={p.facts_total} limit={p.limit} offset={p.offset} onPage={setOffset}
               tail={<a href="#" className="kb-link-inline" onClick={(e) => { e.preventDefault(); actions.onOpen('kb:facts?entity=' + p.code) }}>{t('Filter by type / speaker / topic in the fact table')}</a>} />
      </KbSection>
    </div>
  )
}
