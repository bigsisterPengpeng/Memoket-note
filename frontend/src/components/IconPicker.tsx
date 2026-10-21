/** Note icon picker (a trimmed version of the panel Trilium's NoteIcon opens): a grid of boxicons, click one to set it,
 *  "Default" clears it. Hangs below the title row's icon; click outside / Esc closes. */
import { useEffect, useRef } from 'react'
import Icon from './Icon'
import { t } from '../i18n'

/** A small set enough for daily use; no search — Trilium's 1500-icon search panel is over-design for a note app. */
export const NOTE_ICONS = [
  'bx-note', 'bx-folder', 'bx-book', 'bx-bookmark', 'bx-star', 'bx-heart', 'bx-flag', 'bx-pin',
  'bx-calendar', 'bx-time-five', 'bx-task', 'bx-check-square', 'bx-list-ul', 'bx-bulb', 'bx-target-lock', 'bx-rocket',
  'bx-briefcase', 'bx-buildings', 'bx-group', 'bx-user', 'bx-chat', 'bx-conversation', 'bx-phone', 'bx-envelope',
  'bx-code-alt', 'bx-chip', 'bx-cog', 'bx-wrench', 'bx-bar-chart-alt-2', 'bx-line-chart', 'bx-dollar-circle', 'bx-cart',
  'bx-home', 'bx-map', 'bx-paper-plane', 'bx-car', 'bx-coffee', 'bx-food-menu', 'bx-dumbbell', 'bx-leaf',
  'bx-image', 'bx-music', 'bx-camera', 'bx-palette', 'bx-pencil', 'bx-paint', 'bx-brain', 'bx-lock',
]

export default function IconPicker({ current, onPick, onClose }: {
  current: string
  onPick: (icon: string) => void
  onClose: () => void
}) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const cur = box.current?.querySelector<HTMLButtonElement>('.icon-picker-cell.active') ?? box.current?.querySelector<HTMLButtonElement>('.icon-picker-cell')
    cur?.focus()
  }, [])
  useEffect(() => {
    const onDown = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) onClose() }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onClose() } }
    document.addEventListener('mousedown', onDown, true)
    window.addEventListener('keydown', onKey, true)
    return () => { document.removeEventListener('mousedown', onDown, true); window.removeEventListener('keydown', onKey, true) }
  }, [onClose])
  return (
    <div ref={box} className="icon-picker" role="dialog" aria-label={t('Choose icon')}>
      {/* Keyboard: arrow keys move within the 8-column grid, Enter / Space selects (native button); Tab still follows DOM order */}
      <div className="icon-picker-grid" onKeyDown={(e) => {
        const cells = Array.from(box.current?.querySelectorAll<HTMLButtonElement>('.icon-picker-cell') ?? [])
        const i = cells.indexOf(document.activeElement as HTMLButtonElement)
        if (i < 0) return
        const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 8, ArrowUp: -8 }[e.key]
        if (step === undefined) return
        e.preventDefault()
        cells[Math.max(0, Math.min(cells.length - 1, i + step))]?.focus()
      }}>
        {NOTE_ICONS.map((ic) => (
          <button key={ic} type="button" className={'icon-picker-cell' + (ic === current ? ' active' : '')} title={ic.replace(/^bxs?-/, '')}
                  onClick={() => onPick(ic)}><Icon n={ic} /></button>
        ))}
      </div>
      <div className="icon-picker-foot">
        <button type="button" className="chip chip-action" disabled={!current} title={current ? t('Clear the icon and go back to the default') : t('Already the default icon')} onClick={() => onPick('')}><Icon n="bx-reset" /> {t('Default')}</button>
      </div>
    </div>
  )
}
