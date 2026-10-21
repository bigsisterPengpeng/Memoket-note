
import { t } from '../i18n'
const pad = (n: number) => String(n).padStart(2, '0')

export function fmtDate(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function fmtDateTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso.replace('T', ' ').slice(0, 16)
  return `${fmtDate(iso)} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}


/** "When" in a list: today gives the clock time, yesterday says yesterday, this year gives month-day, only earlier years give the full date.
 *
 *  When the sidebar sorts by recent, a date alone separates nothing -- "the one I wrote yesterday" and "the day before" both read
 *  the same `09-13`, and three written on the same day are completely identical (docs/sidebar-ia-plan.md §3).
 *  Resolution follows distance: the closer, the more the clock time matters; the farther, the more only the day matters.
 */
export function fmtWhen(iso: string, now: Date = new Date()): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10)
  const day = (x: Date) => `${x.getFullYear()}-${pad(x.getMonth() + 1)}-${pad(x.getDate())}`
  const hhmm = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (day(d) === day(now)) return t('Today {time}', { time: hhmm })
  const y = new Date(now); y.setDate(y.getDate() - 1)
  if (day(d) === day(y)) return t('Yesterday {time}', { time: hhmm })
  if (d.getFullYear() === now.getFullYear()) return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  return day(d)
}



export function whenLabel(dup: string | undefined, iso: string, now = new Date()): string {
  return dup && dup.includes(' ') ? dup : fmtWhen(iso, now)
}
