/**
 * Knowledge-base workspace. Facts, topics and entities can still fill the middle pane, but they're pages within the same
 * workspace: the top navigation switches, back returns to the previous level, and only one knowledge-base tab is kept outside.
 */
import { isSpeakerTag } from '../util/kbNoise'
import { t } from '../i18n'
import EntityMerges from './kb/EntityMerges'
import { useEffect, useState } from 'react'

import { displayTitle } from '../util/displayTitle'

import DigestPanel from './DigestPanel'
import MemoryBrowser from './MemoryBrowser'
import EntityPage from './kb/EntityPage'
import FactsTable from './kb/FactsTable'
import { EntitiesIndex, RecentIndex, TopicsIndex } from './kb/IndexPages'
import KbDashboard from './kb/KbDashboard'
import TimelinePage from './kb/TimelinePage'
import TopicPage from './kb/TopicPage'
import UnitPage from './kb/UnitPage'
import type { KbActions } from './kb/KbBits'

import {
  factPeek, factSources, kbTreeChildren, notesCiting, recall,
  isFactId, type CitingNote, type Fact, type FactPeek, type SourceLine, type TreeRow,
} from '../api'
import { fmtDate } from '../util/time'
import Icon from './Icon'

type Props = {
  id: string
  /** The whole tree (real notes + virtual nodes), used to look up titles and subcategories. */
  rows: TreeRow[]
  onOpen: (id: string) => void
  onOpenNote: (noteId: string) => void
  /** Send `original text [fact-id]` into the note currently being written; null if none is being written. */
  onCite: ((factId: string, text: string) => void) | null
  /** The main pane uses the global browsing history; when the split doesn't pass it, fall back to the knowledge-base overview. */
  onBack?: () => void
}

// Labels are data (module-level constants), translated at display via `t(item.label)`
const KB_NAV = [
  { id: 'kb', label: 'Overview', icon: 'bx-home' },
  { id: 'kb:facts', label: 'Facts table', icon: 'bx-table' },
  { id: 'kb:graph', label: 'Topic map', icon: 'bx-network-chart' },
  { id: 'kb:digest', label: 'Periodic review', icon: 'bx-history' },
] as const

function navActive(current: string, item: typeof KB_NAV[number]['id']): boolean {
  if (item === 'kb') return current === 'kb'
  if (item === 'kb:facts') return current === 'kb:facts' || current.startsWith('kb:facts?') || current.startsWith('kb:fact:')
  return current === item
}

export default function KbNoteView(props: Props) {
  const { id, rows } = props
  const actions: KbActions = {
    onOpen: props.onOpen, onOpenNote: props.onOpenNote,
    onCite: props.onCite ? (f) => props.onCite!(f.id, f.text) : null,
  }
  let page: React.ReactNode
  if (isFactId(id)) page = <FactNote {...props} />
  else if (id === 'kb') page = <KbDashboard actions={actions} />
  else if (id === 'kb:topics') page = <TopicsIndex rows={rows} actions={actions} />
  else if (id === 'kb:entities') page = <EntitiesIndex rows={rows} actions={actions} />
  else if (id === 'kb:merges') page = <ToolNote title={t('Possible duplicates')} icon="bx-merge"><EntityMerges /></ToolNote>
  else if (id.startsWith('kb:etype:')) page = <EntitiesIndex rows={rows} actions={actions} node={id} />
  else if (id === 'kb:recent') page = <RecentIndex rows={rows} actions={actions} />
  else if (id === 'kb:timeline') page = <TimelinePage actions={actions} />
  else if (id === 'kb:facts' || id.startsWith('kb:facts?')) page = <FactsTable query={id.split('?')[1] ?? ''} actions={actions} />
  else if (id.startsWith('kb:topic:')) page = <TopicPage code={id.slice('kb:topic:'.length)} actions={actions} />
  else if (id.startsWith('kb:entity:')) page = <EntityPage code={id.slice('kb:entity:'.length)} actions={actions} />
  else if (id.startsWith('kb:unit:')) page = <UnitPage id={id.slice('kb:unit:'.length)} actions={actions} />
  // Multi-part material (the "(n parts)" row on the tree): open its first part; the page top has part navigation
  else if (id.startsWith('kb:material:')) page = <UnitPage id={id.slice('kb:material:'.length)} actions={actions} />
  else if (id === 'kb:graph') page = <ToolNote title={t('Topic map')} icon="bx-network-chart"><MemoryBrowser /></ToolNote>
  else if (id === 'kb:digest') page = <ToolNote title={t('Periodic review')} icon="bx-history"><DigestPanel /></ToolNote>
  else page = <CollectionNote {...props} />

  return (
    <div className="kb-workspace">
      <header className="kb-workspace-head">
        <div className="kb-workspace-brand">
          {id !== 'kb' && (
            <button type="button" className="kb-workspace-back" title={t('Go back')}
                    aria-label={t('Go back')} onClick={props.onBack ?? (() => props.onOpen('kb'))}>
              <Icon n="bx-left-arrow-alt" /> <span>{t('Back')}</span>
            </button>
          )}
          <Icon n="bx-data" />
          <strong>{t('Knowledge base')}</strong>
        </div>
        <nav className="kb-workspace-nav" aria-label={t('Knowledge base views')}>
          {KB_NAV.map((item) => (
            <button type="button" key={item.id}
                    className={navActive(id, item.id) ? 'active' : ''}
                    aria-current={navActive(id, item.id) ? 'page' : undefined}
                    onClick={() => props.onOpen(item.id)}>
              <Icon n={item.icon} /> <span>{t(item.label)}</span>
            </button>
          ))}
        </nav>
      </header>
      <div className="kb-workspace-content">{page}</div>
    </div>
  )
}

