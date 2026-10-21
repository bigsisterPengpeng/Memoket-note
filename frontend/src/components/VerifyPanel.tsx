import { useState } from 'react'
import { factSources, VERDICT, type Verdict } from '../api'
import type { SourceLine, VerifyFinding } from '../api'
import { clickable } from '../util/clickable'
import Icon from './Icon'
import { t } from '../i18n'

const VERDICT_STYLE: Record<Verdict, string> = {
  [VERDICT.contradicts]: 'badge', // reuse the plain badge styling but color via inline style below
  [VERDICT.supports]: 'badge ok',
  [VERDICT.unknown]: 'badge',
}
/** What each backend verdict is called in the UI. */
const VERDICT_LABEL: Record<Verdict, string> = {
  [VERDICT.contradicts]: 'Contradicts',
  [VERDICT.supports]: 'Supports',
  [VERDICT.unknown]: 'Inconclusive',
}


export function emptyVerifyLine(checked: number, unparsed: boolean): string {
  if (unparsed) {
    return checked > 0
      ? t('The model did not answer in the required format, so this passage could not be verified — the knowledge base has {n} related records; click “Verify” again.', { n: checked })
      : t('The model did not answer in the required format, so this passage could not be verified — click “Verify” again.')
  }
  if (checked <= 0) {
    return t('No record supports or contradicts this passage — that does not mean it is correct, only that the knowledge base has nothing related.')
  }
  return t('Checked {n} related knowledge base records; none supports or contradicts this passage — that does not mean it is correct.', { n: checked })
}


export const VERIFY_PASSAGE_CHARS = 40

export function verifyScopeLine(passage: string, gone = false): string {
  const p = (passage || '').replace(/\s+/g, ' ').trim()
  if (!p) return ''
  const head = p.length > VERIFY_PASSAGE_CHARS ? p.slice(0, VERIFY_PASSAGE_CHARS) + '…' : p
  return t('About the passage you selected: “{head}”', { head }) + (gone ? t(' — the text has changed since; this passage is no longer in the note.') : '')
}


export function passageLine(content: string, passage: string): number | null {
  const p = (passage || '').trim()
  if (!p || !content) return null
  const first = content.indexOf(p)
  if (first < 0) return null
  if (content.indexOf(p, first + 1) >= 0) return null      // more than one: do not guess
  // The number of `\n` is the number of lines before it; line numbers are 1-based, aligned with CodeMirror's `doc.line(n)`
  let line = 1
  for (let i = 0; i < first; i++) if (content[i] === '\n') line++
  return line
}

/** Verify result: the same "click to expand the source" pattern as TapProvenance; a judgment with no traceable
 * evidence is just another claim by the model -- especially "contradiction", a judgment that makes users doubt what they
 * wrote; it must be verifiable by the user, not just a one-line conclusion to trust. */
export default function VerifyPanel({ findings, checked = 0, unparsed = false, passage = '', gone = false, onJump, onClose }: {
  findings: VerifyFinding[]
  checked?: number
  unparsed?: boolean
  /** The original words of the passage selected at the time. The card must show it -- see `verifyScopeLine`. */
  passage?: string
  /** Whether this passage is still in the body (judged by the caller against the current body, not guessed). */
  gone?: boolean

  onJump?: () => void
  onClose: () => void
}) {
  const [openId, setOpenId] = useState<string | null>(null)
  const [lines, setLines] = useState<SourceLine[]>([])
  const [loading, setLoading] = useState(false)

  async function toggle(factId: string) {
    if (openId === factId) { setOpenId(null); return }
    setOpenId(factId)
    setLoading(true)
    try { setLines(await factSources(factId)) } catch { setLines([]) } finally { setLoading(false) }
  }

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>{t('Verification')}</h2>
        <button className="icon-btn" title={t('Close (Esc)')} aria-label={t('Close')} onClick={onClose}><Icon n="bx-x" /></button>
      </div>
      {!!verifyScopeLine(passage, gone) && (
        <p className="muted verify-scope" style={{ margin: '2px 0 6px', fontSize: 'var(--t-sm)' }}>
          {onJump
            ? <span className="scope-jump" title={t('Jump back to this passage')} {...clickable(onJump)}>{verifyScopeLine(passage, gone)}</span>
            : verifyScopeLine(passage, gone)}
        </p>
      )}
      {findings.length === 0 && (
        <p className="muted">{emptyVerifyLine(checked, unparsed)}</p>
      )}
      {findings.map((f, i) => (
        <div className="card" key={i}>
          <span
            className={VERDICT_STYLE[f.verdict]}
            style={f.verdict === VERDICT.contradicts ? { background: 'var(--del-bg)', color: 'var(--del)' } : undefined}
          >
            {t(VERDICT_LABEL[f.verdict] ?? f.verdict)}
          </span>
          <p style={{ margin: '6px 0 0' }}>{f.reason}</p>
          {f.fact_id && (
            <>
              <a className="link" style={{ fontSize: 'var(--t-sm)' }} onClick={() => toggle(f.fact_id)}>
                {t('Source: ')}{f.fact_text} {openId === f.fact_id ? t(' (hide original)') : t(' (view original)')}
              </a>
              {openId === f.fact_id && (
                <div className="card" style={{ marginTop: 4 }}>
                  {loading ? <span className="spinner" /> : lines.length === 0 ? (
                    <span className="muted">{t('Original text not found')}</span>
                  ) : lines.map((l) => (
                    <p key={l.id} style={{ margin: '2px 0', fontSize: 'var(--t-sm)' }}>
                      {l.who && <strong>{l.who}: </strong>}{l.text}
                    </p>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      ))}
    </div>
  )
}
