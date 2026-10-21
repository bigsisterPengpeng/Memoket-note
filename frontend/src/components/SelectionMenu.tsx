import { useEffect, useRef } from 'react'
import { useRestoreFocus } from '../util/restoreFocus'
import Icon from './Icon'
import { t } from '../i18n'

export type SelectionAction = 'verify' | 'rewrite' | 'polish' | 'expand' | 'trace' | 'custom'

/**
 * Right-click-with-a-selection context menu. Standard AI-editor actions
 * (Notion/Craft-style "ask AI about this selection") scoped to whatever
 * text is highlighted, rather than the whole note -- verify/rewrite/polish/
 * expand all need "what did the user select", which magic-tap/edit (whole-
 * document actions) don't.
 */
const BUSY_LABEL: Record<SelectionAction, string> = {
  verify: 'Verifying…', rewrite: 'Rewriting…', polish: 'Polishing…', expand: 'Finding context…', trace: 'Tracing…', custom: 'Working…',
}

export default function SelectionMenu({ x, y, busy, onAction, onStop, onClose }: {
  x: number
  y: number

  busy: false | SelectionAction
  onAction: (action: SelectionAction) => void

  onStop?: () => void
  onClose: () => void
}) {
  useRestoreFocus()   // After closing, focus returns to where it was before opening (editor / tree row)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onDocMouseDown(e: MouseEvent) {
      // **A right click does not count as "clicked outside".** A right-click mousedown is immediately followed by contextmenu,
      // and that contextmenu decides by itself whether to reopen the menu at a new position; closing here first would,
      // when the new position has no selection, turn into "menu closed, no new menu" -- what the user sees is
      // nothing at all after a right click.
      if (e.button === 2) return
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    // capture-phase mousedown so this closes before a click elsewhere (e.g.
    // re-selecting text) does anything else with that click.
    document.addEventListener('mousedown', onDocMouseDown, true)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown, true)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [onClose])

  const left = Math.min(x, window.innerWidth - 180)
  const top = Math.min(y, window.innerHeight - 200)

  return (
    <div
      ref={ref}
      className="palette"
      role="menu" aria-label={t('Actions for the selected text')}
      style={{ position: 'fixed', left, top, width: 160, padding: 4, zIndex: 250 }}
    >
      {busy ? (
        <div className="muted" style={{ padding: 10, textAlign: 'center', fontSize: 'var(--t-sm)' }}><span className="spinner" /> {t(BUSY_LABEL[busy])}
          {onStop && <button className="linklike link" style={{ marginInlineStart: 8 }} onClick={onStop}>{t('Stop')}</button>}
        </div>
      ) : (
        <div className="palette-results" style={{ padding: 0 }}>
          <div className="palette-item" onClick={() => onAction('verify')}><Icon n="bx-check-shield" /> {t('Verify')}</div>
          <div className="palette-item" onClick={() => onAction('rewrite')}><Icon n="bx-edit-alt" /> {t('Rewrite')}</div>
          <div className="palette-item" onClick={() => onAction('polish')}><Icon n="bx-star" /> {t('Polish')}</div>
          <div className="palette-item" onClick={() => onAction('expand')}><Icon n="bx-expand-horizontal" /> {t('Expand context')}</div>
          {/* Background: how the things this passage touches evolved over time. **The user writes no question** --
              the backend builds the question (criterion 1). Pain point 13: when summarizing scattered notes the AI cannot untangle
              the timeline, and KITE's planning happens to be good at time order. */}
          <div className="palette-item" onClick={() => onAction('trace')}><Icon n="bx-history" /> {t('Trace')}</div>
          {/* The same harness as `/`'s "Write with AI"; the difference is **scope**: that one is
              "insert a block at the cursor", this one is "do something with the passage I selected". */}
          <div className="palette-item" onClick={() => onAction('custom')}><Icon n="bx-message-dots" /> {t('Custom prompt…')}</div>
        </div>
      )}
    </div>
  )
}
