/** Recently deleted: deleted notes can be recovered within 30 days (Trilium's deletes are undoable too). Once the 5-second undo window has passed,
 *  this is the only way back. Restore = same id, back in its original place (a parent that is also here is restored with it; only if the parent is truly gone does it hang off the tree root), revisions come back too. */
import { useEffect, useState } from 'react'

import { listTrash, purgeTrash, restoreTrash, type TrashItem } from '../api'
import { toast } from '../toast'
import { fmtDateTime } from '../util/time'
import Icon from './Icon'
import { t } from '../i18n'

export default function TrashPanel({ onRestored }: { onRestored: (id: string) => void }) {
  const [items, setItems] = useState<TrashItem[] | null>(null)
  const [busy, setBusy] = useState('')
  const load = () => listTrash().then(setItems).catch(() => setItems([]))
  useEffect(() => { void load() }, [])

  async function restore(it: TrashItem) {
    setBusy(it.note_id)
    try {
      await restoreTrash(it.note_id)
      toast(t('“{title}” restored', { title: it.title || t('Untitled') }))
      window.dispatchEvent(new CustomEvent('notes-changed'))
      await load()
      onRestored(it.note_id)
    } catch (e) { toast(t('Restore failed: {err}', { err: String(e) }), 'error') }
    finally { setBusy('') }
  }
  async function purge(it: TrashItem) {
    setBusy(it.note_id)
    try { await purgeTrash(it.note_id); await load() }
    catch (e) { toast(String(e), 'error') }
    finally { setBusy('') }
  }

  if (items === null) return <p className="muted"><span className="spinner" /> {t('Loading…')}</p>
  return (
    <div className="stack" style={{ gap: 8 }}>
      <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>{t('Deleted notes stay here for 30 days. Restore puts a note back where it was (at the top level if its parent is gone too), with its version history; “Delete permanently” really removes it.')}</p>
      {items.length === 0 && <p className="muted" style={{ fontSize: 'var(--t-md)' }}>{t('No notes deleted in the last 30 days.')}</p>}
      {items.map((it) => (
        <div key={it.note_id} className="card row" style={{ alignItems: 'center', gap: 10, padding: '8px 10px' }}>
          <Icon n="bx-trash" className="muted" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 'var(--t-md)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.title || t('Untitled')}</div>
            <div className="muted" style={{ fontSize: 'var(--t-xs)' }}>{t('Deleted {when}', { when: fmtDateTime(it.deleted_at) })} · {t('{n} chars', { n: it.chars })}</div>
          </div>
          <button style={{ fontSize: 'var(--t-sm)', padding: '2px 10px' }} disabled={busy === it.note_id} onClick={() => void restore(it)}>{t('Restore')}</button>
          <button style={{ fontSize: 'var(--t-sm)', padding: '2px 10px' }} disabled={busy === it.note_id} title={t('Really delete; cannot be recovered')} onClick={() => void purge(it)}>{t('Delete permanently')}</button>
        </div>
      ))}
    </div>
  )
}
