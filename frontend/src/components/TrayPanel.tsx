
import { useCallback, useEffect, useRef, useState } from 'react'
import { clipToTray, deleteTrayItem, listTray, putTray, type TrayItem, type TrayItemIn, type TrayKind } from '../api'
import { clickable } from '../util/clickable'
import { displayTitle } from '../util/displayTitle'
import { friendlyError } from '../util/friendlyError'
import { moveItem, setTrayCache, TRAY_KIND_ICON, TRAY_KIND_LABEL, TRAY_PREVIEW_CHARS, trayAddNotice, withItems, alreadyInTray, type TrayAddDetail } from '../util/tray'
import { setTrayByDefault, trayByDefault } from '../util/trayDefaults'
import { toast } from '../toast'
import Icon from './Icon'
import { t } from '../i18n'


export function trayItemTitle(it: Pick<TrayItem, 'kind' | 'title' | 'excerpt'>): string {
  return it.kind === 'note' ? displayTitle({ title: it.title, content: it.excerpt }) : it.title
}


export const TRAY_EMPTY_LINE = 'No materials yet. Add them from the memory cards below, or right-click a note link in the text.'


const KIND_CLS: Record<TrayKind, string> = { note: 'tray-kind-note', fact: 'tray-kind-fact', import: 'tray-kind-import', selection: 'tray-kind-selection' }

