import { useCallback, useEffect, useRef, useState } from 'react'

import { journeyCatchUp, journeyDay, journeyDays, journeyDeleteDay, journeyDeleteSegment,
         journeyReport, journeyRetention, journeySaveReport, journeySpan, journeyThumb,
         type JourneyDay, type JourneyRetention, type JourneySegment } from '../api'
import { friendlyError } from '../util/friendlyError'
import { JOURNEY_DAY_EVENT, JOURNEY_SPAN_EVENT, takePendingJourneyDay, takePendingJourneySpan } from '../util/journeyOpen'
import { groupRuns } from '../util/journeyRuns'
import { parseMini, type Inline } from '../util/miniMarkdown'
import { usePoll } from '../util/poll'
import JourneyDenyPanel from './JourneyDenyPanel'
import JourneyRetentionPanel, { sayKeep } from './JourneyRetentionPanel'
import { toast } from '../toast'
import Icon from './Icon'
import { t } from '../i18n'



/** Each app gets a fixed color, **assigned in order of appearance, not cycled** — the same app must be
 *  the same color across the page, or the band can't be read as "where did the time go". Beyond 8, the rest go into "Other".
 *
 *  The eight color values live in CSS (`--jn-1..8`, one set each for light and dark) rather than hardcoded here: the light set
 *  would blur together on #242424. These eight are **measured** — colorblind adjacent pairs ΔE 9.1 light / 8.4 dark,
 *  normal vision 19.6 / 19.3, all above the bar. But who sits next to whom on the band is decided by the data (not slot order),
 *  so two non-color encodings are layered on: a 2px background gap between segments, and every row of the timeline below
 *  names the app. **Don't change the color values for looks**; changing them means measuring again. */
const BAND = Array.from({ length: 8 }, (_, i) => `var(--jn-${i + 1})`)
const OTHER = 'var(--jn-other)'

export function appColors(apps: string[]): Map<string, string> {
  const seen: string[] = []
  for (const a of apps) if (a && !seen.includes(a)) seen.push(a)
  const m = new Map<string, string>()
  seen.forEach((a, i) => m.set(a, i < BAND.length ? BAND[i] : OTHER))
  return m
}

const secs = (s: { start: string; end: string }) =>
  Math.max(0, (Date.parse(s.end) - Date.parse(s.start)) / 1000)


export function saySpan(sec: number): string {
  const m = Math.round(sec / 60)
  if (m < 1) return t('under 1 min')
  if (m < 60) return t('{n} min', { n: m })
  return `${t('{n} h', { n: Math.floor(m / 60) })} ${m % 60 ? t('{n} min', { n: m % 60 }) : ''}`.trim()
}

/** Sampling period, seconds. **Must match `INTERVAL_MS` in the shell's `desktop/src/capture.ts`** —
 *  this wiring gap has its own gate: `frontend/scripts/check-journey-tick-parity.mts`. */
export const JOURNEY_TICK_SEC = 15

/** How outrageous a "duration far exceeding sample count" must be to count (seconds). **The criterion is deliberately narrow**:
 *  a discrepancy under half an hour isn't worth pouring cold water on this day on the page. */
export const OVERLONG_MIN_EXCESS_SEC = 600
/** Only speak up when the day's total is over by this much. */
export const OVERLONG_DAY_EXCESS_SEC = 1800
/** The duration must exceed the sampled time by this many times to count as "far exceeding". */
export const OVERLONG_RATIO = 2


export function overlongExcess(segs: { start: string; end: string; n: number }[]):
{ segs: number; excess: number } {
  let n = 0, excess = 0
  for (const s of segs) {
    const dur = secs(s)
    const sampled = Math.max(0, s.n) * JOURNEY_TICK_SEC
    const over = dur - sampled
    // Both ends must be met: the multiple (relative) **and** the absolute duration (don't get dragged in by a 3-minute rounding)
    if (over >= OVERLONG_MIN_EXCESS_SEC && dur > sampled * OVERLONG_RATIO) { n += 1; excess += over }
  }
  return { segs: n, excess }
}

/** Two segments this far apart count as a "not recording" gap: lunch out at noon, an afternoon meeting.
 *  If the band didn't draw them, `Total 4 hours 24 minutes` would contradict a solid band running from morning to night. */
export const GAP_MIN = 15
/** The most width a gap may take on the band: a 12-hour overnight gap mustn't squeeze a whole day into two slivers. */
const GAP_CAP_SEC = 20 * 60


