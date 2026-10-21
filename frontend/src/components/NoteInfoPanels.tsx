/**
 * The two ribbon tabs that "semantically belong in the ribbon" (Trilium's NoteInfoTab /
 * NotePathsTab):
 * · Note info: created/modified time, word count, links to the knowledge base
 * · Note paths: **after cloning, a note lives in several places at once**; the user must be able to see "where else it is",
 *   or they edit one place without knowing which others change with it
 */
import { useEffect, useState } from 'react'

import { notePaths, noteRemotes, type Note, type NoteRemote, type TreeRow } from '../api'
import { displayTitle } from '../util/displayTitle'
import { fmtDate, fmtDateTime } from '../util/time'
import { openRemote, remoteUrl } from '../util/useExportBack'
import { readingMinutes, wordCount } from '../util/wordCount'
import Icon from './Icon'
import { t } from '../i18n'

const SOURCE_LABEL: Record<string, string> = { obsidian: 'Obsidian', notion: 'Notion', apple: 'Apple Notes', evernote: 'Evernote', feishu: 'Feishu', import: 'Import' }

export function NoteInfoPanel({ note, content, row }: { note: Note; content: string; row?: TreeRow }) {
  const words = wordCount(content)
  // Export-back copies (docs/import-sync-plan.md §2): which platforms have a copy of this note, and when it was last exported back
  const [remotes, setRemotes] = useState<NoteRemote[]>([])
  useEffect(() => {
    let alive = true
    const load = () => { noteRemotes(note.id).then((r) => { if (alive) setRemotes(r) }).catch(() => { /* none is fine */ }) }
    load()
    window.addEventListener('note-remotes-changed', load)
    return () => { alive = false; window.removeEventListener('note-remotes-changed', load) }
  }, [note.id])
  return (
    <dl className="kv">
      <dt>{t('Created')}</dt><dd>{fmtDateTime(note.created_at)}</dd>
      <dt>{t('Modified')}</dt><dd>{fmtDateTime(note.updated_at)}</dd>
      <dt>{t('Words')}</dt><dd>{words}{words > 0 && <> · {t('about {n} min read', { n: readingMinutes(words) })}</>}</dd>
      <dt>{t('Quote')}</dt><dd>{row?.cite_count ? t('{n} knowledge base records', { n: row.cite_count }) : t('None')}</dd>
      <dt>{t('Ingested')}</dt><dd>{row?.ingested_at ? t('Ingested ({date})', { date: fmtDate(row.ingested_at) }) : t('Not ingested')}</dd>
      {note.source && <><dt>{t('Source')}</dt><dd>{t(SOURCE_LABEL[note.source] ?? note.source)}{note.imported_at ? ' · ' + t('imported {date}', { date: fmtDate(note.imported_at) }) : ''}{note.imported_at && note.updated_at > note.imported_at ? ' · ' + t('edited locally') : ''}</dd></>}
      {}
      {remotes.length > 0 && <><dt>{t('Copies')}</dt><dd>{remotes.map((r, i) => {
        const url = remoteUrl(r)
        const label = `${t(SOURCE_LABEL[r.platform] ?? r.platform)} · ` + t('exported back {date}', { date: fmtDate(r.exported_at) }) + (r.exported_at < note.updated_at ? t(' (edited since)') : '')
        return <span key={r.platform}>{i > 0 && '; '}{url ? <a href={url} className="link" title={url} onClick={(e) => { e.preventDefault(); openRemote(url) }}>{label}<Icon n="bx-link-external" /></a> : label}</span>
      })}</dd></>}
      <dt>{t('Locations')}</dt><dd>{row?.branch_count && row.branch_count > 1 ? t('{n} places (cloned)', { n: row.branch_count }) : t('1 place')}</dd>
      <dt>id</dt><dd><code style={{ fontSize: 'var(--t-xs)' }}>{note.id}</code></dd>
    </dl>
  )
}

export function NotePathsPanel({ noteId, rows, onOpen, onClone }: {
  noteId: string
  rows: TreeRow[]
  onOpen: (noteId: string) => void
  /** Trilium's note paths widget has "clone to a new location" right under the list */
  onClone?: () => void
}) {
  const [paths, setPaths] = useState<string[][] | null>(null)
  useEffect(() => {
    let alive = true
    setPaths(null)
    notePaths(noteId).then((p) => { if (alive) setPaths(p) }).catch(() => { if (alive) setPaths([]) })
    return () => { alive = false }
  }, [noteId, rows])
  const name = (id: string) => {
    const r = rows.find((x) => x.note_id === id)
    return r ? displayTitle(r) : id
  }
  if (paths === null) return <p className="muted" style={{ margin: 0 }}>…</p>
  return (
    <div className="stack" style={{ fontSize: 'var(--t-md)' }}>
      {paths.length > 1 && (
        <p className="muted" style={{ margin: 0, fontSize: 'var(--t-sm)' }}>
          {t('This note lives in {n} places at once — they are the same note; edit one and all change.', { n: paths.length })}
        </p>
      )}
      {paths.map((p, i) => (
        <div key={i} className="breadcrumb">
          <span className="muted">{t('Root')}</span>
          {p.map((id, k) => (
            <span key={id}>
              <span className="muted"> / </span>
              {k === p.length - 1
                ? <b>{name(id)}</b>
                : <a href="#" onClick={(e) => { e.preventDefault(); onOpen(id) }}>{name(id)}</a>}
            </span>
          ))}
        </div>
      ))}
      {onClone && (
        <div>
          <button className="chip" onClick={onClone}><Icon n="bx-duplicate" /> {t('Clone to another location…')}</button>
        </div>
      )}
    </div>
  )
}
