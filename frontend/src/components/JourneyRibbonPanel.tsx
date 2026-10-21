import { useEffect, useState } from 'react'

import { journeyDay, type JourneyDay } from '../api'
import { openJourneyDay } from '../util/journeyOpen'
import Icon from './Icon'
import { t } from '../i18n'
import { saySpan } from './JourneyPage'

/**
 * "This day's screen activity" on the journal note (`docs/daily-journey-plan.md` §8.4).
 *
 * **A summary + one link in, nothing more.** The second half of the plan's sentence is the point:
 * "the two sides can find each other, but **machine-written content is not stuffed directly into the user's note body**" —
 * the body is what the user writes (§1 "the tree is what I wrote and arranged"). The machine-written copy lives on the screen activity
 * page; here there's only a handle to reach it. Turning a daily report into a note has its own dedicated
 * "Save as note", and that click is **pressed by the user**.
 *
 * Why the ribbon and not the right pane: the ribbon holds **this note's metadata**, and
 * "what I did on screen this day" is exactly this journal note's metadata.
 */
export default function JourneyRibbonPanel({ date }: { date: string }) {
  const [day, setDay] = useState<JourneyDay | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let stale = false
    setDay(null); setFailed(false)
    journeyDay(date).then((d) => { if (!stale) setDay(d) }).catch(() => { if (!stale) setFailed(true) })
    return () => { stale = true }
  }, [date])

  const segs = day?.segments ?? []
  const byApp = new Map<string, number>()
  for (const s of segs) {
    const sec = Math.max(0, (Date.parse(s.end) - Date.parse(s.start)) / 1000)
    byApp.set(s.app, (byApp.get(s.app) ?? 0) + sec)
  }
  const top = [...byApp.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4)
  /** The daily report's first paragraph: it's the day's conclusion. **Only one paragraph is excerpted** — the ribbon is a metadata area,
   *  laying the whole report out here would push the body down. */
  const lead = (day?.report ?? '').split('\n').map((l) => l.trim())
    .find((l) => l && !l.startsWith('#') && !l.startsWith('|') && !l.startsWith('-') && !l.startsWith('·'))

  return (
    <div className="journey-ribbon">
      {failed ? (
        <p className="muted"><Icon n="bx-error" /> {t('Cannot read this day’s screen activity (backend not responding).')}</p>
      ) : !day ? (
        <p className="muted">…</p>
      ) : segs.length === 0 ? (
        <p className="muted">{t('No screen activity for this day — it was off, or no segment was recorded.')}</p>
      ) : (
        <>
          <p className="journey-ribbon-sum">
            <b>{t('{n} segments', { n: segs.length })}</b>{t(', {span} in total', { span: saySpan(segs.reduce((n, s) => n + Math.max(0, (Date.parse(s.end) - Date.parse(s.start)) / 1000), 0)) })}
            {top.length > 0 && <>{'  '}{top.map(([a, sec]) => `${a} ${saySpan(sec)}`).join('  ')}</>}
          </p>
          {lead && <p className="journey-ribbon-lead">{lead.slice(0, 140)}{lead.length > 140 ? '…' : ''}</p>}
        </>
      )}
      {/* **One link in**: this page only gives a summary; details / delete / writing the daily report are all on that page */}
      <button className="chip chip-action" onClick={() => openJourneyDay(date)}>
        <Icon n="bx-desktop" /> {t('Open this day’s screen activity')}
      </button>
    </div>
  )
}