function ToolNote({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <div className="kb-note" style={{ maxWidth: 'none' }}>
      <h2 className="kb-note-title"><Icon n={icon} className="muted" /> {title}</h2>
      {children}
    </div>
  )
}

// ----------------------------------------------------------------- a fact

function FactNote({ id, onOpen, onOpenNote, onCite }: Props) {
  const factId = id.slice('kb:fact:'.length)
  const [fact, setFact] = useState<FactPeek | null | undefined>(undefined)
  const [sources, setSources] = useState<SourceLine[]>([])
  const [citing, setCiting] = useState<CitingNote[]>([])
  const [related, setRelated] = useState<Fact[]>([])
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let alive = true
    setFact(undefined); setSources([]); setCiting([]); setRelated([])
    void factPeek(factId).then((f) => {
      if (!alive) return
      setFact(f)
      if (!f) return

      window.dispatchEvent(new CustomEvent('virtual-title', { detail: { id: 'kb:fact:' + factId, title: (f.text || '').slice(0, 18) || t('Fact') } }))
      // Neighbors: recall with this fact's original text, minus itself. Facts from the same meeting / topic
      // naturally rank first — the cheapest and most accurate way to get "related facts".
      void recall(f.text, 7).then((r) => {
        if (alive) setRelated(r.facts.filter((x) => x.id !== factId).slice(0, 6))
      }).catch(() => {})
    })
    void factSources(factId).then((s) => { if (alive) setSources(s) }).catch(() => {})
    void notesCiting(factId).then((n) => { if (alive) setCiting(n) }).catch(() => {})
    return () => { alive = false }
  }, [factId])

  function copyCite() {
    void navigator.clipboard.writeText(`[${factId}]`).then(() => {
      setCopied(true); setTimeout(() => setCopied(false), 1200)
    })
  }

  if (fact === undefined) return <p className="muted">…</p>
  if (fact === null) {
    return (
      <div className="kb-note">
        <h2 className="kb-note-title" style={{ color: 'var(--del)' }}>{t('Fact not found')}</h2>
        <p className="muted">{t('{id} does not exist in the knowledge base — the citation may be wrong, or the knowledge base was rebuilt.', { id: factId })}</p>
        {}
        <p><button className="chip chip-action" onClick={() => window.dispatchEvent(new CustomEvent('virtual-gone', { detail: 'kb:fact:' + factId }))}><Icon n="bx-x" /> {t('Close this tab')}</button></p>
      </div>
    )
  }

  return (
    <div className="kb-note">
      <div className="muted kb-note-meta">
        <span>◆ {fact.when || t('unknown time')}</span>
        {fact.kind && <span>· {fact.kind}</span>}
        <code className="kb-note-id">[{factId}]</code>
        <span style={{ marginInlineStart: 'auto' }} className="row">
          {onCite && <button onClick={() => onCite(factId, fact.text)} title={t('Insert a citation into the note being written')}><Icon n="bx-link" /> {t('Cite in note')}</button>}
          <button onClick={copyCite}><Icon n={(copied ? 'bx-check' : 'bx-copy')} /> {copied ? t('Copied') : t('Copy citation')}</button>
        </span>
      </div>
      <h2 className="kb-note-title">{fact.text}</h2>
      {(fact.topics.length > 0 || fact.entities.length > 0) && (
        <div className="chip-wrap">
          {fact.topics.map((t) => <button key={t} className="chip" onClick={() => onOpen('kb:topic:' + t)}><Icon n="bx-hash" />{t}</button>)}
          {fact.entities.map((e, i) => [e, fact.entity_names?.[i] ?? e] as const).filter(([, n]) => !isSpeakerTag(n)).map(([e, n]) => <button key={e} className="chip" onClick={() => onOpen('kb:entity:' + e)}><Icon n="bx-user" />{n}</button>)}
        </div>
      )}

      <Section title={t('Original words')} empty={t('No original words kept for this fact')}>
        {sources.map((s) => <Quote key={s.id} line={s} />)}
      </Section>

      {/* The key to fusion: which notes this evidence lives in. Changing or deleting it affects whom. */}
      <Section title={t('Cited by these notes')} empty={t('No note cites this yet. While writing it appears under Related memory; click to insert.')}>
        {citing.map((n) => (
          <a key={n.id} href="#" className="kb-link"
             onClick={(e) => { e.preventDefault(); onOpenNote(n.id) }}>
            {displayTitle(n)}
            <span className="muted" style={{ marginInlineStart: 8 }}>{fmtDate(n.updated_at)}</span>
          </a>
        ))}
      </Section>

      <Section title={t('Related facts')} empty="">
        {related.map((f) => (
          <a key={f.id} href="#" className="kb-link"
             onClick={(e) => { e.preventDefault(); onOpen('kb:fact:' + f.id) }}>
            <span className="muted" style={{ marginInlineEnd: 8, flex: 'none', whiteSpace: 'nowrap' }}>{f.when}</span><span>{f.text}</span>
          </a>
        ))}
      </Section>
    </div>
  )
}