export default function TrayPanel({ noteId, onWrite }: {
  noteId: string
  /** The same thing as the `/` menu's "Write from tray": write a block at the cursor from the tray materials */
  onWrite?: () => void
}) {
  const [items, setItems] = useState<TrayItem[]>([])
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState<Set<string>>(() => new Set())
  const dragFrom = useRef<number | null>(null)
  const [dragOver, setDragOver] = useState<number | null>(null)
  const itemsRef = useRef(items)
  itemsRef.current = items

  const commit = useCallback((next: TrayItem[]) => { setItems(next); setTrayCache(noteId, next) }, [noteId])

  useEffect(() => {
    let alive = true
    setBusy(true)
    listTray(noteId)
      .then((r) => { if (alive) commit(r) })
      .catch((e) => { if (alive) toast(t('Could not load materials: {err}', { err: friendlyError(e) }), 'error') })
      .finally(() => { if (alive) setBusy(false) })
    return () => { alive = false }
  }, [noteId, commit])

  // Someone said "Put in tray": persist it here. Already in the tray: say so, do not add twice. A batch (the notes an import just produced) is one PUT.
  useEffect(() => {
    const on = (e: Event) => {
      const d = (e as CustomEvent<TrayAddDetail>).detail
      if (d.noteId && d.noteId !== noteId) return
      const batch: TrayItemIn[] = (d.items ?? (d.kind ? [d as TrayItemIn] : []))
        .filter((it) => !(it.kind === 'note' && it.ref_id === noteId))         // this note is not laid out on its own desk
      if (!batch.length) { if (d.kind === 'note' && d.ref_id === noteId) toast(t('The current note does not need to be in its own materials')); return }
      const fresh = batch.filter((it) => !alreadyInTray(itemsRef.current, it))
      if (!fresh.length) { toast(batch.length > 1 ? t('These are already materials') : t('Already in the materials')); return }
      putTray(noteId, withItems(itemsRef.current, fresh))
        .then((r) => { commit(r); toast((fresh.length > 1 ? t('Added {n} materials ({total} in total)', { n: fresh.length, total: r.length }) : t('Added to materials ({total} in total)', { total: r.length })) + trayAddNotice(fresh)) })
        .catch((err) => toast(t('Could not add to materials: {err}', { err: friendlyError(err) }), 'error'))
    }
    window.addEventListener('tray-add', on)
    return () => window.removeEventListener('tray-add', on)
  }, [noteId, commit])


  const [byDefault, setByDefault] = useState<boolean>(() => trayByDefault())
  useEffect(() => {
    const on = (e: Event) => setByDefault(Boolean((e as CustomEvent<boolean>).detail))
    window.addEventListener('tray-default-changed', on)
    return () => window.removeEventListener('tray-default-changed', on)
  }, [])

  // Web clip: paste a URL, the backend fetches the article into the tray (tray only)
  const [clipUrl, setClipUrl] = useState('')
  const [clipping, setClipping] = useState(false)
  function clip() {
    const url = clipUrl.trim()
    if (!/^https?:\/\//i.test(url)) { toast(t('Paste a URL starting with http(s)')); return }
    setClipping(true)
    clipToTray(noteId, url)
      .then((r) => { commit(r); setClipUrl(''); toast(t('Web page added to materials ({total} in total)', { total: r.length })) })
      .catch((e) => toast(t('Could not add the web page: {err}', { err: friendlyError(e) }), 'error'))
      .finally(() => setClipping(false))
  }

  function reorder(from: number, to: number) {
    const next = moveItem(items, from, to)
    if (next === items) return
    commit(next)                                                     // update the UI first, roll back if persisting fails
    putTray(noteId, next.map(({ id, kind, ref_id, title, excerpt }) => ({ id, kind, ref_id, title, excerpt })))
      .then(commit)
      .catch((e) => { commit(items); toast(t('Order not saved: {err}', { err: friendlyError(e) }), 'error') })
  }
  function remove(it: TrayItem) {
    deleteTrayItem(noteId, it.id).then(commit).catch((e) => toast(t('Could not remove: {err}', { err: friendlyError(e) }), 'error'))
  }
  function openOriginal(it: TrayItem) {
    if (it.kind === 'note') window.dispatchEvent(new CustomEvent('open-note', { detail: it.ref_id }))
    else if (it.kind === 'fact') window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:fact:' + it.ref_id }))
    else if (it.kind === 'import' && /^https?:\/\//i.test(it.ref_id)) window.open(it.ref_id, '_blank', 'noopener')   // web clip: open the original page
    else setOpen((s) => { const n = new Set(s); if (n.has(it.id)) n.delete(it.id); else n.add(it.id); return n })
  }

  return (
    <div className="tray-panel" data-count={items.length}>
      <div className="row tray-head" style={{ alignItems: 'center' }}>
        <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 'var(--s-2)' }}><Icon n="bx-layer-plus" /> {t('Materials')}</h2>
        <span className="badge" title={t('Number of materials picked for this note')}>{items.length}</span>
        {busy && <span className="spinner" />}
        <span style={{ flex: 1 }} />
        {items.length > 0 && onWrite && (
          <button className="tray-write" onClick={onWrite} title={t('Write a passage at the cursor using only these materials')}>
            <Icon n="bx-pen" /> {t('Write from materials')}
          </button>
        )}
      </div>
      {}
      {items.length > 0 ? (
        <p className="muted tray-hint">
          {t('The AI prioritizes these materials when writing this note.')}
        </p>
      ) : !busy && (
        <p className="muted tray-hint">
          {t(TRAY_EMPTY_LINE)}
        </p>
      )}
      <div className="tray-tools">
        <label className="row tray-default" title={t('When on, newly imported notes, recording transcripts and web clips are added to the current note’s materials')}>
          <input type="checkbox" checked={byDefault} onChange={(e) => { setByDefault(e.target.checked); setTrayByDefault(e.target.checked) }} />
          <span>{t('Add imports / recordings / clips to materials')}</span>
        </label>
        <form className="row tray-clip" onSubmit={(e) => { e.preventDefault(); clip() }}>
          <input type="url" className="tray-clip-url" placeholder={t('Paste a URL to add to materials')} aria-label={t('URL to clip')}
                 value={clipUrl} onChange={(e) => setClipUrl(e.target.value)} disabled={clipping} />
          <button type="submit" className="tray-clip-go" disabled={clipping || !clipUrl.trim()} title={t('Extract the page text and add it to materials')}>
            {clipping ? <span className="spinner" /> : <Icon n="bx-link" />} {t('Clip')}
          </button>
        </form>
      </div>
      {items.length > 0 && (
        <ol className="tray-list" aria-label={t('Materials')}>
          {items.map((it, i) => {
            const expanded = open.has(it.id)
            const text = expanded || it.excerpt.length <= TRAY_PREVIEW_CHARS ? it.excerpt : it.excerpt.slice(0, TRAY_PREVIEW_CHARS) + '…'
            return (
              <li key={it.id}
                  className={'tray-item' + (dragOver === i ? ' drag-over' : '')}
                  draggable
                  onDragStart={(e) => { dragFrom.current = i; e.dataTransfer.effectAllowed = 'move' }}
                  onDragOver={(e) => { e.preventDefault(); if (dragOver !== i) setDragOver(i) }}
                  onDragLeave={() => setDragOver((d) => (d === i ? null : d))}
                  onDrop={(e) => { e.preventDefault(); const from = dragFrom.current; dragFrom.current = null; setDragOver(null); if (from !== null) reorder(from, i) }}
                  onDragEnd={() => { dragFrom.current = null; setDragOver(null) }}>
                <span className="tray-handle" title={t('Drag to reorder (or use the arrows on the right)')} aria-hidden="true"><Icon n="bx-dots-horizontal-rounded" /></span>
                <div className="tray-body">
                  <div className="row" style={{ gap: 'var(--s-2)', alignItems: 'center' }}>
                    <span className={'badge tray-kind ' + KIND_CLS[it.kind]}><Icon n={TRAY_KIND_ICON[it.kind]} /> {t(TRAY_KIND_LABEL[it.kind])}</span>
                    {trayItemTitle(it) && <span className="tray-title" title={trayItemTitle(it)}>{trayItemTitle(it)}</span>}
                  </div>
                  {it.excerpt && (
                    <div className="tray-excerpt" title={expanded ? t('Collapse') : t('Click to see the full text')}
                         {...clickable(() => setOpen((s) => { const n = new Set(s); if (n.has(it.id)) n.delete(it.id); else n.add(it.id); return n }))}>
                      {text}
                    </div>
                  )}
                </div>
                <span className="tray-actions">
                  <button className="icon-btn" title={t('Move up')} disabled={i === 0} onClick={() => reorder(i, i - 1)}><Icon n="bx-chevron-up" /></button>
                  <button className="icon-btn" title={t('Move down')} disabled={i === items.length - 1} onClick={() => reorder(i, i + 1)}><Icon n="bx-chevron-down" /></button>
                  <button className="icon-btn" title={it.kind === 'note' ? t('Open this note') : it.kind === 'fact' ? t('Open this fact') : it.kind === 'import' && /^https?:\/\//i.test(it.ref_id) ? t('Open the original page') : expanded ? t('Collapse') : t('Show full text')}
                          onClick={() => openOriginal(it)}><Icon n="bx-link-external" /></button>
                  <button className="icon-btn" title={t('Remove from materials (the original is untouched)')} onClick={() => remove(it)}><Icon n="bx-x" /></button>
                </span>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