export function stepDay(days: string[], date: string, delta: number, today = ''): string | null {
  if (!days.length) return null
  const cur = date || today
  const i = cur ? days.indexOf(cur) : 0
  if (i < 0) {
    // Today isn't among "days with records": it sits **outside**, before the head of the list —
    // stepping back is the list's first item, stepping forward there's nothing.
    if (!date) return delta < 0 ? (days[0] ?? null) : null
    return null
  }
  const j = i + (delta < 0 ? 1 : -1)          // stepping back = moving later in the list (newest first)
  if (j < 0 || j >= days.length) return null
  return days[j] === (today || days[0]) ? '' : days[j]
}

type Cell = { seg?: JourneySegment; sec: number; gap?: [string, string] }


export function describable(segs: { desc: string; has_frame: boolean; skip?: string }[]): number {
  return segs.filter((s) => !s.desc && !s.skip && s.has_frame).length
}

/** What to write when a row has no description. **"Not described yet" is a promise** — wait a bit and it'll come;
 *  the ones that can't be filled must say why on the spot, so nobody waits forever. */
export function sayNoDesc(s: { has_frame: boolean; skip?: string }): string {
  if (s.skip) return t('{skip}; cannot be described', { skip: s.skip })
  return s.has_frame ? t('Not described yet') : t('No screenshot; cannot be described')
}


type BridgeState = { state: JourneyState; today: number; until?: number; stalled?: string; fake?: boolean }

/** Segments + gaps, arranged by time into something a band can draw. */
export function bandCells(segs: JourneySegment[]): Cell[] {
  const out: Cell[] = []
  segs.forEach((s, i) => {
    const prev = segs[i - 1]
    if (prev) {
      const idle = (Date.parse(s.start) - Date.parse(prev.end)) / 1000
      if (idle >= GAP_MIN * 60) out.push({ sec: Math.min(idle, GAP_CAP_SEC), gap: [prev.end, s.start] })
    }
    out.push({ seg: s, sec: secs(s) })
  })
  return out
}

/** The shell writes with `toISOString()` — **UTC with a Z**. Printing `iso.slice(11,16)` directly
 *  would be off by a whole timezone (8 hours in UTC+8), and times on a timeline can't be off at all. */
export const hhmm = (iso: string) =>
  new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })

/** "Not now" just closes this page — **don't lead to the settings page**:
 *  people who don't want it don't owe us a trip through settings. */
/** Daily report body. Laid out tighter than the editor — it's the beginning of this page, not all of it. */
function ReportBody({ md }: { md: string }) {
  const ink = (parts: Inline[]) => parts.map((p, i) =>
    p.t === 'b' ? <b key={i}>{p.s}</b> : p.t === 'code' ? <code key={i}>{p.s}</code> : <span key={i}>{p.s}</span>)
  return (
    <div className="jr-md">
      {parseMini(md).map((b, i) =>
        b.kind === 'h' ? <h4 key={i}>{ink(b.parts)}</h4>
        : b.kind === 'ul' ? <ul key={i}>{b.items.map((it, k) => <li key={k}>{ink(it)}</li>)}</ul>
        : b.kind === 'pre' ? <pre key={i}>{b.text}</pre>
        : <p key={i}>{ink(b.parts)}</p>)}
    </div>
  )
}

type Props = {
  onLater: () => void
  onOpenNote: (id: string) => void

  onOpenJournal: (date: string) => void
}

