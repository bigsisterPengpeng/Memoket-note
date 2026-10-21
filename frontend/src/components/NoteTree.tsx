/**
 * Note tree -- modeled on Trilium's tree.
 *
 * A few of its practices, all with reasons, not decoration:
 *
 * · **A folder is not a kind of thing**. A note with children is drawn expandable, without children it is a leaf.
 *   So there is no "New folder" action -- create a note, put things in it, and it naturally
 *   becomes a folder.
 * · **Clones must be visible**. The same note can live in several places in the tree; editing one changes all.
 *   Unmarked, users would think they are two notes, and finding the other one changed too would feel like a ghost.
 * · **Expanded state is stored on the server**. A tree that collapses on every refresh is unusable after a few dozen nodes.
 * · **Row height 2.4em, radius 5px** (from Trilium's tree.css): that height is slack for mouse
 *   drag and drop; squeezed to 1.6em the drop hit rate gets noticeably worse.
 */
import { useEffect, useMemo, useRef, useState } from 'react'

import type { TreeRow } from '../api'
import { ROOT_ID, isFactId, isVirtualId } from '../api'
import { displayTitle } from '../util/displayTitle'
import { dupSuffixes } from '../util/dupTitles'
import { NEUTRAL_ENTITY_ICON } from '../util/entityIcon'
import { sourceIcon, sourceLabel } from '../util/noteSource'
import { fmtDate } from '../util/time'
import Icon from './Icon'
import { t } from '../i18n'

type Props = {
  rows: TreeRow[]
  activeNoteId: string | null
  onOpen: (noteId: string, mods?: { alt: boolean }) => void
  onToggle: (row: TreeRow) => void
  onContextMenu?: (row: TreeRow, at: { x: number; y: number }) => void
  /** Which row (branch id) the context menu is open for: that row is highlighted -- the menu has "Delete (with subtree)", you must see which row it targets */
  menuRowId?: string | null
  /** Keyboard: Delete deletes, F2 renames; the "+" shown on hover creates a child note. Real notes only. */
  onDelete?: (row: TreeRow) => void
  onRename?: (row: TreeRow) => void
  onNewChild?: (row: TreeRow) => void
  /** Drag: drop drag before / after / inside target. Real notes only. */
  onDrop?: (drag: TreeRow, target: TreeRow, where: DropWhere) => void
  /** Files dragged in from the system: dropped on a row = import under it, dropped on blank space = import at the root
   *  (note_tree.ts:584-596: dragged-in files become notes directly). */
  onFilesDrop?: (files: FileList, target: TreeRow | null) => void
  /** Bottom toolbar "Locate current note": scrolls once per +1 (clones mean the same note in several places; users lose track of where they are) */
  locateTick?: number
}

export type DropWhere = 'before' | 'after' | 'over'

/** One icon per node kind (Boxicons). Real notes: leaf = note, with children = folder
 *  (rule from notes.ts:140-143). The knowledge base has moved to its own workspace in the launch bar. */
function iconOf(n: { note_id: string; child_count: number; icon?: string; source?: string }): string {
  const id = n.note_id
  if (n.icon) return n.icon              // the icon the user picked wins (Trilium's NoteIcon)
  if (id === 'kb') return 'bx-brain'
  if (id === 'kb:topics') return 'bx-hash'
  if (id === 'kb:entities') return 'bx-group'
  if (id === 'kb:timeline') return 'bx-calendar'
  if (id === 'kb:recent') return 'bx-time-five'
  if (id === 'kb:graph') return 'bx-network-chart'
  if (id === 'kb:digest') return 'bx-history'
  if (id.startsWith('kb:topic:')) return 'bx-hash'
  if (id.startsWith('kb:etype:')) return 'bx-category'
  // Same for the entity level of the tree: **do not use a person icon when the type is unknown** (see util/entityIcon).
  // Here we only have an id, no name, so always neutral -- the name only exists elsewhere.
  if (id.startsWith('kb:entity:')) return NEUTRAL_ENTITY_ICON
  if (id.startsWith('kb:month:')) return 'bx-calendar'
  if (id.startsWith('kb:unit:')) return 'bx-conversation'
  if (id.startsWith('kb:material:')) return 'bx-conversation'   // multi-segment material: same icon as meetings, not a folder
  if (id.startsWith('kb:fact:')) return 'bx-bulb'
  if (id.startsWith('kb:facts')) return 'bx-table'          // the "N more · see facts table" tail row
  if (id.startsWith('app:')) return 'bx-cog'
  // Imported / machine-generated: a source icon replaces the default note. Folders keep theirs -- with children,
  // "this is a level" matters more than "where this came from" (a writing plan's parent is an ordinary folder).
  if (n.child_count === 0) {
    const from = sourceIcon(n.source)
    if (from) return from
  }
  return n.child_count > 0 ? 'bx-folder' : 'bx-note'
}


