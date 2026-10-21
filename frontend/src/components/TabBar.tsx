/**
 * The tab row -- modeled on Trilium's tab_row.
 *
 * Sizes are taken from it (tab_row.ts): a single tab is 100-240px; with many tabs it shrinks in three steps 84 / 60 / 48,
 * and the new-tab button is 36px. These numbers are not guesses -- at 48px a tab only has room for
 * an icon, any narrower and it cannot be clicked accurately.
 *
 * **Why this product needs multiple tabs**: pain point 10 "notes are scattered across Feishu and Notion; to write across
 * both I first have to remember what each is called", and the most common action while writing -- writing against another
 * note. A single-note editor forces the user to keep the other note's content in their head, which is exactly the attention
 * criterion 2 is meant to save.
 */
import { useEffect, useRef, useState } from 'react'
import { fmtShortcut } from '../util/keys'
import Icon from './Icon'
import { t } from '../i18n'

export type Tab = { id: string; noteId: string; title: string }

const MAX_W = 240
/** Trilium's three steps: TAB_SIZE_SMALL 84 / SMALLER 60 / MINI 48. Our floor is
 *  84 -- it covers the two narrower steps with scroll buttons, we cover them with a horizontally scrollable strip; same effect. */
const MIN_W = 84
const MARGIN_W = 5

