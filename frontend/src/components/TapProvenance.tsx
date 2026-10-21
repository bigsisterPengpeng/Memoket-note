import { useState } from 'react'
import { factSources, setMemoryScope } from '../api'
import type { SourceLine, TapMeta } from '../api'
import Icon from './Icon'
import { t } from '../i18n'

/**
 * Magic-tap's grounding claim ("cites the knowledge base") is worth nothing if it can't be
 * checked -- competitor research kept surfacing "AI says it found something
 * but I can't tell if it's right" as the trust-killer. Each cited fact here
 * expands to the actual source dialogue line it came from (same data
 * /api/memory/facts/{id}/sources already serves for the facts table), not
 * just the paraphrased fact text.
 */
/** Deterministic check results for the paragraph just written (backend `harness/checks/tap.py`, plan 8.1).
 *  **Judged but not blocking**: magic tap is meant to be "one click, a paragraph in seconds"; wrapping it in the full loop would turn it
 *  into Smart Continue. So these only sit under the sources row, and whether to redo is the user's call. */
function TapNotes({ notes }: { notes: string[] }) {
  if (notes.length === 0) return null
  return (
    <ul className="tap-notes">
      {notes.map((n, i) => (
        <li key={i} style={{ marginBottom: i === notes.length - 1 ? 0 : 4 }}>{n}</li>
      ))}
    </ul>
  )
}

export default function TapProvenance(
  { meta, notes = [], onDismiss }: { meta: TapMeta; notes?: string[]; onDismiss?: () => void },
) {
  const [openId, setOpenId] = useState<string | null>(null)

  // the user clicks "Sources" to expand.
  const [expanded, setExpanded] = useState(false)
  const [lines, setLines] = useState<SourceLine[]>([])
  const [loading, setLoading] = useState(false)

  async function toggle(id: string) {
    if (openId === id) { setOpenId(null); return }
    setOpenId(id)
    setLoading(true)
    try { setLines(await factSources(id)) } catch { setLines([]) } finally { setLoading(false) }
  }

  if (!meta.grounded) {
    return (
      <div className="muted tap-prov" style={{ fontSize: 'var(--t-sm)' }}>
        <p style={{ margin: 0 }}>
          <span className="badge">{t('Free continuation')}</span> {t('No related records in the knowledge base')}
          {onDismiss && <button className="icon-btn sm" title={t('Close')} onClick={onDismiss}><Icon n="bx-x" /></button>}
        </p>
        {}
        {meta.why_empty && (
          <p className="tap-why" style={{ margin: '4px 0 0' }}>
            {meta.why_empty}
            {meta.scope && meta.scope !== 'all' && meta.why_empty.includes('\u300c\u5168\u90e8\u300d\u91cc\u80fd\u53d6\u5230') && (
              <> <a className="link" onClick={() => setMemoryScope('all')}>{t('Switch to “All”')}</a>{t(', then click Continue again')}</>
            )}
          </p>
        )}
        <TapNotes notes={notes} />
      </div>
    )
  }

  return (
    <div className="muted tap-prov" style={{ fontSize: 'var(--t-sm)' }}>
      <p style={{ margin: '0 0 4px', display: 'flex', alignItems: 'center', gap: 6 }}>
        <span className="badge ok">{t('Cites knowledge base')}</span> {t('Retrieved {n} facts ({ms} ms)', { n: meta.facts, ms: Math.round(meta.recall_ms) })}
        <a className="link" onClick={() => setExpanded((v) => !v)}>
          {expanded ? t('Hide sources') : t('View sources')} <Icon n={(expanded ? 'bx-chevron-up' : 'bx-chevron-down')} />
        </a>
        <span style={{ flex: 1 }} />
        {onDismiss && <button className="icon-btn sm" title={t('Close')} onClick={onDismiss}><Icon n="bx-x" /></button>}
      </p>
      {expanded && meta.sources.slice(0, 6).map((s, i) => {
        const id = meta.fact_ids[i]
        return (
          <div key={id || i} style={{ marginBottom: 4 }}>
            <a className="link" onClick={() => id && toggle(id)}>{s}</a>
            {openId === id && (
              <div className="card" style={{ marginTop: 4 }}>
                {loading ? <span className="spinner" /> : lines.length === 0 ? (
                  <span>{t('Original text not found')}</span>
                ) : lines.map((l) => (
                  <p key={l.id} style={{ margin: '2px 0' }}>
                    {l.who && <strong>{l.who}: </strong>}{l.text}
                  </p>
                ))}
              </div>
            )}
          </div>
        )
      })}
      <TapNotes notes={notes} />
    </div>
  )
}