export default function JourneyPage({ onLater, onOpenNote, onOpenJournal }: Props) {
  // `null` = not asked yet. **Not getting an answer must not be treated as "never enabled"**: that would draw an app that's
  // recording as "enable it?", and the user clicks "Start recording" again — it'd look like it didn't take.
  const [state, setState] = useState<JourneyState | 'unknown' | null>(null)
  const [day, setDay] = useState<JourneyDay | null>(null)
  // Only for stepping to earlier days; empty string = today (the backend takes the current day itself; no page refresh needed past midnight).
  // The initial value is taken from the "day to open" — clicking in from the journal note's ribbon should land on that day
  // (`util/journeyOpen`, plan §8.4)
  const [date, setDate] = useState(takePendingJourneyDay)
  // Days with records (newest first). Stepping follows it — **adding or subtracting a day walks into a run of empty days**.
  const [days, setDays] = useState<string[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [writing, setWriting] = useState(false)
  const [spanning, setSpanning] = useState(0)
  /** Which blocks are expanded (keyed by block start time). After stepping days / refreshing they naturally collapse —
   *  expanding is a one-off "I want to check this stretch" action, not a preference. */
  const [opened, setOpened] = useState<Set<string>>(new Set())
  /** Timed pause until when (ms); where auto-description is stuck (empty string = not stuck) */
  const [until, setUntil] = useState(0)
  const [stalled, setStalled] = useState('')

  const [offline, setOffline] = useState(false)

  const [keepFor, setKeepFor] = useState<JourneyRetention | null>(null)

  const writeAbort = useRef<AbortController | null>(null)
  const spanAbort = useRef<AbortController | null>(null)

  const [confirmSeg, setConfirmSeg] = useState<number | null>(null)
  const [confirmDay, setConfirmDay] = useState(false)


  const [today, setToday] = useState('')
  const [fake, setFake] = useState(false)
  const [spanHint, setSpanHint] = useState(takePendingJourneySpan)
  const spanBox = useRef<HTMLDivElement>(null)
  const bridge = window.memoketDesktop?.journey

  const refresh = useCallback(async () => {
    // The web version has no shell at all: that's not an error, just "never enabled" (this page tells you to use the desktop version).
    if (!bridge) setState('off')
    else await bridge.state().then((s: BridgeState) => { setState(s.state); setUntil(s.until ?? 0); setStalled(s.stalled ?? ''); setFake(!!s.fake) })
      .catch(() => setState((v) => v ?? 'unknown'))
    journeyDay(date).then((d) => { setDay(d); setOffline(false); if (!date) setToday(d.date) }).catch(() => { setDay(null); setOffline(true) })
    journeyDays().then(setDays).catch(() => setDays((v) => v ?? []))
    // If the backend can't be read, keep the previous copy: on the informed-consent screen, better not to state "how long" than to state it wrong
    journeyRetention().then(setKeepFor).catch(() => setKeepFor((v) => v ?? null))
  }, [bridge, date])

  // Check status and segment count every 30 seconds; **no polling while the window is hidden**, check right away when back in front (util/poll)
  useEffect(() => { void refresh() }, [refresh])
  usePoll(() => void refresh(), 30_000)

  // Clicked again from the journal ribbon while this page is already open: the page won't remount, so step there on the spot
  useEffect(() => {
    const on = (e: Event) => setDate((e as CustomEvent<string>).detail ?? '')
    window.addEventListener(JOURNEY_DAY_EVENT, on)
    return () => window.removeEventListener(JOURNEY_DAY_EVENT, on)
  }, [])

  // Stepping to another day voids the two pending confirmations — **the segment index is "the Nth segment of this day"**;

  useEffect(() => { setConfirmSeg(null); setConfirmDay(false) }, [date])


  useEffect(() => {
    const on = (e: Event) => setSpanHint(Number((e as CustomEvent<number>).detail) || 0)
    window.addEventListener(JOURNEY_SPAN_EVENT, on)
    return () => window.removeEventListener(JOURNEY_SPAN_EVENT, on)
  }, [])

  // "…", `spanBox` is null, the scroll runs for nothing, and since `spanHint` never changes again it won't retry —
  // users coming from ⌘K only see the top of the page while the hint is two screens down. Count finished loading in the deps,
  // and add a delayed retry: "Don't record these" and "how long" are fetched asynchronously, and landing pushes this block down again.
  useEffect(() => {
    if (spanHint <= 0) return
    const go = () => spanBox.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
    go()
    const t = setTimeout(go, 700)
    return () => clearTimeout(t)
  }, [spanHint, state, days, keepFor])

  async function catchUp() {
    setBusy(true)
    try {
      const r = await journeyCatchUp(date, 10)


      // "nothing left to describe" — the user had just watched the button say "Describe these 10 segments", and that sentence after clicking
      // amounts to "there never were any", while 9 new `skip`s had just landed on disk.
      toast(r.described
        ? t('Described {described} segments, saved {ingested}{tail}', { described: r.described, ingested: r.ingested, tail: r.left ? t(', {n} left', { n: r.left }) : '' })
        : r.skipped
          ? t('Screenshots for these {n} segments are gone; they cannot be described{tail}', { n: r.skipped, tail: r.left ? t(', {n} still waiting', { n: r.left }) : '' })
          : t('Nothing left to describe'))
      await refresh()
    } catch (e) { toast(friendlyError(e), 'error') } finally { setBusy(false) }
  }


  async function writeReport() {
    if (writing) { stopWrite(); return }
    setWriting(true)
    const ctrl = new AbortController()
    writeAbort.current = ctrl
    try {
      const r = await journeyReport(date, ctrl.signal)
      setDay((d) => (d ? { ...d, report: r.report, report_segments: r.segments,
                           report_at: r.report_at, report_notes: r.notes ?? [] } : d))
      toast(t('Daily report written ({n} segments, {sec} s)', { n: r.segments, sec: (r.took_ms / 1000).toFixed(0) }))
    } catch (e) {

      if ((e as Error).name === 'AbortError') toast(t('Stopped; the review for this day was not written — the previous one (if any) remains'))
      else toast(friendlyError(e), 'error')
    } finally { writeAbort.current = null; setWriting(false) }
  }

  function stopWrite() { writeAbort.current?.abort() }

  /** The daily report follows this day; deleting the day deletes it. **To keep it, save it as a note** —
   *  it hangs under that day's journal page (a review follows the date, and the journal tree is organized by date),
   *  overwriting same-named ones, so rewriting doesn't leave a string of them on the tree. */
  async function saveReport() {
    if (!day?.report) return
    try {
      const r = await journeySaveReport(day.date)
      window.dispatchEvent(new CustomEvent('notes-changed'))
      toast(t('Saved under that day’s journal'))
      onOpenNote(r.note_id)
    } catch (e) { toast(friendlyError(e), 'error') }
  }

  /** A review over a period. **The output is a note** — when done, take the user straight there,
   *  rather than opening a read-only mini window on this page: that kind of thing is gone once closed. */
  async function runSpan(days: number) {
    if (spanning === days) { spanAbort.current?.abort(); return }   // second click = stop
    setSpanning(days)
    const ctrl = new AbortController()
    spanAbort.current = ctrl
    try {
      const r = await journeySpan(days, ctrl.signal)
      window.dispatchEvent(new CustomEvent('notes-changed'))
      toast(t('Written from {n} days of daily reports{tail}', { n: r.days, tail: r.missing.length ? t(' ({n} days had no report)', { n: r.missing.length }) : '' }))
      onOpenNote(r.note_id)
    } catch (e) {
      if ((e as Error).name === 'AbortError') toast(t('Stopped; this review was not written and no note was added to the tree'))
      else toast(friendlyError(e), 'error')
    } finally { spanAbort.current = null; setSpanning(0) }
  }


  async function dropSeg(s: JourneySegment) {
    if (!day) return
    setConfirmSeg(null)

    // said nothing at all (`promise Failed to fetch` in the log, `toasts=[]`), while the user
    // had just clicked "OK" — he'd think it was deleted. "I thought it was wiped clean" is the one error this feature can least afford.
    try {
      const r = await journeyDeleteSegment(day.date, s.i)
      toast(t('Deleted this segment{tail}', { tail: r.removed_facts ? t(', along with {n} memories', { n: r.removed_facts }) : '' }))
      await refresh()
    } catch (e) { toast(t('Could not delete this segment; it is still there: {err}', { err: friendlyError(e) }), 'error') }
  }

  async function wipe() {
    if (!day) return
    setConfirmDay(false)
    try {
      const r = await journeyDeleteDay(day.date)
      toast(t('Deleted this day{tail}', { tail: r.removed_facts ? t(', along with {n} memories', { n: r.removed_facts }) : '' }))
      await refresh()
    } catch (e) { toast(t('Could not delete {date}; the day is still there: {err}', { date: day.date, err: friendlyError(e) }), 'error') }
  }

  const known = days ?? []
  const prev = stepDay(known, date, -1, today)
  const next = stepDay(known, date, 1, today)

  if (state === null || days === null) return <p className="muted" style={{ padding: 16 }}>…</p>
  if (state === 'unknown') {
    return (
      <div className="kb-page kb-empty">
        <Icon n="bx-error" />
        <h3>{t('Cannot read capture status')}</h3>
        <p className="muted">{t('The capture side of the app is not responding, so ')}<b>{t('whether it is on or off is unknown')}</b>{t('. The menu bar icon is authoritative; restarting the app usually fixes this.')}</p>
      </div>
    )
  }

  // —— Never enabled: the informed-consent screen. **Can't be skipped, can't be pre-checked** (§1 ①) ————————
  //
  // "Never enabled" must be judged by **whether anything was ever recorded**, not just the current state: if stopping

  if (state === 'off' && known.length === 0) {
    return (
      <div className="kb-page journey-consent">
        <h2 className="kb-note-title"><Icon n="bx-desktop" className="muted" /> {t('Screen activity recording')}</h2>
        <p className="muted">
          {t('Glances at your screen now and then, notes “what you are doing” in one line, and by evening sums up what you did today.')}
        </p>
        <dl className="journey-facts">
          <dt>{t('What is recorded')}</dt><dd>{t('Only a one-line description of “which app, doing what”. Screenshots are deleted once read; a single thumbnail is kept for you to verify')}</dd>
          {}
          <dt>{t('Where it lives')}</dt><dd>{t('Segments and descriptions stay on this machine. Screenshots go to the vision model set in Settings (the intranet one by default), independent of the writing model')}</dd>
          {}
          <dt>{t('Retention')}</dt>
          <dd>{keepFor
            ? <>{t('Descriptions are kept ')}<b>{sayKeep(keepFor.segment_days)}</b>{t(', thumbnails ')}<b>{sayKeep(keepFor.thumb_days)}</b>{t(', raw screenshots at most {n} days (deleted as soon as described). Expired items delete themselves, ', { n: keepFor.frame_days })}
                <b>{t('along with the memories extracted into the knowledge base')}</b>{t('. Change these under Retention further down this page, or delete everything in one click')}</>
            : <>{t('Expired items delete themselves along with the memories extracted into the knowledge base. Once enabled, view and change this under Retention further down this page')}</>}
          </dd>
          <dt>{t('What is never recorded')}</dt><dd>{t('Password managers, banking, private windows — excluded by default; on a match no screenshot is even taken')}</dd>
          <dt>{t('How to turn it off')}</dt><dd>{t('There is always a switch in the menu bar. Deleting a segment or a whole day also deletes it ')}<b>{t('along with the memories extracted into the knowledge base')}</b></dd>
        </dl>
        <div className="row" style={{ gap: 8, marginTop: 14 }}>
          <button className="primary" onClick={() => { void bridge?.start().then(refresh) }}
                  disabled={!bridge} title={bridge ? '' : t('The web version cannot capture; use the desktop app')}>{t('Start recording')}</button>
          <button onClick={onLater}>{t('Not now')}</button>
        </div>
        <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>
          {bridge ? t('After “Start recording”, macOS asks once for screen recording permission — you must allow it, or nothing can be recorded.')
                  : t('The web version cannot capture; use the desktop app.')}
        </p>
      </div>
    )
  }

  // —— Permission revoked by the system: **the easiest to miss and the nastiest** (§8.5) ————————————————
  if (state === 'no-permission') {
    return (
      <div className="kb-page kb-empty">
        <Icon n="bx-error" />
        <h3>{t('Screen capture is blocked')}</h3>
        <p className="muted">
          {t('Most likely macOS “Screen Recording” permission was turned off — ')}<b>{t('nothing can be recorded right now')}</b>{t('. Enable MEMOKET NOTE under System Settings › Privacy & Security › Screen Recording, then come back.')}
        </p>
      </div>
    )
  }

  const segs = day?.segments ?? []
  const colors = appColors(segs.map((s) => s.app))
  const runs = groupRuns(segs)
  const total = segs.reduce((n, s) => n + secs(s), 0)
  const overlong = overlongExcess(segs)
  const byApp = new Map<string, number>()
  for (const s of segs) byApp.set(s.app, (byApp.get(s.app) ?? 0) + secs(s))
  const left = describable(segs)
  const described = segs.filter((s) => s.desc).length
  // Segments recorded since the daily report was written (>0 means it should prompt a rewrite)
  const grown = day?.report ? Math.max(0, described - (day.report_segments || 0)) : 0

  return (
    <div className="kb-page">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span className="row" style={{ gap: 6, alignItems: 'baseline' }}>
          <h2>{day?.date ?? t('Today')} · {t('Screen activity')}</h2>
          {/* One page per day, steppable. Without these two arrows, "what was I doing yesterday" could only be stared at */}
          <button className="icon-btn sm" title={t('Previous day')} disabled={!prev}
                  onClick={() => prev !== null && setDate(prev)}><Icon n="bx-chevron-left" /></button>
          <button className="icon-btn sm" title={t('Next day')} disabled={next === null}
                  onClick={() => next !== null && setDate(next)}><Icon n="bx-chevron-right" /></button>
        </span>
        <span className="row" style={{ gap: 6 }}>
          {/* After stopping this page still exists (for looking back and deleting), so it must also be able to **start again** here */}
          {state === 'off'
            ? <button className="primary" onClick={() => { void bridge?.start().then(refresh) }}
                      disabled={!bridge} title={bridge ? '' : t('The web version cannot capture; use the desktop app')}>{t('Start recording')}</button>
            : state === 'paused'
              ? <button onClick={() => { void bridge?.resume().then(refresh) }}>{t('Resume recording')}</button>
              : <button onClick={() => { void bridge?.pause(60).then(refresh) }}>{t('Pause for 1 hour')}</button>}
          {}
          <button className="linklike" onClick={() => onOpenJournal(day?.date ?? '')}
                  title={t('Open this day’s journal (created if missing)')}>{t('Go to this day’s journal')}</button>
          {}
          <button className="linklike danger" onClick={() => setConfirmDay(true)}
                  disabled={(!segs.length && !day?.report) || confirmDay}
                  title={segs.length || day?.report ? '' : t('No records for this day yet')}>{t('Delete this day')}</button>
        </span>
      </div>

      {}
      {confirmDay && day && (
        <div className="journey-keep-confirm" role="alertdialog" aria-label={t('Delete screen activity for {date}', { date: day.date })}>
          <b>{t('Delete screen activity for {date}? This will delete:', { date: day.date })}</b>
          <ul>
            {}
            {segs.length > 0 && <li>{t('{n} segments, {described} of them described', { n: segs.length, described: segs.filter((s) => s.desc).length })}</li>}
            {segs.some((s) => s.has_thumb) && <li>{t('{n} thumbnails, plus any raw screenshots not yet deleted', { n: segs.filter((s) => s.has_thumb).length })}</li>}
            {day.report && <li>{t('The daily report written for this day')}</li>}
            {segs.length > 0 && <li>{t('The memories extracted from these descriptions into the knowledge base')}</li>}
          </ul>
          <p className="muted">{t('Once deleted it is gone; there is no trash. Daily reports saved as notes remain — those are notes, not records.')}</p>
          <div className="row" style={{ gap: 6 }}>
            <button className="danger" onClick={() => void wipe()}>
              <Icon n="bx-trash" /> {t('Yes, delete this day')}
            </button>
            <button onClick={() => setConfirmDay(false)}>{t('Keep it')}</button>
          </div>
        </div>
      )}

      <p className="muted journey-state">
        {/* On past days "Recording" is a pointless sentence, easily read as "back-filling that day".
            "Not recording", conversely, must be said — that's the state users most need to know. */}
        {state === 'off' ? t('Not recording — earlier records remain; you can review or delete them.')
          : date ? '' : state === 'paused'
            ? (until ? t('Paused — resumes automatically at {time}.', { time: hhmm(new Date(until).toISOString()) }) : t('Paused — nothing is recorded meanwhile.'))
            : t('Recording.')}
        {segs.length > 0 && ` ${t('{day}: {n} segments, {span} in total.', { day: date ? t('This day') : t('Today'), n: segs.length, span: saySpan(total) })}`}
      </p>
      {}
      {overlong.excess >= OVERLONG_DAY_EXCESS_SEC && (
        <p className="muted journey-state"><Icon n="bx-error" /> {t('This total runs long: {n} segments last far longer than their sample count suggests, adding about {span}. Most likely waking from sleep / lock folded the gap into the previous segment (an old bug, fixed, but **existing records cannot be corrected**). The segments in the band still open, and each one’s start and end are accurate.', { n: overlong.segs, span: saySpan(overlong.excess) })}</p>
      )}
      {}
      {fake && (
        <p className="muted journey-state"><Icon n="bx-error" /> {t('This page is not showing real screen activity — this instance uses a fake capture source (')}<code>journey/_fake.json</code>{t('); no screen was captured. Delete that file and restart to record for real.')}</p>
      )}
      {offline && (
        <p className="muted journey-state"><Icon n="bx-error" /> {t('The backend is not responding, so this day’s records cannot be read — capture keeps running in the shell; refresh later.')}</p>
      )}
      {/* Say so when description is stuck: with the image model unreachable the shell fails every 3 minutes,
          and on the user's side there's just a full page of "Not described yet", looking broken */}
      {!date && stalled && left > 0 && state === 'running' && (
        <p className="muted journey-state"><Icon n="bx-error" /> {t('Auto-describe stopped: {why}. It retries every 3 minutes; you can also click “Describe” below.', { why: stalled })}</p>
      )}

      {/* **Report on top, evidence below** (§8.3 ②): first see what today was about, scroll down to check */}
      {day?.report ? (
        <div className="card journey-report">
          <div className="row" style={{ alignItems: 'center', gap: 8, marginBottom: 2 }}>
            <span className="muted" style={{ fontSize: 'var(--t-sm)' }}
                  title={day.report_at ? t('Written at {time}', { time: hhmm(day.report_at) }) : undefined}>
              {t('This day’s review')}
              {/* **The daily report is a snapshot; the day keeps growing**: without saying how many segments it was written from, what you see in the afternoon
                  is still the morning's, with no sign that it's out of date */}
              {grown > 0
                ? ` ${t('Written from {n} segments; {grown} more recorded since', { n: day.report_segments, grown })}`
                : day.report_segments > 0 && ` ${t('Written from {n} segments', { n: day.report_segments })}`}
            </span>
            <span style={{ flex: 1 }} />
            <button className="chip chip-action" onClick={() => void saveReport()}><Icon n="bx-save" /> {t('Save as note')}</button>
            {}
            <button className={'chip chip-action' + (grown > 0 ? ' hot' : '')}
                    onClick={() => void writeReport()}
                    title={writing ? t('Stop this rewrite') : t('Rewrite from the current records')}>
              {writing ? <><span className="spinner" /> {t('Stop')}</> : <><Icon n="bx-refresh" /> {t('Rewrite')}</>}
            </button>
          </div>
          <ReportBody md={day.report} />
          {/* Deterministic check of the daily report (backend `harness/checks/journey.py`, plan 8.2).
              **Judged, not blocked** — one model call, a one-shot output; the check results sit under it,
              and whether to "Rewrite" is the user's call. Same tier as slides, outline and continue. */}
          {(day.report_notes ?? []).length > 0 && (
            <ul className="journey-report-notes">
              {(day.report_notes ?? []).map((n, i) => <li key={i} style={{ marginBottom: 4 }}>{n}</li>)}
            </ul>
          )}
        </div>
      ) : described > 0 && (
        <div className="row">
          <button className="primary" onClick={() => void writeReport()}
                  title={writing ? t('Stop; skip the review for this day') : undefined}>
            {writing ? <><span className="spinner" /> {t('Writing…')}{'  '}{t('Stop')}</> : t('Write this day’s review ({n} segments)', { n: described })}
          </button>
          <span className="muted" style={{ fontSize: 'var(--t-sm)', alignSelf: 'center', marginInlineStart: 8 }}>
            {t('One model call. Durations are counted; the model only writes what moved forward and where it got stuck.')}
          </span>
        </div>
      )}

      {segs.length === 0 ? (

        !offline && <p className="muted">{
          date ? t('No records for this day.')
            : state === 'running' ? t('Recording just started today; the first segment will show up here once there is enough.')
              : state === 'paused' ? t('No records today yet — recording is paused; it continues after “Resume recording”.')
                : t('No records today yet — not recording; click “Start recording” at the top right to begin.')
        }</p>
      ) : (
        <>
          {/* One band per day: **answers "where did the time go" at a glance**. No pie chart — proportion isn't the question here */}
          <div className="journey-band" role="img" aria-label={t('Today {span}', { span: saySpan(total) })}>
            {bandCells(segs).map((c, i) => (
              <span key={i} className={c.gap ? 'journey-gap' : undefined}
                    title={c.gap ? t('{from}–{to} not recording', { from: hhmm(c.gap[0]), to: hhmm(c.gap[1]) })
                                 : `${hhmm(c.seg!.start)}–${hhmm(c.seg!.end)} ${c.seg!.app}`}
                    style={{ flex: `${Math.max(c.sec, 60)} 0 0`,
                             background: c.gap ? undefined : colors.get(c.seg!.app) ?? OTHER }} />
            ))}
          </div>
          <div className="chip-wrap journey-legend">
            {[...byApp.entries()].sort((a, b) => b[1] - a[1]).map(([app, sec]) => (
              <span key={app} className="badge">
                <i className="journey-dot" style={{ background: colors.get(app) ?? OTHER }} />
                {app} {saySpan(sec)}
              </span>
            ))}
          </div>

          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', marginTop: 14 }}>
            <h3 className="kb-section-title">{t('Timeline of the day')}</h3>
            {left > 0 && (
              <button onClick={() => void catchUp()} disabled={busy}>
                {busy ? <span className="spinner" /> : t('Describe these {n} segments', { n: Math.min(left, 10) })}
              </button>
            )}
          </div>
          <div className="stack">
            {}
            {runs.map((run, ri) => {
              const one = run.segs.length === 1
              const open = one || opened.has(run.start)
              return (
                <div key={ri} className={'journey-run' + (open && !one ? ' open' : '')}>
                  {!one && (
                    <div className="journey-row journey-run-head">
                      <span className="journey-time">{hhmm(run.start)}–{hhmm(run.end)}</span>
                      <span className={'journey-desc' + (run.desc ? '' : ' muted')}>
                        {/* If **even one segment** in this block can still be filled, say "Not described yet";
                            when none can, give the reason from the first one. */}
                        {run.desc || sayNoDesc(run.segs.find((s) => !s.skip && s.has_frame) ?? run.segs[0])}
                      </span>
                      <span className="journey-app" title={run.app}>
                        <i className="journey-dot" style={{ background: colors.get(run.app) ?? OTHER }} />
                        <span className="journey-app-name">{run.app}</span>
                      </span>
                      <button className="chip journey-run-more"
                              aria-expanded={open}
                              title={open ? t('Collapse these segments') : t('Expand to see what each segment recorded')}
                              onClick={() => setOpened((o) => {
                                const n = new Set(o)
                                if (!n.delete(run.start)) n.add(run.start)
                                return n
                              })}>
                        {t('{n} segments', { n: run.segs.length })} <Icon n={open ? 'bx-chevron-up' : 'bx-chevron-down'} />
                      </button>
                    </div>
                  )}
                  {open && run.segs.map((s) => (
                    <div key={s.i} className="journey-row">
                      <span className="journey-time">{hhmm(s.start)}–{hhmm(s.end)}</span>
                      <span className={'journey-desc' + (s.desc ? '' : ' muted')}>
                        {s.desc || sayNoDesc(s)}
                        {/* The thumbnail is **evidence**: a description with no basis at all can't be judged by users as made up or not.
                            Takes no space by default; appears only when the mouse rests on that row. */}
                        {s.has_thumb && (
                          <img className="journey-thumb" loading="lazy" alt=""
                               src={journeyThumb(day!.date, s.i)} />
                        )}
                      </span>
                      <span className="journey-app" title={s.title || s.app}>
                        <i className="journey-dot" style={{ background: colors.get(s.app) ?? OTHER }} />
                        <span className="journey-app-name">{s.app}</span>
                      </span>
                      <button className="icon-btn sm journey-del" title={t('Delete this segment (along with the memories extracted from it)')}
                              aria-expanded={confirmSeg === s.i}
                              onClick={() => setConfirmSeg((v) => (v === s.i ? null : s.i))}><Icon n="bx-trash" /></button>
                      {}
                      {confirmSeg === s.i && (
                        <div className="journey-row-confirm" role="alertdialog"
                             aria-label={t('Delete the segment {from}–{to}', { from: hhmm(s.start), to: hhmm(s.end) })}>
                          <b>{t('Delete this segment?')}</b>
                          <p className="muted">{s.desc || t('(not described yet)')}</p>
                          <p className="muted">{t('Also deletes the memories extracted into the knowledge base; once deleted it is gone.')}</p>
                          <div className="row" style={{ gap: 6 }}>
                            <button className="danger" onClick={() => void dropSeg(s)}>
                              <Icon n="bx-trash" /> {t('Yes, delete')}
                            </button>
                            <button onClick={() => setConfirmSeg(null)}>{t('Keep it')}</button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        </>
      )}

      <JourneyDenyPanel />

      {/* "How long to keep" + "Delete everything". Next to "Don't record these" — they answer the same question:
          **can I erase it** (one of the three questions in §8.1). Refresh this page after clearing:
          if the deleted days stayed in the stepping list, users would think it failed. */}
      <JourneyRetentionPanel onChanged={() => void refresh()} />

      {/* Review over a period: **daily reports → long report → a note**. At the very bottom —
          it isn't the protagonist of the "Today" page, it's a path out of it (§4.2). */}
      <div className="journey-span" ref={spanBox}>
        <h3 className="kb-section-title">{t('Review a period')}</h3>
        <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '2px 0 6px' }}>
          {t('Combines these days’ reports into one long review saved as a note — you can keep editing and continuing it. Days without a report are skipped and listed in the note.')}<b>{t('One click is one model call.')}</b>
        </p>
        {}
        {spanHint > 0 && spanning === 0 && (
          <p className="journey-span-hint">
            <Icon n="bx-info-circle" /> {t('From ⌘K: to write the “last {n} days” review, press the button below.', { n: spanHint })}
            <b>{t('It is one model call, so that click is left to you.')}</b>
          </p>
        )}
        <div className="row" style={{ gap: 6 }}>
          {/* The running one becomes "Stop", only the other is disabled (range can change only after it finishes).
              If both were disabled, the running job would have no way out. */}
          {[7, 30].map((d) => (
            <button key={d} className={spanHint === d && spanning === 0 ? 'primary' : undefined}
                    disabled={spanning !== 0 && spanning !== d} onClick={() => { setSpanHint(0); void runSpan(d) }}
                    title={spanning === d ? t('Stop this review') : spanning !== 0 ? t('Writing; change the range once it finishes') : t('One model call')}>
              {spanning === d ? <><span className="spinner" /> {t('Last {n} days', { n: d })}{'  '}{t('Stop')}</> : t('Last {n} days', { n: d })}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
