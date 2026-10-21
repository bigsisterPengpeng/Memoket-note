import React, { useEffect, useRef, useState } from 'react'
import * as api from '../api'
import type { Fact, NoteBrief } from '../api'
import { DESTINATIONS, paletteLabel } from '../util/destinations'
import { displayTitle } from '../util/displayTitle'
import { JOURNEY_SPAN_DAYS, openJourneySpan } from '../util/journeyOpen'
import { fmtDate } from '../util/time'
import Highlight from './Highlight'
import Icon from './Icon'
import { t } from '../i18n'


export const COMMANDS: { label: string; icon: string; run: () => void }[] = [
  // Labels are data (module-level constants), translated at display via `t(c.label)`; each row below is marked i18n-ignore
  { label: 'New note', icon: 'bx-plus', run: () => window.dispatchEvent(new CustomEvent('new-note')) },
  { label: 'Today’s journal', icon: 'bx-calendar-event', run: () => window.dispatchEvent(new CustomEvent('open-today')) },
  { label: 'Topic map', icon: 'bx-network-chart', run: () => window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:graph' })) },
  { label: 'Timeline', icon: 'bx-calendar', run: () => window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:timeline' })) },
  ...DESTINATIONS.map((d) => ({
    label: paletteLabel(d), icon: d.icon,
    run: () => window.dispatchEvent(new CustomEvent('open-virtual', { detail: d.id })),
  })),

  // that review is a model call, and picking a command in ⌘K is just "type two letters + Enter" with no second confirmation,
  // while its "Stop" is on that page. So this takes people to the "Review a period" block and highlights "Last 7 days";
  // whether to press it is the user's call — full rationale on `util/journeyOpen.openJourneySpan`.
  { label: `This week’s screen activity (review of the last ${JOURNEY_SPAN_DAYS} days)`, icon: 'bx-calendar',
    run: () => openJourneySpan() },
  { label: 'Change icon (current note)', icon: 'bx-smile', run: () => window.dispatchEvent(new CustomEvent('open-icon-picker')) },
  { label: 'Locate current note (in tree)', icon: 'bx-crosshair', run: () => window.dispatchEvent(new CustomEvent('tree-locate')) },
  { label: 'Collapse the whole tree', icon: 'bx-collapse-vertical', run: () => window.dispatchEvent(new CustomEvent('tree-collapse')) },
  { label: 'Shortcuts', icon: 'bx-command', run: () => window.dispatchEvent(new CustomEvent('show-shortcuts')) },
  { label: 'Export all notes (Markdown zip)', icon: 'bx-export', run: () => window.dispatchEvent(new CustomEvent('export-all')) },

  // This entry is a **deep link**, not a destination: it opens a block inside the import page, so it doesn't go through DESTINATIONS.
  { label: 'Export back to Obsidian / Notion / Feishu…', icon: 'bx-share',
    run: () => { window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'app:import' /* deep link */ })); setTimeout(() => document.querySelector('.export-back')?.scrollIntoView({ block: 'start', behavior: 'smooth' }), 700) } },
]

/**
 * Cmd/Ctrl+K: one search box over both notes and the knowledge base, instead
 * of two separate search boxes in two separate panels. Picking a note opens
 * it; picking a fact inserts a citation at the cursor -- same citation
 * format @-mention completion and RelatedMemory already use, so all three
 * "find and cite a fact" paths in the app behave identically.
 */
