
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import * as api from '../api'
import type { Fact } from '../api'
import { clickable } from '../util/clickable'
import { CARD_WIDTH, placeCard, pushLineBelow, seamPush } from '../util/cardPlacement'
import { candidates, emptyReason, summarizeTrace, type TraceSummary } from '../util/traceCard'
import type { AltHoverRange } from '../editor/altHover'
import Icon from './Icon'
import { t } from '../i18n'

const GAP = 10

export type TraceCardState = { phrase: string; anchor: DOMRect; reason: 'hover' | 'key'; range: AltHoverRange }
type Loaded = { phrase: string; summary: TraceSummary; why?: '' | 'no_terms' | 'weak'; kbEmpty?: boolean }

// Hovering the same word twice needs no second query (lexical recall is fast anyway, but flashing "Searching the knowledge base..." between close and reopen looks bad)
const cache = new Map<string, Loaded>()

/** Query the knowledge base. For a run of single characters (a word the segmenter does not know): query each two-character window covering the mouse character, use whichever has records, and only if none does query the whole run (`util/traceCard.candidates`). */
export async function lookup(phrase: string, focus: number | undefined): Promise<Loaded> {
  const key = focus == null ? phrase : `${phrase}#${focus}`
  const hit = cache.get(key)
  if (hit) return hit
  let shown = phrase
  let r: Awaited<ReturnType<typeof api.recall>>
  if (focus == null) {
    r = await api.recall(phrase, 8)
  } else {
    const cands = candidates(phrase, focus)               // two-character windows first, the whole run last (all three lexical, in parallel)
    const got = await Promise.all(cands.map((c) => api.recall(c, 8)))
    const windows = cands.length > 1 ? cands.length - 1 : 1
    let best = 0
    for (let i = 1; i < windows; i++) if (got[i].facts.length > got[best].facts.length) best = i
    // Only when no two-character window hits does the whole run get a turn; if that also misses, report the leftmost two-character window (not the whole run -- the user rested on one word)
    if (got[best].facts.length === 0 && windows < cands.length && got[cands.length - 1].facts.length > 0) best = cands.length - 1
    shown = cands[best]; r = got[best]
  }
  const loaded: Loaded = { phrase: shown, summary: summarizeTrace(r.facts), why: r.why_empty, kbEmpty: r.kb_empty }
  cache.set(key, loaded)
  return loaded
}

export default function TraceCard({ card, content, onClose, onInsert, onTrace }: {
  card: TraceCardState
  content: string
  onClose: () => void
  onInsert: (text: string) => void
  /** Run the 20-second full background (model); result in the right pane's "Timeline" */
  onTrace: (phrase: string) => void
}) {
  const { phrase, anchor, reason, range } = card
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number; width: number }>({ left: anchor.right + GAP, top: anchor.top - 8, width: CARD_WIDTH })
  const [data, setData] = useState<Loaded | null>(null)
  const [failed, setFailed] = useState('')

  useEffect(() => {
    setData(null); setFailed('')
    let alive = true
    lookup(phrase, range.focus).then((d) => { if (alive) setData(d) })
      .catch((e) => { if (alive) setFailed(String(e?.message ?? e)) })
    return () => { alive = false }
  }, [phrase, range.focus])

  useLayoutEffect(() => {
    const h = ref.current?.offsetHeight ?? 140
    const pane = (ref.current?.closest('.note-pane') ?? document.querySelector('.note-pane')) as HTMLElement | null
    const b = pane?.getBoundingClientRect()
    const bounds = b && b.width > 0 ? b : { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight, width: window.innerWidth, height: window.innerHeight }
    const p = placeCard(anchor, bounds, h, window.innerHeight)
    setPos({ left: p.left, top: p.top, width: p.width })

    return pushLineBelow(anchor, seamPush(p.side, h))
  }, [anchor, data, failed])

  // From the keyboard: the card takes focus (Tab reaches the buttons); on close focus returns to the editor
  useEffect(() => {
    if (reason !== 'key') return
    ref.current?.focus()
    return () => { (document.querySelector('.note-scroll .cm-content') as HTMLElement | null)?.focus() }
  }, [reason, phrase])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) onClose() }
    const onMove = (e: MouseEvent) => {
      if (reason !== 'hover') return
      const inCard = ref.current?.contains(e.target as Node)
      const a = anchor
      const nearWord = e.clientX >= a.left - 12 && e.clientX <= a.right + GAP + 4 && e.clientY >= a.top - 10 && e.clientY <= a.bottom + 10
      if (!inCard && !nearWord) onClose()
    }
    const onScroll = () => onClose()
    document.addEventListener('keydown', onKey, true)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('mousemove', onMove)
    document.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('keydown', onKey, true)
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('scroll', onScroll, true)
    }
  }, [reason, anchor, onClose])

  const s = data?.summary
  const shown = data?.phrase ?? phrase
  const cited = (f: Fact) => content.includes(`[${f.id}]`)
  const row = (label: string, f: Fact) => (
    <div key={label + f.id} className="margin-card-fact trace-row" title={t('Open this record')}
         {...clickable(() => window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:fact:' + f.id })))}>
      <span className="trace-when"><span className="badge">{label}</span> {f.when || '—'}</span>
      <span>{f.text}</span>
    </div>
  )
  const latest = s?.last ?? s?.first ?? s?.related[0] ?? null

  return (
    <div ref={ref} className="margin-card trace-card" role="dialog" tabIndex={-1} aria-label={t('Trace of “{phrase}”', { phrase: shown })}
         style={{ left: pos.left, top: pos.top, width: pos.width }}>
      <div className="row margin-card-head">
        <span className="badge"><Icon n="bx-history" /> {t('Trace')}</span>
        <span className="margin-card-where trace-phrase">“{shown}”{s ? ' · ' + t('{n} in the knowledge base', { n: s.count }) : ''}</span>
        <button className="icon-btn margin-card-close" title={t('Collapse (Esc)')} onClick={onClose}><Icon n="bx-x" /></button>
      </div>
      {failed
        ? <div className="margin-card-say">{t('Could not look up: ')}{failed}</div>
        : !s
          ? <div className="margin-card-say muted">{t('Searching the knowledge base…')}</div>
          : s.count === 0
            ? <div className="margin-card-say">{emptyReason(shown, data?.why, data?.kbEmpty)}</div>
            : (
              <div className="stack margin-card-facts">
                {s.first && row(t('First'), s.first)}
                {s.last && row(t('Latest'), s.last)}
                {s.related.map((f) => row(t('Related'), f))}
              </div>
            )}
      <div className="row margin-card-actions">
        {latest && (cited(latest)
          ? <span className="badge ok" title={t('Already cited in the note')}>{t('Cited')}</span>
          : <button onClick={() => { onInsert(` [${latest.id}]`); onClose() }} title={t('Insert the latest record’s source at the cursor')}>{t('Cite the latest')}</button>)}
        {s && s.count > 0 && <button onClick={() => { onTrace(shown); onClose() }} title={t('Have the model lay out how this evolved over time (about 20 seconds); the result appears in the Trace tab')}>{t('Full trace')}</button>}
        <span className="muted margin-card-more">{reason === 'key' ? t('Esc to close') : t('Move away to close')}</span>
      </div>
    </div>
  )
}
