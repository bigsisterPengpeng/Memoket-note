/**
 * Right pane -- tabs only (as in Trilium). "Memory" is the default tab.
 *
 * **Why related memory stays resident instead of being another tab** (a deliberate divergence from
 * Trilium; the reason is docs/product-north-star.md criterion 2):
 *
 *   > While writing a report I wanted an old note; by the time I found it, read it and came back, I forgot what point it was supposed to support.
 *
 * Clicking a tab does not leave the page, but it is an **active retrieval action** -- the user first has to think
 * "I should look that up". Recall that surfaces while you write is **passive**: it is there before you need it.
 * The two cost attention differently, and this product is defined as "keeping attention".
 *
 * The tab area below copies two Trilium practices:
 * · `alwaysShown`: stays on the strip even without content, otherwise the strip reshapes itself when switching notes
 *   and whatever is under the mouse moves away
 * · tabs with content get a badge, so you know something is inside without opening it
 *
 * **Explicitly not copying its SidebarChat.** That is a chat box, exactly what criterion 1 wants gone.
 * Our "Runs" shows what the harness did and judged each round -- an execution record, not a conversation.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { t } from '../i18n'


export const RIGHT_TAB_KEY = 'memoket.rightTab'
import { fmtShortcut } from '../util/keys'
import Icon from './Icon'

export type PaneTab = {
  id: string
  title: string
  icon?: string          // Boxicons class name
  badge?: string | number
  /** Stays on the tab strip even without content. See "the strip reshapes itself" in the comment above. */
  alwaysShown?: boolean
  hasContent?: boolean
  /** When hasContent is false the content area says why it is empty, instead of staying blank. */
  emptyHint?: string
  body: ReactNode
}

export default function RightPane({
  tabs, defaultTab, onCollapse, focusTab,
}: { tabs: PaneTab[]; defaultTab: string; onCollapse?: () => void
     /** An external request to switch to some tab (a harness run switches to "Plan"). Switches once per change. */
     focusTab?: { id: string; n: number } }) {
  const shown = tabs.filter((t) => t.alwaysShown || t.hasContent !== false)

  // (same storage as appearance, `memoket.` prefix). If the remembered tab has no content this time, fall back to the first one; `current` below covers it.
  const [active, setActiveState] = useState(() => { try { return localStorage.getItem(RIGHT_TAB_KEY) || defaultTab } catch { return defaultTab } })
  const setActive = (id: string) => { setActiveState(id); try { localStorage.setItem(RIGHT_TAB_KEY, id) } catch { /* private window etc.: works without storing */ } }
  useEffect(() => { if (focusTab) setActive(focusTab.id) }, [focusTab])
  const current = shown.find((t) => t.id === active) ?? shown[0]

  return (
    <>
      <div className="right-pane-tabs" role="tablist">
        {shown.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={current?.id === t.id}
            className={'pane-tab' + (current?.id === t.id ? ' active' : '')}
            onClick={() => setActive(t.id)}
          >
            {t.icon && <Icon n={t.icon} />}
            {t.title}
            {t.badge !== undefined && t.badge !== 0 && (
              <span className="pane-tab-badge">{t.badge}</span>
            )}
          </button>
        ))}
        {/* Right-end action area: fully clickable at any width (RightPanelContainer.css:110-145) */}
        {onCollapse && (
          <span className="right-pane-actions">
            <button className="icon-btn" title={t('Collapse right pane ({key})', { key: fmtShortcut('⇧⌘\\') })} onClick={onCollapse}><Icon n="bx-chevrons-right" /></button>
          </span>
        )}
      </div>
      <div className="right-pane-body" role="tabpanel">
        {current?.hasContent === false
          ? <p className="muted" style={{ fontSize: 'var(--t-sm)' }}>{current.emptyHint ? t(current.emptyHint) : t('This note has nothing here yet.')}</p>
          : current?.body}
      </div>
    </>
  )
}
