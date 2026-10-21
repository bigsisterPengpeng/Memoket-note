/**
 * Shared small pieces for knowledge-base pages. Charts follow the dataviz rules: a single-hue sequence (one accent color) for
 * quantity, thin marks, rounded ends, values on hover, text in the text color.
 */
import { isSpeakerTag } from '../../util/kbNoise'
import { entityIcon } from '../../util/entityIcon'
import { clickable } from '../../util/clickable'
import { useState, type ReactNode } from 'react'

import type { FactDetail, KbMonth } from '../../api'
import Icon from '../Icon'
import { t } from '../../i18n'


export function MissingPage({ what, id, actions, back = 'kb', backLabel = t('Back to knowledge base overview') }: {
  what: string; id: string; actions: KbActions; back?: string; backLabel?: string
}) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      <h3 style={{ margin: 0 }}>{t('No such {what}', { what })}</h3>
      <p className="muted" style={{ margin: 0 }}><code>{id}</code>{t(' does not exist in the knowledge base — maybe an old tab, a rename, or the knowledge base was rebuilt.')}</p>
      <div><button onClick={() => actions.onOpen(back)}><Icon n="bx-left-arrow-alt" /> {backLabel}</button></div>
    </div>
  )
}

export type KbActions = {
  onOpen: (id: string) => void                 // virtual node kb:…
  onOpenNote: (noteId: string) => void
  /** Send `original text [id]` into the note being written; null if none is being written (the page degrades to "Copy citation") */
  onCite: ((f: { id: string; text: string }) => void) | null
}

export function StatTile({ value, label, hint, onClick }: {
  value: ReactNode; label: string; hint?: string; onClick?: () => void
}) {
  const body = <>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {onClick && <Icon n="bx-right-arrow-alt" className="stat-open" />}
    </>
  return onClick
    ? <button type="button" className="stat-tile interactive" title={hint} onClick={onClick}>{body}</button>
    : <div className="stat-tile" title={hint}>{body}</div>
}

/** Single-hue bar chart: month × count. Value on hover; months labeled at both ends.
 *  div instead of svg: an svg stretched to the container width turns three bars into three big bricks; div gives each bar
 *  a max width (28px), so with few of them they're just a few thin bars standing at the left. */
export function MiniBars({ data, height = 64, label = t('facts') }: { data: KbMonth[]; height?: number; label?: string }) {
  if (data.length === 0) return <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>{t('No monthly data yet.')}</p>
  const max = Math.max(1, ...data.map((d) => d.facts))
  return (
    <div className="mini-bars" style={{ maxWidth: Math.max(data.length * 31, 132) }}>{/* even with just one or two months there must be room for two "2026-03" labels, or the labels wrap onto two lines */}
      <div className="mini-bars-row" style={{ height }}>
        {data.map((d) => (
          <div key={d.month} className="mini-bar" title={`${d.month} · ${d.facts} ${label}`}
               style={{ height: d.facts ? `${Math.max(3, (d.facts / max) * 100)}%` : 0, opacity: d.facts ? undefined : 0 }} />
        ))}
      </div>
      <div className="mini-bars-axis muted">
        <span>{data[0].month}</span>
        {data.length > 1 && <span>{data[data.length - 1].month}</span>}
      </div>
    </div>
  )
}

export function Chip({ icon, children, count, onClick, title }: {
  icon?: string; children: ReactNode; count?: number; onClick?: () => void; title?: string
}) {
  return (
    <button className="chip" onClick={onClick} title={title} disabled={!onClick}>
      {icon && <Icon n={icon} />}
      <span>{children}</span>
      {count !== undefined && <span className="chip-count">{count}</span>}
    </button>
  )
}


export function KbSection({ title, note, extra, children }: { title: string; note?: string; extra?: ReactNode; children: ReactNode }) {
  return (
    <section className="kb-section">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h3 className="kb-section-title">{title}</h3>
        {extra}
      </div>
      {note && <p className="muted" style={{ margin: '-6px 0 0', fontSize: 'var(--t-sm)' }}>{note}</p>}
      {children}
    </section>
  )
}