export default function CommandPalette({ onOpenNote, onInsertFact, tabs = [], onOpenTab }: {
  onOpenNote: (id: string) => void
  onInsertFact: (text: string) => void

  tabs?: { noteId: string; title: string; snip?: string }[]
  onOpenTab?: (noteId: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [notes, setNotes] = useState<NoteBrief[]>([])
  const [notesTotal, setNotesTotal] = useState(0)
  const [facts, setFacts] = useState<Fact[]>([])
  const [activeIndex, setActiveIndex] = useState(0)
  const [recent, setRecent] = useState<NoteBrief[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const openRef = useRef(false)
  openRef.current = open
  // After closing, focus returns to where it was before opening (usually the editor): the panel stays mounted, so useRestoreFocus's mount / unmount approach can't be used
  const prevFocus = useRef<HTMLElement | null>(null)
  useEffect(() => {
    if (open) { prevFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; return }
    const el = prevFocus.current
    if (el && el.isConnected) el.focus()
    prevFocus.current = null
  }, [open])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      // ⌘K is ours; ⌘J is Trilium's jumpToNote — an alias so muscle memory from both works
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && (e.key.toLowerCase() === 'k' || e.key.toLowerCase() === 'j')) {
        e.preventDefault()
        setOpen((v) => !v)
      } else if (e.key === 'Escape' && openRef.current) {
        // Swallow Esc only while open: with the writing-plan panel stacked below, Esc closes only the topmost layer
        e.preventDefault()
        setOpen(false)
      }
    }


    function onOpenEvent() { setOpen(true) }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('open-command-palette', onOpenEvent)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('open-command-palette', onOpenEvent)
    }
  }, [])


  const listRef = useRef<HTMLDivElement>(null)
  useEffect(() => { (listRef.current?.querySelector('.palette-item.active') as HTMLElement | null)?.scrollIntoView({ block: 'nearest' }) }, [activeIndex])

  useEffect(() => {
    if (!open) return
    setQ('')
    setNotes([])
    setFacts([])
    setActiveIndex(0)
    const t = setTimeout(() => inputRef.current?.focus(), 0)
    // "Recently edited" lists only notes with text: empty folder shells (scaffolding like Journal / 2026 / September) created that day

    api.listNotesBrief('').then(({ notes: ns }) => setRecent(
      [...ns].filter((n) => n.has_body)
        .sort((a, b) => (b.updated_at > a.updated_at ? 1 : -1)).slice(0, 6),
    )).catch(() => {})
    return () => clearTimeout(t)
  }, [open])

  useEffect(() => {
    if (!open || !q.trim()) { setNotes([]); setNotesTotal(0); setFacts([]); return }
    let stale = false   // when typing fast, the previous char's results may come back after this one's; don't let them overwrite
    const t = setTimeout(() => {
      // Title hits first, body hits after, at most 8 — a single common character appears in almost every note's body,
      // listing them all is as good as not searching
      api.listNotesBrief(q).then(({ notes: list, total }) => {
        if (stale) return
        const needle = q.trim().toLowerCase()
        const byTitle = list.filter((n) => displayTitle(n).toLowerCase().includes(needle))
        const byBody = list.filter((n) => !byTitle.includes(n))
        setNotes([...byTitle, ...byBody].slice(0, 8))
        setNotesTotal(total)
      }).catch(() => {})
      api.recall(q, 6).then((r) => { if (!stale) setFacts(r.facts) }).catch(() => {})
    }, 200)
    return () => { stale = true; clearTimeout(t) }
  }, [q, open])

  if (!open) return null

  const typing = !!q.trim()
  const cmdHits = typing ? COMMANDS.filter((c) => c.label.includes(q.trim()) || t(c.label).toLowerCase().includes(q.trim().toLowerCase())) : COMMANDS
  // Same-named ones (three "One year of startup") can't be told apart by title and date: add a snippet of the first body line (first_body computed server-side)
  const dupName = (list: NoteBrief[]) => { const names = list.map(displayTitle); return new Set(names.filter((t, i) => names.indexOf(t) !== i)) }
  const dupNotes = dupName(notes); const dupRecent = dupName(recent)
  const firstBody = (n: NoteBrief) => n.first_body ? <span className="muted palette-snip">{n.first_body.slice(0, 40)}{n.first_body.length > 40 ? '…' : ''}</span> : null
  const needle = q.trim().toLowerCase()
  const tabHits = typing ? tabs.filter((t) => (t.title || '').toLowerCase().includes(needle)).slice(0, 6) : []
  // Notes already listed as tabs aren't repeated in the notes group
  const noteHits = notes.filter((n) => !tabHits.some((t) => t.noteId === n.id))
  const dupTabs = new Set(tabHits.map((t) => t.title).filter((t, i, arr) => arr.indexOf(t) !== i))
  const items = typing
    ? [
      ...cmdHits.map((c) => ({ kind: 'cmd' as const, cmd: c })),
      ...tabHits.map((t) => ({ kind: 'tab' as const, tab: t })),
      ...noteHits.map((n) => ({ kind: 'note' as const, note: n })),
      ...facts.map((f) => ({ kind: 'fact' as const, fact: f })),
    ]
    : [
      ...recent.map((n) => ({ kind: 'note' as const, note: n })),
      ...COMMANDS.map((c) => ({ kind: 'cmd' as const, cmd: c })),
    ]

  function choose(i: number) {
    const item = items[i]
    if (!item) return
    if (item.kind === 'note') onOpenNote(item.note.id)
    else if (item.kind === 'tab') (onOpenTab ?? onOpenNote)(item.tab.noteId)
    else if (item.kind === 'cmd') item.cmd.run()
    else onInsertFact(`${item.fact.text} [${item.fact.id}]`)
    setOpen(false)
  }

  let idx = 0
  function row(key: string, label: React.ReactNode, icon: string) {
    const i = idx++
    return (
      <div key={key} className={'palette-item' + (i === activeIndex ? ' active' : '')} onClick={() => choose(i)}>
        <Icon n={icon} /> {label}
      </div>
    )
  }

  return (
    <div className="palette-backdrop" onClick={() => setOpen(false)}>
      <div className="palette" role="dialog" aria-label={t('Search and commands')} onClick={(e) => e.stopPropagation()}>
        <input aria-label={t('Search notes, knowledge base, commands')}
          ref={inputRef}
          value={q}
          onChange={(e) => { setQ(e.target.value); setActiveIndex(0) }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIndex((i) => Math.min(i + 1, items.length - 1)) }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIndex((i) => Math.max(i - 1, 0)) }
            else if (e.key === 'Enter') { e.preventDefault(); choose(activeIndex) }
          }}
          placeholder={t('Search notes or knowledge base… (Esc to close)')}
        />
        <div className="palette-results" ref={listRef}>
          {typing && items.length === 0 && <p className="muted" style={{ padding: 8 }}>{t('No matches')}</p>}
          {!typing && recent.length > 0 && <p className="muted palette-group">{t('Recently edited')}</p>}
          {!typing && recent.map((n) => row(n.id, <span className="palette-line"><span className="palette-main">{displayTitle(n)}{dupRecent.has(displayTitle(n)) && firstBody(n)}</span>
            <span className="muted palette-when">{fmtDate(n.updated_at)}</span></span>, n.icon || 'bx-note'))}
          {typing && cmdHits.length > 0 && <p className="muted palette-group">{t('Commands')}</p>}
          {typing && cmdHits.map((c) => row('c' + c.label, t(c.label), c.icon))}
          {typing && tabHits.length > 0 && <p className="muted palette-group">{t('Open tabs')}</p>}
          {typing && tabHits.map((tab) => row('t' + tab.noteId, <span className="palette-line"><span className="palette-main"><Highlight text={tab.title || t('Untitled')} q={q} />
            {/* Three same-named "One year of startup" tabs can't be told apart by name: add a body snippet (same as the notes group) */}
            {dupTabs.has(tab.title) && tab.snip && <span className="muted palette-snip">{tab.snip.slice(0, 40)}{tab.snip.length > 40 ? '…' : ''}</span>}</span>
            <span className="muted palette-when">{t('Tab')}</span></span>, tab.noteId.startsWith('kb') || tab.noteId.startsWith('app:') ? 'bx-hash' : 'bx-window-alt'))}
          {noteHits.length > 0 && <p className="muted palette-group">{t('Notes')}</p>}
          {typing && noteHits.map((n) => {

            // "harness test" mixed into a row of "One year of startup", with no clue why it was there.
            const title = displayTitle(n)
            const s = title.toLowerCase().includes(q.trim().toLowerCase()) ? null : n.snippet   // the snippet is computed server-side
            return row(n.id, <span className="palette-line"><span className="palette-main"><Highlight text={title} q={q} />
              {s ? <span className="muted palette-snip">{s.before}<mark>{s.hit}</mark>{s.after}</span> : (dupNotes.has(title) && firstBody(n))}</span>
              <span className="muted palette-when">{fmtDate(n.updated_at)}</span></span>, n.icon || 'bx-note')
          })}
          {}
          {typing && notesTotal > notes.length && <p className="muted palette-group" style={{ marginTop: 2 }}>{t('{n} more not listed — type more to narrow down', { n: notesTotal - notes.length })}</p>}
          {facts.length > 0 && <p className="muted palette-group">{t('Knowledge base (click to insert a citation)')}</p>}
          {/* The date gets its own cell so it isn't cut: it used to be appended after the body, and for longer facts the date was eaten by the ellipsis first,
              so some rows in a column had dates and some didn't. */}
          {typing && facts.map((f) => row(f.id, <span className="palette-line"><span className="palette-main"><Highlight text={f.text} q={q} /></span>
            {f.when && <span className="muted palette-when">{f.when}</span>}</span>, 'bx-bulb'))}
          {!typing && <p className="muted palette-group">{t('Go to')}</p>}
          {!typing && COMMANDS.map((c) => row('c' + c.label, t(c.label), c.icon))}
        </div>
      </div>
    </div>
  )
}