// ----------------------------------------------------------------- a category

function CollectionNote({ id, rows, onOpen }: Props) {
  const me = rows.find((r) => r.note_id === id)
  const subs = rows.filter((r) => r.parent_note_id === id && !isFactId(r.note_id))
  const [facts, setFacts] = useState<TreeRow[] | undefined>(undefined)

  useEffect(() => {
    let alive = true
    setFacts(undefined)
    void kbTreeChildren(id).then((f) => { if (alive) setFacts(f) }).catch(() => { if (alive) setFacts([]) })
    return () => { alive = false }
  }, [id])

  return (
    <div className="kb-note">
      <div className="muted kb-note-meta">
        <span>▤ {t('Knowledge base')}</span>
        {me && me.fact_count > 0 && <span>· {t('{n} facts', { n: me.fact_count })}</span>}
      </div>
      <h2 className="kb-note-title">{me?.title ?? id}</h2>
      {me?.preview && <p className="muted" style={{ marginTop: -6 }}>{t('Aliases: {aliases}', { aliases: me.preview })}</p>}

      {subs.length > 0 && (
        <Section title={id === 'kb' ? t('Categories') : t('Subcategories')} empty="">
          {subs.sort((a, b) => a.position - b.position).map((s) => (
            <a key={s.id} href="#" className="kb-link"
               onClick={(e) => { e.preventDefault(); onOpen(s.note_id) }}>
              ▤ {s.title}
              {s.fact_count > 0 && <span className="muted" style={{ marginInlineStart: 8 }}>{s.fact_count}</span>}
            </a>
          ))}
        </Section>
      )}

      {facts === undefined
        ? <p className="muted">…</p>
        : facts.length > 0 && (
          <Section title={t('Fact')} empty="">
            {facts.map((f) => (
              <a key={f.id} href="#" className="kb-link"
                 onClick={(e) => { e.preventDefault(); onOpen(f.note_id) }}>
                <span className="muted" style={{ marginInlineEnd: 8 }}>{f.updated_at}</span>{f.preview}
              </a>
            ))}
          </Section>
        )}
    </div>
  )
}

/** An original quote may be a whole meeting transcript (the real library has some thousands of chars long). Show the beginning first, expand to see more —
 *  the point of the "original quote" is checking the source, not rereading the whole meeting. */
const QUOTE_CHARS = 280
function Quote({ line }: { line: SourceLine }) {
  const [full, setFull] = useState(false)
  const long = line.text.length > QUOTE_CHARS
  const text = full || !long ? line.text : line.text.slice(0, QUOTE_CHARS) + '…'
  return (
    <blockquote className="kb-quote">
      <span className="muted">{line.who || '?'}{line.date ? ` · ${line.date}` : ''}{t(': ')}</span>{text}
      {long && (
        <a href="#" className="muted" style={{ marginInlineStart: 6 }}
           onClick={(e) => { e.preventDefault(); setFull((v) => !v) }}>
          {full ? t('Collapse') : t('Show full text ({n} chars)', { n: line.text.length })}
        </a>
      )}
    </blockquote>
  )
}

function Section({ title, empty, children }: {
  title: string; empty: string; children: React.ReactNode
}) {
  const kids = Array.isArray(children) ? children.filter(Boolean) : children ? [children] : []
  if (kids.length === 0 && !empty) return null
  return (
    <section className="kb-section">
      <h3 className="kb-section-title">{title}</h3>
      {kids.length === 0 ? <p className="muted" style={{ margin: 0 }}>{empty}</p> : kids}
    </section>
  )
}
