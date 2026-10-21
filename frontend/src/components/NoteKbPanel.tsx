/**
 * The "Knowledge base" tab in the ribbon: **everything this note has to do with the knowledge base, in one place**.
 * Design in docs/kb-fusion-design.md §3.4.
 *
 * Three things: which records it cites (each can be peeked), whether it has been ingested, and whether it cites facts that **no longer exist**
 * -- the last one is a real problem (made up by the model, or the knowledge base was rebuilt and ids changed); hiding it
 * means letting a note rest on evidence that does not exist.
 */
import { useEffect, useState, lazy, Suspense } from 'react'
import { t } from '../i18n'

const LocalGraph = lazy(() => import('./kb/LocalGraph'))
import { fmtDate } from '../util/time'

import { addFact, deleteFact, factPeek, noteKb, notesCiting, updateFact, type CitingNote, type FactPeek, type NoteKb, type TreeRow, noteGraph, type NoteGraph } from '../api'
import { displayTitle } from '../util/displayTitle'
import { toast } from '../toast'
import { friendlyError } from '../util/friendlyError'
import Icon from './Icon'

export default function NoteKbPanel({ citedIds, row, noteId, onIngest, onSync, ingesting, onOpenNote, refreshTick = 0, empty = false, onStripMissing }: {
  citedIds: string[]
  /** Remove the citations that cannot be found from the body (only the `[id]`; the sentence stays) */
  onStripMissing?: (ids: string[]) => void
  /** The body is empty: clicking "Save to knowledge base" would do nothing (App just returns), so grey it out and say why */
  empty?: boolean
  row: TreeRow | undefined
  noteId: string
  onIngest: () => void
  /** Sync: the server reads the latest body, deletes the old session and re-extracts (manually added facts stay) */
  onSync: () => void
  ingesting: boolean
  onOpenNote: (id: string) => void
  /** +1 after ingest / sync finishes; the contribution list reloads */
  refreshTick?: number
}) {
  // Which facts this note contributed + whether it changed without syncing. Only queried if ingested; queried again after ingest finishes.
  const [kb, setKb] = useState<NoteKb | null>(null)
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null)
  const [adding, setAdding] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    setKb(null)
    noteKb(noteId).then((k) => { if (alive) setKb(k) }).catch(() => {})
    return () => { alive = false }
    // stale (changed, not synced) is judged server-side by updated_at vs ingested_at: re-query after persisting, or the yellow text only appears after reopening the note
  }, [noteId, refreshTick, row?.ingested_at, row?.updated_at])

  async function saveEdit() {
    if (!editing) return
    const text = editing.text.trim()
    if (!text) { setEditing(null); return }
    try {
      const f = await updateFact(editing.id, text)
      setKb((k) => (k ? { ...k, facts: k.facts.map((x) => (x.id === f.id ? { ...x, text: f.text } : x)) } : k))
      setEditing(null)
    } catch (e) { toast(t('Could not edit: {err}', { err: friendlyError(e) }), 'error') }
  }
  async function remove(id: string) {
    try {
      await deleteFact(id)
      setKb((k) => (k ? { ...k, facts: k.facts.filter((x) => x.id !== id) } : k))
    } catch (e) { toast(t('Could not delete: {err}', { err: friendlyError(e) }), 'error') }
  }
  async function saveAdd() {
    const text = (adding ?? '').trim()
    if (!text) { setAdding(null); return }
    try {
      const f = await addFact(noteId, text)
      setKb((k) => (k ? { ...k, ingested_at: k.ingested_at || new Date().toISOString(), facts: [...k.facts, f] } : k))
      setAdding(null)
    } catch (e) { toast(t('Could not add: {err}', { err: friendlyError(e) }), 'error') }
  }

  // Backlinks: which other notes cite the same evidence. Trilium's Backlinks is "who links to me";
  // the question here is "who shares evidence with me" -- for a note tool that is the useful neighbor.
  const [citing, setCiting] = useState<Record<string, CitingNote[]>>({})
  // null = queried and does not exist; undefined = not queried yet
  const [facts, setFacts] = useState<Record<string, FactPeek | null | undefined>>({})

  useEffect(() => {
    let alive = true
    for (const id of citedIds) {
      if (facts[id] !== undefined) continue
      void factPeek(id).then((f) => { if (alive) setFacts((m) => ({ ...m, [id]: f })) })
      void notesCiting(id).then((ns) => { if (alive) setCiting((m) => ({ ...m, [id]: ns })) })
    }
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [citedIds])

  const missing = citedIds.filter((id) => facts[id] === null)

  // What surrounds this note: which topics / entities the cited + contributed facts hang on (our version of Trilium's NoteMap)
  const [graph, setGraph] = useState<NoteGraph | null>(null)
  // The graph is computed from the body **persisted** on the server: re-query on row.updated_at (the tree row refreshes after autosave persists), not on the local citation count --

  useEffect(() => {
    let alive = true
    noteGraph(noteId).then((g) => { if (alive) setGraph(g) }).catch(() => {})
    return () => { alive = false }
  }, [noteId, refreshTick, row?.updated_at, row?.ingested_at])

  return (
    <div className="stack" style={{ fontSize: 'var(--t-md)' }}>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
        {row?.ingested_at
          ? <span className="muted">⇡ {t('Saved to knowledge base')} · {fmtDate(row.ingested_at)}</span>
          : <span className="muted">{t('Not saved to the knowledge base yet')}</span>}
        {row?.ingested_at
          ? <button onClick={onSync} disabled={ingesting} style={{ marginInlineStart: 'auto' }} title={t('The server re-reads the latest text, drops the facts extracted last time and extracts again; facts you added by hand are kept')}>
              {ingesting ? <span className="spinner" /> : (kb?.stale ? t('Sync to knowledge base') : t('Re-sync'))}
            </button>
          : <button onClick={onIngest} disabled={ingesting || empty} style={{ marginInlineStart: 'auto' }} title={empty ? t('The note is empty — write something first') : undefined}>
              {ingesting ? <span className="spinner" /> : <><Icon n="bx-import" /> {t('Save to knowledge base')}</>}
            </button>}
      </div>
      {kb?.stale && !ingesting && (
        // Changed-not-synced must stand out: the ⇡ in the tree turns yellow too. With auto-sync on it runs by itself after a while.
        <div className="card" style={{ borderColor: 'var(--warn)', background: 'var(--warning-weak)', color: 'var(--warn)', padding: '6px 8px' }}>
          {t('The note changed after it was ingested on {date}; the knowledge base still has the old version — click “Sync to knowledge base”, or turn on auto-sync in Settings.', { date: fmtDate(kb.ingested_at) })}
        </div>
      )}

      {/* Facts this note contributed: editable, deletable, extendable. Fixing an extractor mistake saves a model call compared to re-ingesting. */}
      {row?.ingested_at && (
        <div className="stack" style={{ gap: 6 }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
            <strong style={{ fontSize: 'var(--t-sm)' }}>{t('Facts from this note')}{kb ? ' · ' + t('{n} items', { n: kb.facts.length }) : ''}</strong>
            {adding === null && <button onClick={() => setAdding('')} style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }}><Icon n="bx-plus" /> {t('Add one')}</button>}
          </div>
          {adding !== null && (
            <div className="stack" style={{ gap: 4 }}>
              <textarea aria-label={t('New fact')} rows={2} value={adding} autoFocus placeholder={t('One sentence stating one thing (who, when, what)')}
                        onChange={(e) => setAdding(e.target.value)} />
              <div className="row" style={{ gap: 6 }}>
                {}
                <button className="primary" onClick={() => void saveAdd()} disabled={!(adding ?? '').trim()}
                        title={(adding ?? '').trim() ? undefined : t('Write a sentence first: who, when, what')}
                        style={{ fontSize: 'var(--t-sm)', padding: '2px 10px' }}>{t('Add')}</button>
                <button onClick={() => setAdding(null)} style={{ fontSize: 'var(--t-sm)', padding: '2px 10px' }}>{t('Never mind')}</button>
              </div>
            </div>
          )}
          {kb === null && <p className="muted" style={{ margin: 0, fontSize: 'var(--t-sm)' }}><span className="spinner" /> {t('Checking…')}</p>}
          {kb && kb.facts.length === 0 && <p className="muted" style={{ margin: 0, fontSize: 'var(--t-sm)' }}>{t('No facts worth recording were extracted when this note was ingested.')}</p>}
          {kb?.facts.map((f) => (
            <div key={f.id} className="card" style={{ padding: '6px 8px' }}>
              {editing?.id === f.id ? (
                <div className="stack" style={{ gap: 4 }}>
                  <textarea aria-label={t('Edit this fact')} rows={2} value={editing.text} autoFocus onChange={(e) => setEditing({ id: f.id, text: e.target.value })} />
                  <div className="row" style={{ gap: 6 }}>
                    {}
                    <button className="primary" onClick={() => void saveEdit()} disabled={!editing.text.trim()}
                            title={editing.text.trim() ? undefined : t('Cannot save an empty fact — to remove it use “Delete from knowledge base” on the right')}
                            style={{ fontSize: 'var(--t-sm)', padding: '2px 10px' }}>{t('Save')}</button>
                    <button onClick={() => setEditing(null)} style={{ fontSize: 'var(--t-sm)', padding: '2px 10px' }}>{t('Cancel')}</button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="row" style={{ gap: 6, alignItems: 'flex-start' }}>
                    <div style={{ flex: 1, minWidth: 0 }}>{f.text}</div>
                    <button className="icon-btn" title={t('Edit')} onClick={() => setEditing({ id: f.id, text: f.text })}><Icon n="bx-edit-alt" /></button>
                    <button className="icon-btn" title={t('Delete from knowledge base')} onClick={() => void remove(f.id)}><Icon n="bx-x" /></button>
                  </div>
                  <div className="muted" style={{ fontSize: 'var(--t-xs)' }}>
                    {f.when || '—'}{f.who ? ` · ${f.who}` : ''}{f.kind ? ` · ${f.kind}` : ''}{f.manual ? ' · ' + t('added by hand') : ''}
                    <code style={{ fontSize: 'var(--t-2xs)', marginInlineStart: 6 }}>[{f.id}]</code>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {missing.length > 0 && (
        // **Missing ones must stand out.** This is a note resting on evidence that does not exist.
        <div className="card" style={{ borderColor: 'var(--del)', background: 'var(--live-weak)', color: 'var(--del)' }}>
          {/* Only list the first 8: with 300 missing (a long fabricated test note) a block of red text filled the whole panel */}
          {t('{n} citations not found in the knowledge base: ', { n: missing.length })}{missing.slice(0, 8).join(', ')}{missing.length > 8 ? t('… and {n} more', { n: missing.length - 8 }) : ''}
          <div className="row" style={{ gap: 8, alignItems: 'center' }}>
            <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('The citations may be wrong, or the knowledge base was rebuilt')}</span>
            {onStripMissing && (
              <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px', marginInlineStart: 'auto' }} title={t('Remove only these [id] markers from the text; the sentences stay')}
                      onClick={() => onStripMissing(missing)}>{t('Remove these citations')}</button>
            )}
          </div>
        </div>
      )}

      <strong style={{ fontSize: 'var(--t-sm)' }}>{t('Facts cited by this note')}{citedIds.length ? ' · ' + t('{n} items', { n: citedIds.length }) : ''}</strong>
      {citedIds.length === 0
        ? <p className="muted" style={{ margin: 0 }}>{t('This note does not cite any knowledge base record yet. Content inserted by Continue and Trace carries citations automatically.')}</p>
        : citedIds.map((id) => {
          const f = facts[id]
          return (
            <div key={id} className="card" style={{ padding: '6px 8px' }}>
              <div className="muted" style={{ fontSize: 'var(--t-xs)' }}>
                {f ? `${f.when} · ${f.kind}` : id}
              </div>
              <div>{f === undefined ? '…' : f === null ? t('(not found)') : f.text}</div>
              {(citing[id] ?? []).filter((n) => n.id !== noteId).length > 0 && (
                <div className="muted" style={{ fontSize: 'var(--t-xs)', marginTop: 4 }}>
                  {t('Also cited in: ')}
                  {(citing[id] ?? []).filter((n) => n.id !== noteId).map((n) => (
                    <a key={n.id} href="#" onClick={(e) => { e.preventDefault(); onOpenNote(n.id) }}
                       style={{ marginInlineStart: 6 }}>{displayTitle(n)}</a>
                  ))}
                </div>
              )}
            </div>
          )
        })}

      {}
      {graph && graph.topics.length + graph.entities.length >= 2 && (
        <div className="stack" style={{ gap: 4 }}>
          <strong style={{ fontSize: 'var(--t-sm)' }}>{t('Around this note')} <span className="muted" style={{ fontWeight: 'var(--w-normal)' }}>· {t('topics and entities connected through {n} facts; click a node to open its page', { n: graph.facts })}</span></strong>
          <Suspense fallback={<p className="muted">…</p>}>          <LocalGraph topics={graph.topics} entities={graph.entities} links={graph.links} height={200}
                      actions={{ onOpen: (id) => window.dispatchEvent(new CustomEvent('open-virtual', { detail: id })), onOpenNote, onCite: null }} /></Suspense>
        </div>
      )}
    </div>
  )
}
