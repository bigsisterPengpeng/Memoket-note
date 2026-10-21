import { useCallback, useEffect, useRef, useState } from 'react'

import { journeyRetention, journeySetRetention, journeyWipeAll, type JourneyRetention } from '../api'
import { friendlyError } from '../util/friendlyError'
import { toast } from '../toast'
import Icon from './Icon'
import { t } from '../i18n'



/** Days in human words. `0` = keep forever. */
export function sayKeep(days: number): string {
  if (!days) return t('Keep forever')
  if (days % 30 === 0 && days >= 30) return t('{m} months ({days} days)', { m: days / 30, days })
  if (days % 7 === 0) return t('{w} weeks ({days} days)', { w: days / 7, days })
  return t('{n} days', { n: days })
}

/** Size in human words. **No "0.0 MB"** — that reads as broken rather than "nothing there". */
export function saySize(bytes: number): string {
  if (bytes <= 0) return t('No space used')
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

/** Before "Delete everything", say clearly what gets deleted. **A single "Are you sure?" doesn't count**:
 *  users need to know this touches how many days, segments, images, daily reports, and the memories in the knowledge base. */
export function wipeLines(r: JourneyRetention): string[] {
  const out = [t('{n} days of records (oldest {oldest})', { n: r.days, oldest: r.oldest || '—' }),
               t('{n} segments, {described} of them described', { n: r.segments, described: r.described })]
  if (r.thumbs) out.push(t('{n} thumbnails, plus any raw screenshots not yet deleted', { n: r.thumbs }))
  if (r.reports) out.push(t('{n} daily reports', { n: r.reports }))
  out.push(t('The memories extracted from these descriptions into the knowledge base'))
  out.push(t('{size} in total', { size: saySize(r.bytes) }))
  return out
}

export default function JourneyRetentionPanel({ onChanged }: { onChanged?: () => void }) {
  const [r, setR] = useState<JourneyRetention | null>(null)
  const [busy, setBusy] = useState(false)
  /** After "Delete everything" is pressed, first lay out what will be deleted — **the confirmation isn't a dialog, this block expands itself**:
   *  a system dialog fits only one sentence, while six lines are listed here. */
  const [confirming, setConfirming] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  const load = useCallback(() => { journeyRetention().then(setR).catch(() => setR(null)) }, [])
  useEffect(() => { load() }, [load])
  // This block lives at the bottom of the page: the six expanded lines are most likely off-screen, and without scrolling,
  // users who clicked "Delete everything" only see the button change, never reading "what will be deleted"
  useEffect(() => { if (confirming) box.current?.scrollIntoView({ block: 'end', behavior: 'smooth' }) }, [confirming])

  async function set(segment: number, thumb: number) {
    setBusy(true)
    try {
      const out = await journeySetRetention(segment, thumb)
      setR(out)
      const s = out.swept
      const gone = s?.days_removed?.length ?? 0
      // **Clean up right after changing, and say what was cleaned**: a privacy switch where you
      // "can't tell whether it took effect" is as good as none.
      toast(gone || s?.thumbs_removed
        ? t('Retention updated — also cleared{what}', { what: `${gone ? ` ${t('{n} days', { n: gone })}` : ''}${s?.thumbs_removed ? ` ${t('{n} thumbnails', { n: s.thumbs_removed })}` : ''}${s?.facts_removed ? `${t(', ')}${t('{n} memories', { n: s.facts_removed })}` : ''}` })
        : t('Retention updated — nothing has expired yet'))
      onChanged?.()
    } catch (e) { toast(friendlyError(e), 'error') } finally { setBusy(false) }
  }

  async function wipe() {
    setBusy(true)
    try {
      const out = await journeyWipeAll()
      setR(out)
      setConfirming(false)
      const s = out.swept
      toast(t('Deleted {n} days of screen activity{tail}', { n: s?.days_removed?.length ?? 0, tail: s?.facts_removed ? t(', along with {n} memories', { n: s.facts_removed }) : '' }))
      onChanged?.()
    } catch (e) { toast(friendlyError(e), 'error') } finally { setBusy(false) }
  }

  if (!r) return null
  const fails = r.swept?.failures?.length ? r.swept.failures : (r.failures ?? [])

  return (
    <div className="journey-keep">
      <h3 className="kb-section-title">{t('Retention')}</h3>
      <p className="muted journey-keep-why">
        {t('Expired items delete themselves, ')}<b>{t('along with the memories extracted into the knowledge base')}</b>{t('. Currently on disk: ')}<b>{t('{days} days · {segs} segments · {size}', { days: r.days, segs: r.segments, size: saySize(r.bytes) })}</b>
        {r.oldest && t(' (oldest {oldest})', { oldest: r.oldest })}{t('.')}
      </p>

      <div className="journey-keep-rows">
        <label className="journey-keep-row">
          <span>{t('Segment descriptions')}</span>
          <select aria-label={t('How long to keep segment descriptions')} value={r.segment_days} disabled={busy}
                  onChange={(e) => void set(Number(e.target.value), r.thumb_days)}>
            {r.segment_choices.map((d) => <option key={d} value={d}>{sayKeep(d)}</option>)}
          </select>
          <span className="muted">{t('One-line description + timeline + that day’s report')}</span>
        </label>
        <label className="journey-keep-row">
          <span>{t('Thumbnails')}</span>
          <select aria-label={t('How long to keep thumbnails')} value={r.thumb_days} disabled={busy}
                  onChange={(e) => void set(r.segment_days, Number(e.target.value))}>
            {r.thumb_choices.map((d) => <option key={d} value={d}>{sayKeep(d)}</option>)}
          </select>
          <span className="muted">{t('The small image used to verify a description when reviewing')}</span>
        </label>
        {/* The large image is a tier with **no choice**: deleted as soon as the description is done; these 3 days are just a window for "the image
            machine keeps failing to connect". Shown because "where it's stored / how long it's kept" must match. */}
        <div className="journey-keep-row">
          <span>{t('Raw screenshots')}</span>
          <span className="journey-keep-fixed">{t('At most {n} days', { n: r.frame_days })}</span>
          <span className="muted">{t('Deleted as soon as described; kept at most this long if not')}</span>
        </div>
      </div>

      {fails.length > 0 && (
        <p className="journey-keep-fail">
          <Icon n="bx-error" /> {t('{n} files could not be deleted and are still on disk:', { n: fails.length })}
          {fails.slice(0, 5).map((f, i) => <span key={i} className="mono-line">{f}</span>)}
        </p>
      )}

      {confirming ? (
        <div className="journey-keep-confirm" ref={box}>
          <b>{t('Delete all screen activity? This will delete:')}</b>
          <ul>{wipeLines(r).map((l, i) => <li key={i}>{l}</li>)}</ul>
          <p className="muted">
            {t('Once deleted it is gone; there is no trash.')}
            <b>{t('The switch, exclusions and retention settings remain')}</b>{t(' — those are settings, not records.')}
          </p>
          <div className="row" style={{ gap: 6 }}>
            <button className="danger" disabled={busy} onClick={() => void wipe()}>
              {busy ? <span className="spinner" /> : <Icon n="bx-trash" />} {t('Delete these {n} days', { n: r.days })}
            </button>
            <button onClick={() => setConfirming(false)}>{t('Keep it')}</button>
          </div>
        </div>
      ) : (
        <button className="linklike danger" disabled={busy || !r.days}
                title={r.days ? '' : t('There are no records')}
                onClick={() => setConfirming(true)}>{t('Delete all')}</button>
      )}
    </div>
  )
}