type Node = TreeRow & { depth: number }



/** Flatten the branch list by parent/child into "rows to draw", only expanding expanded nodes. */
function flatten(rows: TreeRow[]): Node[] {
  const byParent = new Map<string, TreeRow[]>()
  for (const r of rows) {
    const list = byParent.get(r.parent_note_id)
    if (list) list.push(r)
    else byParent.set(r.parent_note_id, [r])
  }
  for (const list of byParent.values()) {
    list.sort((a, b) => a.position - b.position || a.title.localeCompare(b.title))
  }

  const out: Node[] = []
  // Iterative rather than recursive: tree depth is up to the user, and **if the data ever forms a cycle** (the backend has
  // a guard, but the frontend should not assume it never leaks), recursion blows the stack outright, while iteration with a seen set
  // at worst draws duplicates and the UI stays alive.
  const seen = new Set<string>()
  const walk = (parent: string, depth: number) => {
    for (const row of byParent.get(parent) ?? []) {
      const key = `${row.note_id}@${row.parent_note_id}`
      if (seen.has(key)) continue
      seen.add(key)
      out.push({ ...row, depth })
      if (row.is_expanded && row.child_count > 0) walk(row.note_id, depth + 1)
    }
  }
  walk(ROOT_ID, 0)
  return out
}

