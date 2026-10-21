
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useRestoreFocus } from '../util/restoreFocus'
import { fmtShortcut } from '../util/keys'
import Icon from './Icon'

export type MenuItem =
  | { kind: 'sep' }
  | { kind: 'header'; label: string }
  | {
      kind?: 'item'
      label: string
      icon?: string
      hint?: string          // description on the right (says why when disabled)
      shortcut?: string      // keyboard shortcut, <kbd> style
      danger?: boolean
      disabled?: boolean
      onSelect: () => void
    }

export type MenuAt = { x: number; y: number }

/** The clickable kind (not a separator, not a subheading). */
export type MenuAction = Extract<MenuItem, { onSelect: () => void }>


export function selectableItem(it: MenuItem | undefined): it is MenuAction {
  return !!it && it.kind !== 'sep' && it.kind !== 'header' && !it.disabled
}

/** Remove consecutive, leading and trailing separators. */
export function tidyMenu(items: MenuItem[]): MenuItem[] {
  const out: MenuItem[] = []
  for (const it of items) {
    const sep = 'kind' in it && it.kind === 'sep'
    const prevSep = out.length === 0 || out[out.length - 1].kind === 'sep'
    if (sep && prevSep) continue
    out.push(it)
  }
  while (out.length && out[out.length - 1].kind === 'sep') out.pop()
  return out
}

export default function ContextMenu({
  at, items, onClose,
}: { at: MenuAt; items: MenuItem[]; onClose: () => void }) {
  useRestoreFocus()   // after closing, focus returns to where it was before opening (editor / tree row)
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<MenuAt>(at)
  const [hi, setHi] = useState(-1)
  const list = tidyMenu(items)

  // Render in place first, then measure — the number of items varies, so height can only be measured, not computed.
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const { width, height } = el.getBoundingClientRect()
    const pad = 5
    setPos({
      x: Math.max(pad, Math.min(at.x, window.innerWidth - width - pad)),
      // A menu taller than the window (a list of 50 tabs): pin to the top and scroll internally via CSS max-height; don't push the head off the window
      y: Math.max(pad, Math.min(at.y, window.innerHeight - height - pad)),
    })
  }, [at.x, at.y, list.length])

  // Scroll the highlighted item into view: when the menu is taller than the window it scrolls internally (a list of 50 tabs); ↑↓ moving out of sight must scroll along
  useEffect(() => {
    if (hi < 0) return
    const el = ref.current?.querySelector('.context-menu-item.hi') as HTMLElement | null
    el?.scrollIntoView({ block: 'nearest' })
  }, [hi])

  useEffect(() => {
    const selectable = (k: number) => selectableItem(list[k])
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); return }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const step = e.key === 'ArrowDown' ? 1 : -1
        let k = hi
        for (let n = 0; n < list.length; n++) {
          k = (k + step + list.length) % list.length
          if (selectable(k)) { setHi(k); break }
        }
      } else if (e.key === 'Enter') {
        const it = list[hi]
        if (!selectableItem(it)) return
        e.preventDefault(); onClose(); it.onSelect()
      }
    }
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose()
    }
    window.addEventListener('keydown', onKey)
    // capture: the item's own onClick runs first, then this closes the menu
    window.addEventListener('mousedown', onDown, true)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onDown, true)
    }
  }, [onClose, hi, list])

  return createPortal((
    <div
      ref={ref}
      className="context-menu"
      role="menu"
      style={{ left: pos.x, top: pos.y }}
    >
      {list.map((it, i) => {
        if ('kind' in it && it.kind === 'sep') return <div key={i} className="context-menu-sep" />
        if ('kind' in it && it.kind === 'header') return <div key={i} className="context-menu-header">{it.label}</div>
        const item = it as Extract<MenuItem, { label: string; onSelect: () => void }>
        return (
          <button
            key={i}
            role="menuitem"
            className={'context-menu-item' + (item.danger ? ' danger' : '') + (hi === i ? ' hi' : '')}
            disabled={item.disabled}
            onMouseEnter={() => setHi(i)}
            onClick={() => { onClose(); item.onSelect() }}
          >
            <span className="cm-icon">{item.icon?.startsWith('bx-') ? <Icon n={item.icon} /> : (item.icon ?? '')}</span>
            <span className="cm-label">{item.label}</span>
            {/* The hint shows on one line only (CSS ellipsis), full text goes into title — a menu needs to be scannable */}
            {item.hint && <span className="cm-hint" title={item.hint}>{item.hint}</span>}
            {item.shortcut && <kbd className="cm-kbd">{fmtShortcut(item.shortcut)}</kbd>}
          </button>
        )
      })}
    </div>
  ), document.body)
}
