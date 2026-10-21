/**
 * Small in-app dialogs — replacing `window.prompt`.
 *
 * Why prompt can't stay: in Electron it's a **system-level modal**, its styling entirely outside
 * theme control; and the "Move to…" prompt flattened the whole tree into a numbered list for users to type an index,
 * which grows unscrollable past a hundred notes. Trilium's counterparts are `dialogs/{item_picker,
 * move_to, clone_to, branch_prefix}.tsx` — pickers with search.
 */
import { useEffect, useMemo, useRef, useState } from 'react'

import { ROOT_ID, isVirtualId, type TreeRow } from '../api'
import { displayTitle } from '../util/displayTitle'
import { useRestoreFocus } from '../util/restoreFocus'
import { t } from '../i18n'

// ------------------------------------------------------------ pick a node

export type PickerRequest = {
  title: string
  /** Not selectable (itself and its subtree — choosing them would form a cycle) */
  exclude: Set<string>
  /** The few put first (the current note, the level it's in). **A hint, not a decision made for you** —
   *  they still need a click to be selected. See the comment on App.openWritingPlan. */
  first?: string[]
  resolve: (noteId: string | null) => void
}

export function NotePicker({ req, rows }: { req: PickerRequest; rows: TreeRow[] }) {
  const [q, setQ] = useState('')
  const [i, setI] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  useRestoreFocus()
  useEffect(() => { input.current?.focus() }, [])

  // Paths help users recognize locations: after cloning, same-named notes appear in several places; titles alone can't tell them apart
  const paths = useMemo(() => {
    const byId = new Map<string, TreeRow>()
    for (const r of rows) if (!byId.has(r.note_id)) byId.set(r.note_id, r)
    const of = (r: TreeRow): string => {
      const parts: string[] = []
      let cur: TreeRow | undefined = byId.get(r.parent_note_id)
      let guard = 0
      while (cur && guard++ < 50) { parts.unshift(displayTitle(cur)); cur = byId.get(cur.parent_note_id) }
      return parts.join(' / ')
    }
    return new Map(rows.map((r) => [r.id, of(r)]))
  }, [rows])

  const items = useMemo(() => {
    const seen = new Set<string>()
    const list = rows.filter((r) => !isVirtualId(r.note_id) && !req.exclude.has(r.note_id)
      && !seen.has(r.note_id) && seen.add(r.note_id))
    const needle = q.trim().toLowerCase()
    const hit = needle
      ? list.filter((r) => (displayTitle(r) + ' ' + (paths.get(r.id) ?? '')).toLowerCase().includes(needle))
      : list
    // "Move to…" / "Clone to…" can choose the tree root, "which note should infinite continue write under" can't —
    // the caller puts ROOT_ID into exclude and it won't appear. It used to be unconditionally first and

    const root = req.exclude.has(ROOT_ID)
      ? [] : [{ id: 'root', note_id: ROOT_ID, label: t('(root)'), path: '' }]
    // The ones the caller asked to put first (deduplicated, keeping the given order)
    const want = req.first ?? []
    const rank = (r: TreeRow) => { const k = want.indexOf(r.note_id); return k < 0 ? want.length : k }
    const ordered = want.length ? [...hit].sort((a, b) => rank(a) - rank(b)) : hit
    return [...root,
            ...ordered.slice(0, 200).map((r) => ({ id: r.id, note_id: r.note_id, label: displayTitle(r), path: paths.get(r.id) ?? '' }))]
  }, [rows, q, req.exclude, req.first, paths])

  const choose = (k: number) => { const it = items[k]; if (it) req.resolve(it.note_id) }

  const listRef = useRef<HTMLDivElement>(null)
  useEffect(() => { (listRef.current?.querySelector('.palette-item.active') as HTMLElement | null)?.scrollIntoView({ block: 'nearest' }) }, [i])

  return (
    <div className="palette-backdrop" onMouseDown={() => req.resolve(null)}>
      <div className="palette" role="dialog" onMouseDown={(e) => e.stopPropagation()}>
        <div className="muted" style={{ fontSize: 'var(--t-sm)', padding: '2px 4px 6px' }}>{req.title}</div>
        <input aria-label={t('Search title or path')}
          ref={input} value={q} placeholder={t('Search title or path…')}
          onChange={(e) => { setQ(e.target.value); setI(0) }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setI((v) => Math.min(v + 1, items.length - 1)) }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setI((v) => Math.max(v - 1, 0)) }
            else if (e.key === 'Enter') { e.preventDefault(); choose(i) }
            else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); req.resolve(null) }
          }}
        />
        <div className="palette-results" ref={listRef}>
          {items.map((it, k) => (
            <div key={it.id} className={'palette-item' + (k === i ? ' active' : '')}
                 onMouseEnter={() => setI(k)} onClick={() => choose(k)} title={it.path ? `${it.label} · ${it.path}` : it.label}>
              {}
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0, flex: '0 1 auto' }}>{it.label}</span>
              {it.path && <span className="muted" style={{ marginInlineStart: 8, fontSize: 'var(--t-sm)', flex: 'none' }}>{it.path}</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ------------------------------------------------------------ type a line

export type PromptRequest = {
  title: string
  initial: string
  resolve: (value: string | null) => void
}

export function TextPrompt({ req }: { req: PromptRequest }) {
  const [v, setV] = useState(req.initial)
  const input = useRef<HTMLInputElement>(null)
  useRestoreFocus()
  useEffect(() => { input.current?.focus(); input.current?.select() }, [])
  return (
    <div className="palette-backdrop" onMouseDown={() => req.resolve(null)}>
      <div className="dialog" role="dialog" onMouseDown={(e) => e.stopPropagation()}>
        <div className="dialog-title">{req.title}</div>
        <input
          ref={input} value={v} onChange={(e) => setV(e.target.value)} aria-label={req.title}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); req.resolve(v) }
            else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); req.resolve(null) }
          }}
        />
        <div className="dialog-actions">
          <button onClick={() => req.resolve(null)}>{t('Cancel')}</button>
          <button className="primary" onClick={() => req.resolve(v)}>{t('OK')}</button>
        </div>
      </div>
    </div>
  )
}