export default function TabBar({
  tabs, activeId, onSelect, onClose, onNew, onContextMenu, onReorder, iconOf, onListTabs, busyIds, menuTabId,
}: {
  tabs: Tab[]
  activeId: string | null
  /** A tab's note icon (only if the user picked one; Trilium's tabs carry NoteIcon too). Not part of the Tab model -- that goes to localStorage, and a changed icon would keep the old value */
  iconOf?: (noteId: string) => string | undefined
  onSelect: (id: string) => void
  onClose: (id: string) => void
  onNew: () => void
  onContextMenu?: (tab: Tab, at: { x: number; y: number }) => void
  /** Drag to reorder: move id to position index */
  onReorder?: (id: string, index: number) => void
  /** When they do not fit, an extra ▾ lists every tab (Chrome's tab search / VS Code's "Open Editors"). With 50 tabs, scrolling ◀ ▶ one step at a time finds nothing */
  onListTabs?: (at: { x: number; y: number }) => void
  /** Notes the harness is currently writing: a color bar on top of the tab. When you switch to another tab it is the only place showing "still running, and which note" */
  busyIds?: Set<string>
  /** Which tab the context menu is open for: highlight it (Trilium's tab_row does the same on right click) */
  menuTabId?: string | null
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [dragId, setDragId] = useState<string | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)

  // Shrink proportionally when there are too many tabs. Width is computed here rather than left to flex to guarantee
  // every tab is **at least** recognizable as a tab (Trilium's floor is 48px).
  // Scroll the active tab into view: with a dozen tabs, the one reached by ⌘9 / back may be out of sight
  useEffect(() => {
    if (!activeId) return
    const el = ref.current?.querySelector('.note-tab.active') as HTMLElement | null
    el?.scrollIntoView({ inline: 'nearest', block: 'nearest' })
  }, [activeId, tabs.length])

  // Show two scroll buttons when they do not fit (Trilium tab_row.ts:19x: each scroll is ±210px) -- horizontal wheel scrolling alone
  // is undiscoverable, and with a dozen tabs the rightmost one stays hidden forever
  const [overflow, setOverflow] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const check = () => setOverflow(el.scrollWidth > el.clientWidth + 2)
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    return () => ro.disconnect()
  }, [tabs.length])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    // Available width is the strip's parent (the tab row) minus the left/right spacer / filler / +;
    // gaps are subtracted as (n-1)*5 per tab_row.ts:536-538.
    const parent = el.parentElement
    const avail = (parent?.clientWidth ?? el.clientWidth) - 36 - 50 - 72 - (tabs.length - 1) * MARGIN_W
    const each = Math.floor(avail / Math.max(1, tabs.length))
    const w = Math.max(MIN_W, Math.min(each, MAX_W))
    el.style.setProperty('--tab-w', `${w}px`)

    el.dataset.size = w <= 84 ? 'small' : w < 120 ? 'narrow' : ''
  }, [tabs.length])

  return (
    <>
    {overflow && <button className="tab-scroll" title={t('Scroll left')} onClick={() => { if (ref.current) ref.current.scrollBy({ left: -210, behavior: 'smooth' }) }}><Icon n="bx-chevron-left" /></button>}
    <div className="tab-strip" ref={ref} role="tablist"
         // Turn vertical wheel scrolling into horizontal: the strip is horizontal, the user's wheel is vertical (tab_row.ts:424-466)
         onWheel={(e) => { if (e.deltaY && ref.current) ref.current.scrollLeft += e.deltaY }}>
      {tabs.map((tab, i) => (
        <div
          key={tab.id}
          role="tab"
          aria-selected={tab.id === activeId}
          className={'note-tab' + (tab.id === activeId ? ' active' : '') + (busyIds?.has(tab.noteId) ? ' busy' : '') + (menuTabId === tab.id ? ' ctx-target' : '')
            + (dragId === tab.id ? ' dragging' : '') + (overIndex === i && dragId !== tab.id ? ' drop-before' : '')}
          title={`${tab.title || t('Untitled')}${busyIds?.has(tab.noteId) ? t(' (writing)') : ''}${i < 9 ? `  ${fmtShortcut('⌘' + (i + 1))}` : ''}`}
          onClick={() => onSelect(tab.id)}
          // Drag to reorder within the row (Trilium uses Draggabilly; HTML5 dnd is enough)
          draggable={!!onReorder}
          onDragStart={(e) => { setDragId(tab.id); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', tab.id) }}
          onDragOver={(e) => {
            if (!dragId) return
            e.preventDefault()
            const r = e.currentTarget.getBoundingClientRect()
            setOverIndex(e.clientX < r.left + r.width / 2 ? i : i + 1)
          }}
          onDrop={(e) => {
            e.preventDefault()
            if (dragId && overIndex !== null) onReorder?.(dragId, overIndex)
            setDragId(null); setOverIndex(null)
          }}
          onDragEnd={() => { setDragId(null); setOverIndex(null) }}
          // Middle-click closes: a universal browser habit, Trilium has it too. Without it, closing a pile of
          // tabs means aiming at that tiny × one by one.
          onAuxClick={(e) => { if (e.button === 1) { e.preventDefault(); onClose(tab.id) } }}
          onContextMenu={(e) => {
            if (!onContextMenu) return
            e.preventDefault()
            onContextMenu(tab, { x: e.clientX, y: e.clientY })
          }}
        >
          {iconOf?.(tab.noteId) && <Icon n={iconOf(tab.noteId)!} className="note-tab-icon" />}
          <span className="note-tab-title">{tab.title || t('Untitled')}</span>
          <span
            className="note-tab-close"
            aria-label={t('Close')}
            onClick={(e) => { e.stopPropagation(); onClose(tab.id) }}
          >
            ×
          </span>
        </div>
      ))}
    </div>
    {overflow && <button className="tab-scroll" title={t('Scroll right')} onClick={() => { if (ref.current) ref.current.scrollBy({ left: 210, behavior: 'smooth' }) }}><Icon n="bx-chevron-right" /></button>}
    {overflow && onListTabs && (
      <button className="tab-scroll tab-list" title={t('List all {n} tabs', { n: tabs.length })}
              onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); onListTabs({ x: r.left, y: r.bottom + 2 }) }}>
        <Icon n="bx-chevron-down" />
      </button>
    )}
    <button className="note-new-tab" onClick={onNew} title={t('New note ({key})', { key: fmtShortcut('⌘T') })}><span><Icon n="bx-plus" /></span></button>
    {/* Double-click empty space in the tab row to open a new tab (browser convention) */}
    <div className="tab-row-filler" onDoubleClick={onNew} />
    </>
  )
}