export default function NoteTree({
  rows, activeNoteId, onOpen, onToggle, onContextMenu, onDelete, onRename, onNewChild, onDrop, onFilesDrop, locateTick, menuRowId,
}: Props) {
  const hasFiles = (e: React.DragEvent) => !!onFilesDrop && Array.from(e.dataTransfer.types).includes('Files')
  const nodes = useMemo(() => flatten(rows), [rows])

  // Real notes only: revisions once fed knowledge-base virtual nodes in too, where duplicate names are normal,
  // and hanging dates on them means nothing.
  const dup = useMemo(
    () => dupSuffixes(nodes.filter((n) => !isVirtualId(n.note_id))
      .map((n) => ({ key: n.id, title: displayTitle(n), at: n.updated_at }))),
    [nodes])
  const rootRef = useRef<HTMLDivElement>(null)

  // Drag state. The drop position splits the row's y into three: top 25% = before, bottom 25% = after,
  // middle = inside (note_tree.ts:615-623 moveBefore/After/ToParent).
  const [drag, setDrag] = useState<Node | null>(null)
  const [drop, setDrop] = useState<{ id: string; where: DropWhere } | null>(null)
  const expandTimer = useRef<number | null>(null)
  const clearExpandTimer = () => { if (expandTimer.current) { window.clearTimeout(expandTimer.current); expandTimer.current = null } }

  // Which row has keyboard focus (roving tabindex). Defaults to the current note; once the user moves away with arrow keys
  // they go separate ways -- Trilium also has two concepts, "focus" and "active".
  const [focusKey, setFocusKey] = useState<string | null>(null)
  const focused = nodes.find((n) => n.id === focusKey)
    ?? nodes.find((n) => n.note_id === activeNoteId) ?? nodes[0]

  // After switching notes, scroll the active row into the viewport (note_tree.ts:393-397 scrollOfs 100).
  // Clones mean the same note in several places in the tree; scroll to the **first** one.
  useEffect(() => {
    const el = rootRef.current?.querySelector<HTMLElement>('.tree-node.active')
    el?.scrollIntoView({ block: locateTick ? 'center' : 'nearest' })
  }, [activeNoteId, locateTick])

  function onKeyDown(e: React.KeyboardEvent) {
    if (!focused || e.metaKey || e.ctrlKey || e.altKey) return
    const i = nodes.indexOf(focused)
    const go = (n: Node | undefined) => { if (n) { setFocusKey(n.id); e.preventDefault() } }
    switch (e.key) {
      case 'ArrowDown': go(nodes[i + 1]); break
      case 'ArrowUp': go(nodes[i - 1]); break
      case 'ArrowRight':
        e.preventDefault()
        if (focused.child_count > 0 && !focused.is_expanded) onToggle(focused)
        else go(nodes[i + 1]?.depth === focused.depth + 1 ? nodes[i + 1] : undefined)
        break
      case 'ArrowLeft':
        e.preventDefault()
        if (focused.child_count > 0 && focused.is_expanded) onToggle(focused)
        else go(nodes.slice(0, i).reverse().find((n) => n.depth === focused.depth - 1))
        break
      case 'Enter': case ' ': e.preventDefault(); onOpen(focused.note_id); break
      case 'Delete': case 'Backspace':
        if (onDelete && !isVirtualId(focused.note_id)) { e.preventDefault(); onDelete(focused) }
        break
      case 'F2':
        if (onRename && !isVirtualId(focused.note_id)) { e.preventDefault(); onRename(focused) }
        break
      case 'Home': go(nodes[0]); break
      case 'End': go(nodes[nodes.length - 1]); break
    }
  }

  // The focused row also scrolls into view as the keyboard moves it
  useEffect(() => {
    if (!focusKey) return
    rootRef.current?.querySelector<HTMLElement>('.tree-node.focused')?.scrollIntoView({ block: 'nearest' })
  }, [focusKey])

  if (nodes.length === 0) {
    return <p className="muted" style={{ fontSize: 'var(--t-md)', padding: '8px 4px' }}>
      {t('No notes yet. Create one to start.')}
    </p>
  }

  return (
    <div className="note-tree" role="tree" ref={rootRef} tabIndex={0} onKeyDown={onKeyDown}
         onDragOver={(e) => { if (hasFiles(e)) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy' } }}
         onDrop={(e) => { if (hasFiles(e)) { e.preventDefault(); onFilesDrop?.(e.dataTransfer.files, null); setDrop(null) } }}>
      {nodes.map((n) => {
        const active = n.note_id === activeNoteId
        const hasKids = n.child_count > 0
        const virtual = isVirtualId(n.note_id)
        return (
          <div
            key={n.id}
            role="treeitem"
            aria-expanded={hasKids ? n.is_expanded : undefined}
            aria-selected={active}
            className={'tree-node' + (active ? ' active' : '') + (focused?.id === n.id ? ' focused' : '') + (menuRowId === n.id ? ' ctx-target' : '')
              + (drag?.id === n.id ? ' dragging' : '') + (drop?.id === n.id ? ' drop-' + drop.where : '')}
            // 10px per level, root indented another 12px (theme-next/shell.css:716-723)
            style={{ paddingInlineStart: 12 + n.depth * 10 }}
            onClick={(e) => { setFocusKey(n.id); onOpen(n.note_id, { alt: e.altKey }) }}
            draggable={!!onDrop && !virtual}
            onDragStart={(e) => {
              setDrag(n); e.dataTransfer.effectAllowed = 'move'
              e.dataTransfer.setData('text/plain', n.note_id)
            }}
            onDragOver={(e) => {
              if (hasFiles(e) && !virtual) {          // files: always into this row
                e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect = 'copy'
                if (drop?.id !== n.id) setDrop({ id: n.id, where: 'over' })
                return
              }
              if (!drag || virtual || drag.id === n.id) return
              e.preventDefault()
              const r = e.currentTarget.getBoundingClientRect()
              const y = (e.clientY - r.top) / r.height
              const where: DropWhere = y < .25 ? 'before' : y > .75 ? 'after' : 'over'
              if (drop?.id !== n.id || drop.where !== where) {
                setDrop({ id: n.id, where })
                // Auto-expand after hovering 600ms (fancytree dnd5's autoExpandMS)
                clearExpandTimer()
                if (where === 'over' && hasKids && !n.is_expanded)
                  expandTimer.current = window.setTimeout(() => onToggle(n), 600)
              }
            }}
            onDragLeave={() => { if (drop?.id === n.id) { setDrop(null); clearExpandTimer() } }}
            onDrop={(e) => {
              e.preventDefault()
              if (hasFiles(e)) {
                e.stopPropagation()
                if (!virtual) onFilesDrop?.(e.dataTransfer.files, n)
                setDrop(null); return
              }
              if (drag && drop && drop.id === n.id && drag.id !== n.id) onDrop?.(drag, n, drop.where)
              setDrag(null); setDrop(null); clearExpandTimer()
            }}
            onDragEnd={() => { setDrag(null); setDrop(null); clearExpandTimer() }}
            onContextMenu={(e) => {
              if (!onContextMenu) return
              e.preventDefault()
              setFocusKey(n.id)
              onContextMenu(n, { x: e.clientX, y: e.clientY })
            }}
            // Only show a tooltip when the text is really truncated (note_tree.ts:329-353),
            // otherwise a popup on every row is annoying
            onMouseEnter={(e) => {
              const title = e.currentTarget.querySelector<HTMLElement>('.tree-title')
              if (title && title.scrollWidth > title.clientWidth) e.currentTarget.title = title.textContent ?? ''
              else e.currentTarget.removeAttribute('title')
            }}
          >
            <span
              className={'tree-expander' + (hasKids ? '' : ' leaf')}
              onClick={(e) => { e.stopPropagation(); if (hasKids) onToggle(n) }}
              aria-hidden={!hasKids}
            >
              {hasKids && <Icon n={(n.is_expanded ? 'bx-chevron-down' : 'bx-chevron-right')} />}
            </span>
            {/* Icon: real notes leaf = document / with children = folder (notes.ts:140-143);
                knowledge-base virtual nodes fact ◆ / category ▤. */}
            <span className="tree-icon" aria-hidden={!sourceLabel(n.source)}
                  title={sourceLabel(n.source) || undefined}><Icon n={iconOf(n)} /></span>
            {}
            <span className="tree-title" title={displayTitle(n) + (n.updated_at ? '\n' + t('Modified {date}', { date: fmtDate(n.updated_at) }) : '')}>{displayTitle(n)}</span>
            {dup.has(n.id) && <span className="tree-dup-date">· {dup.get(n.id)}</span>}
            <span className="tree-gap" />
            {n.fact_count > 0 && !isFactId(n.note_id) && (
              <span className="tree-badge" title={t('{n} facts', { n: n.fact_count })}>{n.fact_count}</span>
            )}
            {/* The link to the knowledge base, visible right in the tree (docs/kb-fusion-design.md).
                Tell at a glance "grounded" from "still just a draft". */}
            {n.ingested_at && (
              // Edited after ingest (updated_at newer than ingested_at): yellow ⇡, the knowledge base still has the old version
              n.updated_at > n.ingested_at
                ? <span className="tree-badge ingested stale"
                        title={t('Ingested ({date}) but edited since; the knowledge base still has the old version — sync in the Citations tab', { date: fmtDate(n.ingested_at) })}>⇡</span>
                : <span className="tree-badge ingested"
                        title={t('Saved to knowledge base ({date})', { date: fmtDate(n.ingested_at) })}>⇡</span>
            )}
            {n.cite_count > 0 && (
              <span className="tree-badge cited"
                    title={t('Cites {n} knowledge base records', { n: n.cite_count })}>◆{n.cite_count}</span>
            )}
            {n.branch_count > 1 && (
              // Clone marker. The user must know editing here changes the other places too.
              <span className="tree-badge" title={t('This note lives in {n} places', { n: n.branch_count })}>
                ⧉
              </span>
            )}
            {hasKids && !virtual && <span className="tree-count">{n.child_count}</span>}
            {/* "+ New child note", shown only on hover. Creating notes is the most frequent action; hiding it in the context menu
                costs too much (note_tree.ts:1875-1941 add-note-button). */}
            {onNewChild && !virtual && (
              <button className="tree-item-button" title={t('New child note')}
                      onClick={(e) => { e.stopPropagation(); onNewChild(n) }}><Icon n="bx-plus" /></button>
            )}
          </div>
        )
      })}
    </div>
  )
}

export { flatten as flattenTreeForTest }