// ------------------------------------------------------------ confirm

export type ConfirmRequest = {
  title: string
  detail?: string
  okLabel?: string
  danger?: boolean
  resolve: (ok: boolean) => void
}

/** Only for actions whose **consequences aren't visible** (deleting a subtree takes invisible things with it). Single-note
 *  deletion uses optimistic delete + undo, which beats a confirm dialog — don't overuse this. */
export function ConfirmDialog({ req }: { req: ConfirmRequest }) {
  const btn = useRef<HTMLButtonElement>(null)
  const cancel = useRef<HTMLButtonElement>(null)
  // Dangerous operations (deleting a whole subtree) put default focus on "Cancel": a casual Enter shouldn't delete dozens of notes.
  // Ordinary confirmations give focus to the OK button.
  useRestoreFocus()
  useEffect(() => { (req.danger ? cancel : btn).current?.focus() }, [req.danger])
  return (
    <div className="palette-backdrop" onMouseDown={() => req.resolve(false)}>
      <div className="dialog" role="alertdialog" onMouseDown={(e) => e.stopPropagation()}
           onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); req.resolve(false) } }}>
        <div className="dialog-title">{req.title}</div>
        {req.detail && <div className="dialog-detail">{req.detail}</div>}
        <div className="dialog-actions">
          <button ref={cancel} onClick={() => req.resolve(false)}>{t('Cancel')}</button>
          <button ref={btn} className="primary" style={req.danger ? { background: 'var(--del)', borderColor: 'var(--del)' } : undefined}
                  onClick={() => req.resolve(true)}>{req.okLabel ?? t('OK')}</button>
        </div>
      </div>
    </div>
  )
}