/** One fact: date · speaker · type · text · open / cite. */
export function FactRow({ f, actions, showTopics = false }: { f: FactDetail; actions: KbActions; showTopics?: boolean }) {
  const [copied, setCopied] = useState(false)
  const cite = () => {
    if (actions.onCite) { actions.onCite(f); return }
    void navigator.clipboard.writeText(`${f.text} [${f.id}]`).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200) })
  }
  return (
    <div className="fact-row">
      <div className="fact-meta muted">
        <span>{f.when || '—'}</span>
        {f.who && <span>· {f.who}</span>}
        {f.kind && <span className="fact-kind">{f.kind}</span>}
      </div>
      <div className={'fact-text' + (f.superseded_by ? ' superseded' : '')} {...clickable(() => actions.onOpen('kb:fact:' + f.id))}>{f.text}</div>
      {f.superseded_by && (
        <div className="fact-tags">
          <Chip icon={f.merged ? 'bx-git-merge' : 'bx-right-arrow-alt'} onClick={() => actions.onOpen('kb:fact:' + f.superseded_by)} title={f.merged ? t('This one was merged into another; open the merged one') : t('This one is outdated; open the one that replaced it')}>{f.merged ? t('Merged') : t('Superseded')}</Chip>
        </div>
      )}
      {f.note_id && (
        // Ingested from a note: backlink to that note (the knowledge base → note direction used to be broken)
        <div className="fact-tags">
          <Chip icon="bx-note" onClick={() => actions.onOpenNote(f.note_id!)} title={t('Open the note it was ingested from')}>{f.manual ? t('Added by hand in a note') : t('From a note')}</Chip>
        </div>
      )}
      {showTopics && (f.topics.length > 0 || f.entities.length > 0) && (
        <div className="fact-tags">
          {f.topics.map((tp) => <Chip key={tp} icon="bx-hash" onClick={() => actions.onOpen('kb:topic:' + tp)}>{tp}</Chip>)}
          {}
          {f.entities.map((e, i) => [e, f.entity_names?.[i] ?? e] as const).filter(([, n]) => !isSpeakerTag(n)).map(([e, n]) => <Chip key={e} icon={entityIcon(n)} onClick={() => actions.onOpen('kb:entity:' + e)}>{n}</Chip>)}
        </div>
      )}
      <div className="fact-actions">
        <button className="icon-btn" title={t('Open this fact')} onClick={() => actions.onOpen('kb:fact:' + f.id)}><Icon n="bx-link-external" /></button>
        <button className="icon-btn" title={actions.onCite ? t('Cite into the note being written') : t('Copy citation (original text [id])')} onClick={cite}>
          <Icon n={(copied ? 'bx-check' : actions.onCite ? 'bx-link' : 'bx-copy')} />
        </button>
      </div>
    </div>
  )
}

export function FactList({ facts, actions, showTopics }: { facts: FactDetail[]; actions: KbActions; showTopics?: boolean }) {
  if (facts.length === 0) return <p className="muted" style={{ fontSize: 'var(--t-md)', margin: 0 }}>{t('No facts.')}</p>
  // Group by month: see at a glance "which month talked about this"
  const groups: { month: string; items: FactDetail[] }[] = []
  for (const f of facts) {
    const m = (f.when || t('Unknown')).slice(0, 7)
    const g = groups[groups.length - 1]
    if (g && g.month === m) g.items.push(f); else groups.push({ month: m, items: [f] })
  }
  return (
    <div className="fact-list">
      {groups.map((g) => (
        <div key={g.month}>
          <div className="fact-month muted">{g.month}</div>
          {g.items.map((f) => <FactRow key={f.id} f={f} actions={actions} showTopics={showTopics} />)}
        </div>
      ))}
    </div>
  )
}


// a function, not a module constant: t() must run at display time
const exampleFacts = (): FactDetail[] => [
  { id: 'demo-1', text: t('Measured prototype battery life is 11 hours, 2 hours more than the last version.'), when: '2026-03-04',
    kind: t('conclusion'), who: t('Engineer Li'), conf: 'high', topics: [t('hardware')], entities: [], unit: 'demo' },
  { id: 'demo-2', text: t('This version is priced at 199 dollars, launching first in North America.'), when: '2026-03-11',
    kind: t('decision'), who: '', conf: 'high', topics: [t('pricing')], entities: [], unit: 'demo',
    note_id: 'demo-note' },
]

const NO_ACTIONS: KbActions = { onOpen: () => {}, onOpenNote: () => {}, onCite: null }

export function ExampleFacts() {
  return (
    <div className="kb-example">
      <div className="muted" style={{ fontSize: 'var(--t-sm)', marginBottom: 4 }}>
        {t('Example — after an import, every sentence becomes an entry like this: with a date, speaker and type, openable, and citable into the body in one click.')}
      </div>
      <div className="fact-list" inert>
        <div className="fact-month muted">2026-03</div>
        {exampleFacts().map((f) => <FactRow key={f.id} f={f} actions={NO_ACTIONS} showTopics />)}
      </div>
    </div>
  )
}

export function Pager({ total, limit, offset, onPage, tail }: { total: number; limit: number; offset: number; onPage: (o: number) => void; tail?: ReactNode }) {
  if (total <= limit) return null
  const page = Math.floor(offset / limit) + 1, pages = Math.ceil(total / limit)
  return (
    <div className="row" style={{ gap: 6, alignItems: 'center', marginTop: 8 }}>
      <button className="icon-btn" title={t('Previous page')} aria-label={t('Previous page')} disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - limit))}><Icon n="bx-chevron-left" /></button>
      <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('{page} / {pages} · {total} in total', { page, pages, total })}</span>
      <button className="icon-btn" title={t('Next page')} aria-label={t('Next page')} disabled={offset + limit >= total} onClick={() => onPage(offset + limit)}><Icon n="bx-chevron-right" /></button>
      {/* Nobody pages through 121 pages one by one: next to the pager offer a way out, "filter in the fact table" (passed in by topic / entity pages) */}
      {tail && <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>· {tail}</span>}
    </div>
  )
}
