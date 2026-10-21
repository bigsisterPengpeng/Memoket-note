import { useEffect, useMemo, useState } from 'react'
import { clickable } from '../../util/clickable'

import { kbDay, kbTimeline, type FactDetail, type KbTimelineMonth } from '../../api'
import { FactList, type KbActions } from './KbBits'
import Icon from '../Icon'
import { t } from '../../i18n'

/** Vertical timeline: year → month → day. Bars are the month's / day's fact counts; click a day to expand its facts. */
export default function TimelinePage({ actions }: { actions: KbActions }) {
  const [months, setMonths] = useState<KbTimelineMonth[] | null>(null)
  const [openMonth, setOpenMonth] = useState<string | null>(null)
  const [openDay, setOpenDay] = useState<string | null>(null)
  const [dayFacts, setDayFacts] = useState<Record<string, FactDetail[]>>({})
  useEffect(() => { kbTimeline().then((m) => { setMonths(m); const heavy = [...m].reverse().find((x) => x.facts >= 10) ?? m[m.length - 1]; setOpenMonth(heavy?.month ?? null) }).catch(() => setMonths([])) }, [])
  useEffect(() => {
    if (!openDay || dayFacts[openDay]) return
    kbDay(openDay).then((f) => setDayFacts((m) => ({ ...m, [openDay]: f }))).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openDay])

  const years = useMemo(() => {
    const out: { year: string; months: KbTimelineMonth[] }[] = []
    for (const m of [...(months ?? [])].reverse()) {
      const y = m.month.slice(0, 4)
      const g = out[out.length - 1]
      if (g && g.year === y) g.months.push(m); else out.push({ year: y, months: [m] })
    }
    return out
  }, [months])

  const sq = (n: number) => Math.sqrt(Math.max(0, n))
  const max = Math.max(1, ...(months ?? []).map((m) => sq(m.facts)))

  if (!months) return <p className="muted"><span className="spinner" /> {t('Loading…')}</p>
  if (months.length === 0) return <p className="muted">{t('No dated facts yet.')}</p>
  return (
    <div className="kb-page">
      <div className="kb-head">
        <h2 className="kb-note-title"><Icon n="bx-calendar" className="muted" /> {t('Timeline')}</h2>
        <div className="muted" style={{ fontSize: 'var(--t-md)' }}>{t('{n} months · newest on top. Click a month to expand to days, click a day to see facts.', { n: months.length })}</div>
      </div>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        {years.map((y) => <a key={y.year} href={'#y' + y.year} className="chip" onClick={(e) => { e.preventDefault(); document.getElementById('y' + y.year)?.scrollIntoView({ block: 'start', behavior: 'smooth' }) }}>{y.year}</a>)}
      </div>
      {years.map((y) => (
        <div key={y.year} id={'y' + y.year} className="tl-year">
          <div className="tl-year-label">{y.year}</div>
          {y.months.map((m) => {
            const open = openMonth === m.month
            const dmax = Math.max(1, ...m.days.map((d) => sq(d.facts)))
            return (
              <div key={m.month} className={'tl-month' + (open ? ' open' : '')}>
                <div className="tl-row" {...clickable(() => setOpenMonth(open ? null : m.month))} aria-expanded={open}>
                  <span className="tl-label">{t('Month {m}', { m: m.month.slice(5) })}</span>
                  <span className="tl-bar"><span style={{ width: `${(sq(m.facts) / max) * 100}%` }} /></span>
                  <span className="tl-num muted">{t('{n} items · {u} meetings', { n: m.facts, u: m.units })}</span>
                </div>
                {open && (
                  <div className="tl-days">
                    {m.days.map((d) => (
                      <div key={d.date}>
                        <div className={'tl-row day' + (openDay === d.date ? ' open' : '')} {...clickable(() => setOpenDay(openDay === d.date ? null : d.date))} aria-expanded={openDay === d.date}>
                          <span className="tl-label">{d.date.length >= 10 ? t('Day {d}', { d: d.date.slice(8) }) : t('Unknown date')}</span>
                          <span className="tl-bar"><span style={{ width: `${(sq(d.facts) / dmax) * 100}%` }} /></span>
                          <span className="tl-num muted">{t('{n} items', { n: d.facts })}{d.units ? t(' · {u} meetings', { u: d.units }) : ''}</span>
                        </div>
                        {openDay === d.date && (
                          <div className="tl-facts">
                            {dayFacts[d.date] ? <FactList facts={dayFacts[d.date]} actions={actions} showTopics /> : <span className="spinner" />}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
