import { useEffect } from 'react'
import { useRestoreFocus } from '../util/restoreFocus'
import { SHORTCUT_GROUPS } from '../shortcuts'
import { fmtShortcut } from '../util/keys'
import Icon from './Icon'
import { t } from '../i18n'

/** The keyboard shortcut list opened by ⌘/ (a read-only version of Trilium's Options → Shortcuts table). */
export default function ShortcutsPanel({ onClose }: { onClose: () => void }) {
  // Esc closes it (capture phase, so the editor does not swallow it first)
  useRestoreFocus()
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onClose])
  return (
    <div className="palette-backdrop" onClick={onClose}>
      <div className="palette shortcuts" role="dialog" aria-label={t('Shortcuts')} onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ justifyContent: 'space-between', padding: '14px 16px 6px' }}>
          <h3 style={{ margin: 0 }}><Icon n="bx-command" /> {t('Shortcuts')}</h3>
          <button className="icon-btn" title={t('Close (Esc)')} onClick={onClose}><Icon n="bx-x" /></button>
        </div>
        <div className="palette-results shortcuts-body">
          {SHORTCUT_GROUPS.map((g) => (
            <section key={g.title}>
              <p className="muted palette-group">{t(g.title)}</p>
              {g.items.map((it) => (
                <div key={it.keys} className="shortcut-row">
                  <kbd>{fmtShortcut(t(it.keys))}</kbd><span>{t(it.what)}</span>
                </div>
              ))}
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}
