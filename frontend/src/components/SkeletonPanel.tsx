import { splitBeatLabel } from '../util/sectionStatus'
import { t } from '../i18n'

type Props = {
  spine: string
  beats: string[]
  /** The overall beat-coverage score after each Smart Continue round runs writer_harness.evaluate()
   * (0/1/2, note is the model's one-line explanation) -- null means no scoring has run yet
   * (outline just generated, or magic tap was used rather than Smart Continue). This is one aggregate score,
   * not a per-beat coverage list: there used to be a per-beat check based on beats_coverage_user(),
   * now that judgment is absorbed into the unified principle-scoring loop (see
   * writer_harness/README.md); the price is that the beat list no longer marks
   * each item's ticked state separately, replaced by the aggregate score + one-line explanation. */
  beatCoverage: { level: number; note: string } | null
  /** Deterministic check results for the outline (backend `harness/checks/skeleton.py`, plan 4.3).
   *
   * **Judged but not blocking persistence**, same tier as slides: the outline is a one-shot product, not part of the multi-round
   * loop, so these only sit beside the product, and whether to regenerate is the user's call.
   *
   * Why the outline needs judging: it is the **most upstream step of the whole writing loop, and the only one without a loop**,
   * and the continue step's `spine_fidelity` measured capped at 1.88-1.96 -- with a wrong plan,
   * "on topic" and "beat coverage" can both score full marks while the note is bad. */
  notes?: string[]
  loading: boolean
  onRun: () => void

  onStop?: () => void
  /** A beat marked "written (from body line N)": clicking the status badge jumps to that line */
  onJumpLine?: (line: number) => void
}

const LEVEL_LABEL: Record<number, string> = { 0: 'Not enough', 1: 'Partly covered', 2: 'Covered' }
const LEVEL_COLOR: Record<number, string> = { 0: 'var(--del)', 1: 'var(--warn)', 2: 'var(--ins)' }

/** Line 1: core tension (spine) + structural beats. Also the input to magic tap and smart edit.
 * Beats are the rhetorical/narrative functions each part of the piece serves, not a content outline -- so no <ol>
 * numbering like a to-do list; a labeled list stresses "this is a functional slot". */
export default function SkeletonPanel({ spine, beats, beatCoverage, notes = [], loading, onRun, onStop, onJumpLine }: Props) {
  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>{t('Writing outline')}</h2>
        {}
        {loading && onStop
          ? <button onClick={onStop} title={t('Cancel this generation and reset the button; the text and existing outline stay')}><span className="spinner" /> {t('Stop')}</button>
          : <button onClick={() => onRun()} disabled={loading}>
              {loading ? <span className="spinner" /> : t('Generate outline')}
            </button>}
      </div>
      {!spine && beats.length === 0 && !loading && (
        <p className="muted">{t('No outline yet. Once generated it guides Smart edit and Continue.')}</p>
      )}
      {spine && (
        <p
          style={{
            margin: '10px 0',
            padding: '10px 12px',
            fontSize: 'var(--t-base)',
            fontStyle: 'italic',
            borderLeft: '3px solid var(--accent)',
            background: 'var(--card-alt)',
          }}
        >
          {spine}
        </p>
      )}
      {beats.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: '8px 0 0' }}>
          {}
          {beats.map((b, i) => {
            const { status, text, line } = splitBeatLabel(b)
            const chip = status === 'written' ? t('Written') : status === 'missing' ? t('To fill') : ''
            return (
              <li key={i} style={{ marginBottom: 6, fontSize: 'var(--t-md)', display: 'flex', gap: 6, alignItems: 'baseline' }}>
                {chip
                  ? (line && onJumpLine
                      ? <button className={'plan-state ' + status} title={t('From line {n} in the note; click to jump there', { n: line })} onClick={() => onJumpLine(line)}>{chip}</button>
                      : <span className={'plan-state ' + status} title={status === 'missing' ? t('Not in the note yet') : t('Already in the note')}>{chip}</span>)
                  : <span className="muted">·</span>}
                <span>{text}</span>
              </li>
            )
          })}
        </ul>
      )}
      {notes.length > 0 && (
        <ul style={{ margin: '10px 0 0', padding: '8px 10px 8px 24px', listStyle: 'disc',
                     background: 'var(--card-alt)', borderLeft: '3px solid var(--warn)',
                     fontSize: 'var(--t-sm)' }}>
          {notes.map((n, i) => (
            <li key={i} style={{ marginBottom: i === notes.length - 1 ? 0 : 6 }}>{n}</li>
          ))}
        </ul>
      )}
      {beatCoverage && (
        <p style={{ marginTop: 8, fontSize: 'var(--t-sm)', display: 'flex', gap: 6, alignItems: 'baseline' }}>
          <span style={{ color: LEVEL_COLOR[beatCoverage.level], fontWeight: 'var(--w-semi)' }}>
            {t('Beat coverage: ')}{t(LEVEL_LABEL[beatCoverage.level] ?? String(beatCoverage.level))}
          </span>
          <span className="muted">{beatCoverage.note}</span>
        </p>
      )}
    </div>
  )
}
