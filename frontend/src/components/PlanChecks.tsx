
import { useMemo } from 'react'
import { checkDone, doneSummary } from '../util/doneChecks'
import { t } from '../i18n'

export default function PlanChecks({ done, content, checked, onToggle, onEdit }: {
  done: string
  content: string
  /** Item texts the user has ticked */
  checked: string[]
  onToggle: (text: string, on: boolean) => void
  /** "Done criteria" still empty: click to open the writing mode settings */
  onEdit?: () => void
}) {
  const items = useMemo(() => checkDone(done, content, checked), [done, content, checked])
  const sum = doneSummary(items)
  if (items.length === 0) {
    return (
      <div>
        <h2>{t('Must satisfy')}</h2>
        <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>
          {t('No “Must satisfy” set in the writing task yet. It is optional; the AI writes to these requirements, checkable ones show results and you confirm the rest.')}
          {onEdit && <> <a href="#" onClick={(e) => { e.preventDefault(); onEdit() }}>{t('Set in Writing mode')}</a></>}
        </p>
      </div>
    )
  }
  const MARK: Record<string, { glyph: string; title: string }> = {
    pass: { glyph: '✓', title: t('Auto check: satisfied') },
    fail: { glyph: '✗', title: t('Auto check: not yet satisfied') },
  }
  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h2 style={{ margin: 0 }}>{t('Must satisfy')}</h2>
        <span className={'plan-check-sum' + (sum.failing ? ' fail' : sum.ok === sum.total ? ' ok' : '')} title={t('Confirmed / total. Passed auto checks and items you confirmed both count as done.')}>
          {sum.ok}/{sum.total}
        </span>
      </div>
      <ul className="plan-checks">
        {items.map((it) => (
          <li key={it.text} className={'plan-check ' + it.status}>
            {it.status === 'manual' ? (
              <label className="plan-check-row">
                <input type="checkbox" checked={it.checked} onChange={(e) => onToggle(it.text, e.target.checked)}
                       title={t('The AI follows this while writing, but the system cannot reliably verify it; tick it once you have confirmed')} />
                <span className="plan-check-text">{it.text}</span>
                <span className="badge">{t('Needs your confirmation')}</span>
              </label>
            ) : (
              <div className="plan-check-row" title={MARK[it.status].title}>
                <span className={'plan-check-mark ' + it.status} aria-label={MARK[it.status].title}>{MARK[it.status].glyph}</span>
                <span className="plan-check-text">{it.text}</span>
              </div>
            )}
            {it.why && <div className="plan-check-why muted">{it.why}</div>}
            {it.status === 'manual' && !it.checked && <div className="plan-check-why muted">{t('The AI writes to this; the system cannot reliably verify it — confirm when done')}</div>}
          </li>
        ))}
      </ul>
    </div>
  )
}
