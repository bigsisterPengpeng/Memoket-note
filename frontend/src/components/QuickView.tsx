/**
 * Quick view -- read another note without leaving the current one (Trilium's PopupEditor).
 *
 * A direct application of criterion 2: "leaving the current page to look at an old record = failure". The right pane's
 * related memory solved "surfacing", but reading the full text used to mean opening a new tab and switching away. This is
 * an overlay: read it, close it, and the body and cursor are still where they were.
 */
import { useEffect } from 'react'
import { useRestoreFocus } from '../util/restoreFocus'

import type { Note } from '../api'
import { displayTitle } from '../util/displayTitle'
import MarkdownEditor from './MarkdownEditor'
import { fmtDate } from '../util/time'
import Icon from './Icon'
import { t } from '../i18n'

export default function QuickView({ note, onClose, onOpen }: {
  note: Note
  onClose: () => void
  onOpen: (n: Note) => void
}) {
  useRestoreFocus()
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onClose])
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal quick-view" role="dialog" aria-label={t('Quick view')} onMouseDown={(e) => e.stopPropagation()}>
        <div className="row" style={{ alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <b style={{ flex: 1, fontSize: 'var(--t-base)' }}>{displayTitle(note)}</b>
          <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{fmtDate(note.updated_at)}</span>
          <button onClick={() => { onClose(); onOpen(note) }}>{t('Open in a tab')}</button>
          <button className="icon-btn" title={t('Close (Esc)')} aria-label={t('Close')} onClick={onClose}><Icon n="bx-x" /></button>
        </div>
        <div className="quick-view-body">
          {note.content.trim() ? <MarkdownEditor content={note.content} readOnly /> : <p className="muted" style={{ margin: '8px 0' }}>{t('This note is still empty.')}</p>}
        </div>
      </div>
    </div>
  )
}
