import { useCallback, useEffect, useState } from 'react'

import { decideEntityMerge, entityMergeCandidates, undoEntityMerge,
         type EntityMergeCandidate, type EntityMergeDecision } from '../../api'
import { toast, toastAction } from '../../toast'
import { t } from '../../i18n'


const WHY: Record<string, string> = {
  initials: 'initials', translit: 'transliteration', spelling: 'similar spelling', substring: 'one contains the other',   // i18n-ignore (data table; translated at display)
}

export default function EntityMerges({ onDone }: { onDone?: () => void }) {
  const [rows, setRows] = useState<EntityMergeCandidate[] | null>(null)
  const [decided, setDecided] = useState(0)
  const [busy, setBusy] = useState('')

  const load = useCallback(() => {
    entityMergeCandidates().then((d) => { setRows(d.candidates); setDecided(d.decided) })
      .catch(() => setRows([]))
  }, [])
  useEffect(load, [load])

  async function decide(c: EntityMergeCandidate, d: EntityMergeDecision) {
    const key = c.a + c.b
    setBusy(key)
    try {
      await decideEntityMerge(c.a, c.b, d, c.why)
      // Remove it from the list once decided: don't refetch the whole table — the user is clicking in a row, and reordering would make things jump under their hand
      setRows((r) => (r ?? []).filter((x) => x.a + x.b !== key))
      setDecided((n) => n + 1)
      // **"Undo any time" needs somewhere to be honored.** Clicking through a screen, a misclick is common,
      // and the pair disappears from the list once decided — without this undo, that sentence would be false.
      const said = d === 'same' ? t('Merged: {a} + {b} → {n} facts', { a: c.name_a, b: c.name_b, n: c.facts_total })
        : d === 'drop_a' ? t('“{name}” is no longer an entity', { name: c.name_a })
          : d === 'drop_b' ? t('“{name}” is no longer an entity', { name: c.name_b })
            : d === 'unsure' ? t('Noted “Not sure”: {a} / {b}', { a: c.name_a, b: c.name_b })
              : t('Noted “Not the same”: {a} / {b}', { a: c.name_a, b: c.name_b })
      toastAction(said, t('Undo'), () => {
        void undoEntityMerge(c.a, c.b).then(() => {
          setRows((r) => [c, ...(r ?? [])])       // put back at the top; the user was just looking at it
          setDecided((n) => Math.max(0, n - 1))
          onDone?.()
        }).catch((e) => toast(e instanceof Error ? e.message : String(e), 'error'))
      }, 7000)
      onDone?.()
    } catch (e) { toast(e instanceof Error ? e.message : String(e), 'error') } finally { setBusy('') }
  }

  if (rows === null) return <p className="muted" style={{ fontSize: 'var(--t-sm)' }}>…</p>
  if (!rows.length) {
    return (
      <p className="muted" style={{ fontSize: 'var(--t-md)' }}>
        {t('Nothing left to judge')}{decided ? t(' ({n} pairs judged)', { n: decided }) : ''}{t('. You can scan again after new content is added to the library.')}
      </p>
    )
  }

  return (
    <div className="stack">
      <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>
        {t('{n} pairs may be the same thing', { n: rows.length })}{decided ? t(' · {n} pairs judged', { n: decided }) : ''}{t('.')}
        <b>{t('Merging only affects display and retrieval; the knowledge base itself is untouched, and it can be undone any time.')}</b>
      </p>
      {rows.map((c) => (
        <div key={c.a + c.b} className="card merge-card">
          <div className="merge-head">
            <span className="merge-side"><b>{c.name_a}</b> <span className="muted">{t('{n} items', { n: c.facts_a })}</span></span>
            <span className="muted merge-eq">=?</span>
            <span className="merge-side"><b>{c.name_b}</b> <span className="muted">{t('{n} items', { n: c.facts_b })}</span></span>
            <span className="badge">{WHY[c.why] ? t(WHY[c.why]) : c.why}</span>
            <span style={{ flex: 1 }} />
            <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('{n} after merging', { n: c.facts_total })}</span>
          </div>

          {c.both.length > 0 ? (
            <div className="merge-both">
              <span className="muted">{t('Both names appear together in this sentence:')}</span>
              {c.both.map((s, i) => <p key={i}>{s}</p>)}
            </div>
          ) : (
            <p className="muted merge-none">{t('These two names never appeared together — there\'s no evidence either way.')}</p>
          )}

          <div className="merge-samples">
            <div><span className="muted">{c.name_a}{t(': ')}</span>{(c.sample_a[0] ?? t('(no original quote)'))}</div>
            <div><span className="muted">{c.name_b}{t(': ')}</span>{(c.sample_b[0] ?? t('(no original quote)'))}</div>
          </div>

          {}
          <div className="row" style={{ gap: 6, marginTop: 8 }}>
            <button className="primary" disabled={!!busy} onClick={() => void decide(c, 'same')}>{t('Same thing')}</button>
            <button disabled={!!busy} onClick={() => void decide(c, 'different')}>{t('Not the same')}</button>
            <button disabled={!!busy} onClick={() => void decide(c, 'unsure')}
                    title={t('When neither side has evidence, this is a legitimate answer — noted and not asked again, but kept apart from “Not the same”')}>{t('Not sure')}</button>
          </div>
          <div className="row merge-drops" style={{ gap: 10 }}>
            <span className="muted">{t('If one of them shouldn\'t count as an entity at all:')}</span>
            <button className="linklike link" disabled={!!busy} onClick={() => void decide(c, 'drop_a')}>{c.name_a}</button>
            <button className="linklike link" disabled={!!busy} onClick={() => void decide(c, 'drop_b')}>{c.name_b}</button>
          </div>
        </div>
      ))}
    </div>
  )
}
