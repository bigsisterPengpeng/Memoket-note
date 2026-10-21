/**
 * Ribbon -- the collapsible tab strip under the title, holding **this note's metadata**.
 *
 * Modeled on Trilium's ribbon (basic properties, note paths, attachments...). The first thing we put in
 * is the **writing outline**, for the reason in docs/product-north-star.md criterion 3:
 *
 *   > High automation = plans itself, executes itself, checks the result.
 *   > So **the plan must be visible**.
 *
 * The outline is this automation's plan -- it belongs in the note's metadata area, seen together with the body, not in
 * some right-pane panel you have to switch to. Hide the plan and the user only sees a spinning
 * indicator, which says nothing at all.
 *
 * One detail copied from it: **the strip does not disappear just because the current note has no content** (Trilium's
 * `alwaysShown`). If it disappeared, the whole strip would reshape itself when switching notes, and whatever is under the mouse
 * would move away.
 */
import { useEffect, useState, type ReactNode } from 'react'

import ContextMenu, { type MenuAt, type MenuItem } from './ContextMenu'
import Icon from './Icon'
import { t } from '../i18n'

export type RibbonTab = {
  id: string
  title: string
  icon?: string
  /** A badge when there is content, so the user knows something is inside without opening it */
  badge?: string | number
  /** Whether to auto-expand when switching notes. Per Trilium Ribbon.tsx:46-51: expand the first tab whose activate
   *  is true, collapse only if none is. When the writing outline has content it **must** expand -- criterion 3
   *  says the plan must be visible, and a collapsed plan is no different from a spinner. */
  activate?: boolean
  body: ReactNode
}

/** Which tab was open last (`''` = the user collapsed it themselves).
 *  **Not remembered per note**: "do I want to see the toolbar" is a personal habit, not a property of a note.
 *  localStorage throws in private mode / with site data disabled, so both reads and writes are guarded. */
const REMEMBER_KEY = 'ribbon-open'
const remembered = (): string | undefined => {
  try { return localStorage.getItem(REMEMBER_KEY) || undefined } catch { return undefined }
}
const remember = (id: string | undefined) => {
  try { localStorage.setItem(REMEMBER_KEY, id ?? '') } catch { /* cannot store: just not remembered this time */ }
}

export default function Ribbon({
  tabs, defaultOpen, noteKey, actions,
}: { tabs: RibbonTab[]; defaultOpen?: string; noteKey?: string; actions?: MenuItem[] }) {
  // The three-dot menu at the right end (Trilium NoteActions): low-frequency odds and ends like export / copy / focus mode
  // go in here, so they do not compete for attention on the same row as magic tap / Smart Continue (the flip side of criterion 1)
  const [menuAt, setMenuAt] = useState<MenuAt | null>(null)
  // undefined = collapsed. Collapsed is the default: the body is the star, metadata is expanded when needed.
  const [open, setOpen] = useState<string | undefined>(defaultOpen ?? remembered())

  // Recompute by the activate rule when switching notes; within the same note leave the user's manual collapse/expand alone.
  const activateId = tabs.find((t) => t.activate)?.id
  useEffect(() => {
    setOpen(defaultOpen ?? activateId ?? remembered())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [noteKey, defaultOpen, activateId === undefined])


  const choose = (id: string | undefined) => { setOpen(id); remember(id) }

  if (tabs.length === 0) return null

  return (
    <div className="ribbon">
      <div className="ribbon-strip" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={open === t.id}
            className={'ribbon-tab' + (open === t.id ? ' active' : '')}
            onClick={() => choose(open === t.id ? undefined : t.id)}
          >
            {t.icon && <span className="ribbon-icon">{t.icon.startsWith('bx-') ? <Icon n={t.icon} /> : t.icon}</span>}
            <span>{t.title}</span>
            {t.badge !== undefined && t.badge !== 0 && (
              <span className="ribbon-badge">{t.badge}</span>
            )}
          </button>
        ))}
        {actions && actions.length > 0 && (
          <button className="ribbon-actions" title={t('More actions')} aria-label={t('More actions')} aria-haspopup="menu"
                  onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setMenuAt({ x: r.right - 200, y: r.bottom + 4 }) }}>
            <Icon n="bx-dots-horizontal-rounded" />
          </button>
        )}
        {menuAt && actions && <ContextMenu at={menuAt} items={actions} onClose={() => setMenuAt(null)} />}
      </div>
      {open && (
        <div className="ribbon-body" role="tabpanel">
          {tabs.find((t) => t.id === open)?.body}
        </div>
      )}
    </div>
  )
}
