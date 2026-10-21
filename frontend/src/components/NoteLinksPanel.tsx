import { useEffect, useState } from 'react'
import { linkedNoteIds } from '../util/wordCount'
import * as api from '../api'
import { displayTitle } from '../util/displayTitle'
import { fmtDate } from '../util/time'
import Icon from './Icon'
import { t } from '../i18n'

/** Ribbon "Links": notes this one links out to + notes linking in. Type `[[` to insert a link. */
export default function NoteLinksPanel({ noteId, content, onOpen, onUnlink, knownIds, knownNotes, updatedAt }: {
  noteId: string
  content: string
  onOpen: (noteId: string) => void
  /** Turn links to deleted notes into plain text (the title is kept) */
  onUnlink?: (ids: string[]) => void
  /** Note ids currently in the library: broken links are computed locally from the body (the server's dangling list only updates once autosave persists, 1.5 s later) */
  knownIds?: Set<string>
  /** Notes in the library (App's notes): the outgoing list is also computed locally from the body -- a [[ link just typed should show up here without waiting for persistence;
   *  the incoming list still has to ask the server (other notes' bodies live on the server) */
  knownNotes?: api.Note[]
  /** When this note was last persisted: the incoming list re-queries with it */
  updatedAt?: string
}) {
  const [links, setLinks] = useState<api.NoteLinks | null>(null)
  // Re-query only when the number of links in the body changes -- no need to query on every keystroke
  const linked = linkedNoteIds(content)
  const outgoingKey = linked.join(',')
  useEffect(() => {
    let alive = true
    api.noteLinks(noteId).then((r) => { if (alive) setLinks(r) }).catch(() => { if (alive) setLinks({ outgoing: [], backlinks: [] }) })
    return () => { alive = false }
  }, [noteId, outgoingKey, updatedAt])
  if (!links) return <p className="muted" style={{ margin: 0 }}>…</p>
  const list = (rows: api.CitingNote[], empty: string) => rows.length === 0
    ? <p className="muted" style={{ margin: 0, fontSize: 'var(--t-sm)' }}>{empty}</p>
    : rows.map((n) => (
      <a key={n.id} className="kb-link" onClick={() => onOpen(n.id)}>
        <Icon n={(n.icon || 'bx-note')} /> <span className="ellipsis">{displayTitle(n)}</span>
        <span className="muted" style={{ marginInlineStart: 'auto', fontSize: 'var(--t-xs)' }}>{fmtDate(n.updated_at)}</span>
      </a>
    ))
  // Outgoing: computed locally when notes are available (in body order, deduplicated, only notes that still exist)
  const outgoing: api.CitingNote[] = knownNotes
    ? linked.map((id) => knownNotes.find((n) => n.id === id)).filter((n): n is api.Note => !!n)
        .map((n) => ({ id: n.id, title: n.title, updated_at: n.updated_at, preview: (n.content || '').slice(0, 80), icon: n.icon }))
    : links.outgoing
  const dangling = knownIds
    ? linked.filter((id) => !knownIds.has(id))
    : (links.dangling ?? [])
  return (
    <div className="stack" style={{ gap: 8 }}>
    {dangling.length > 0 && (
      // The linked note is gone (deleted / imported from another library): it used to be dropped silently, only a hover in the body revealed it
      <div className="card" style={{ borderColor: 'var(--del)', color: 'var(--del)', fontSize: 'var(--t-md)' }}>
        {t('{n} links point to notes that no longer exist', { n: dangling.length })}
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('Hovering that link in the note shows “This note no longer exists”')}</span>
          {onUnlink && <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px', marginInlineStart: 'auto' }} title={t('Turn the links into plain text; the words stay')} onClick={() => onUnlink(dangling)}>{t('Convert to plain text')}</button>}
        </div>
      </div>
    )}
    <div className="row" style={{ gap: 24, alignItems: 'flex-start', fontSize: 'var(--t-md)' }}>
      <section style={{ flex: 1, minWidth: 0 }}>
        <p className="muted palette-group" style={{ marginInline: 0 }}>{t('Links to')} {outgoing.length > 0 && `· ${outgoing.length}`}</p>
        {list(outgoing, t('Type [[ in the note to search titles and link another note.'))}
      </section>
      <section style={{ flex: 1, minWidth: 0 }}>
        <p className="muted palette-group" style={{ marginInline: 0 }}>{t('Linked from')} {links.backlinks.length > 0 && `· ${links.backlinks.length}`}</p>
        {list(links.backlinks, t('No other note links here yet.'))}
      </section>
    </div>
    </div>
  )
}
