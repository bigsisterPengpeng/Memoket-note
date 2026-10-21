
import { useState, type RefObject } from 'react'
import type { EditorView } from '@codemirror/view'
import { acceptLayer, dropLayer, layersOf, settledOf, turnLayerOff, turnLayerOn } from '../editor/roundDiff'
import { runTitle, type RunHistory, type RunRound } from '../util/runRounds'
import { toast } from '../toast'
import { getLang, t } from '../i18n'
import { layerLabel } from '../util/changeLayers'
import type { WritingFeedback } from '../api'

const when = (at: number | string) => new Date(at).toLocaleTimeString(getLang() === 'zh' ? 'zh-CN' : 'en-US', { hour: '2-digit', minute: '2-digit' })

export default function ChangeLayersPanel({ viewRef, tick, runs = [], stuck = [], onRecomputeStuck, onDropStuck,
                                            onRestoreBefore, onUndoRound, busy = false, feedback }: {
  viewRef: RefObject<EditorView | null>
  tick: number
  /** Burned runs (`util/runRounds.groupRuns`), newest first */
  runs?: RunHistory[]

  stuck?: { id: string; label: string; why: string[] }[]
  onRecomputeStuck?: (id: string) => void
  onDropStuck?: (id: string) => void
  onRestoreBefore?: (r: RunRound) => void
  onUndoRound?: (r: RunRound) => void
  busy?: boolean
  feedback?: WritingFeedback | null
}) {
  void tick                                            // only to re-render after disposition
  const [, bump] = useState(0)
  const view = viewRef.current
  const layers = view ? layersOf(view) : []
  const settled = view ? settledOf(view) : []
  const settledOn = (id: number) => settled.find((x) => x.id === id)

  const settledOnly = settled.filter((x) => !layers.some((l) => l.id === x.id))
  const settledLines = settledOnly.map((x) => (
    <p key={x.id} className="muted layer-settled" style={{ fontSize: 'var(--t-xs)', margin: 0 }}>
      {layerLabel(x.label)} · {when(x.at)} · {t('Settled: {accepted} accepted, {reverted} reverted', { accepted: x.accepted, reverted: x.reverted })}
    </p>
  ))
  const toggle = (id: number, off: boolean) => {
    if (!view) return
    if (off) {
      const r = turnLayerOn(view, id)
      if (r.lost) toast(t('Re-applied {replayed}; {lost} could not be replayed because the text changed', { replayed: r.replayed, lost: r.lost }), 'error')
    } else {
      turnLayerOff(view, id)
    }
    bump((n) => n + 1)                                 // off / on is dispatched; React doesn't know
  }

  const stuckCards = stuck.length === 0 ? null : (
    <div className="stack layer-stuck" style={{ gap: 6 }}>
      <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>
        {t('The {n} layers below are left over from last time and ', { n: stuck.length })}<strong>{t('could not be put back')}</strong>{t(': the text was edited elsewhere and those places can no longer be located by content.')}
        <strong>{t('The text was not touched')}</strong>{t(' — either recompute against the current text, or drop it.')}
      </p>
      {stuck.map((s) => (
        <div key={s.id} className="card layer-card stuck" style={{ padding: '6px 10px' }}>
          <div className="row" style={{ gap: 8, alignItems: 'center' }}>
            <strong style={{ fontSize: 'var(--t-md)' }}>{layerLabel(s.label)}</strong>
            <span className="muted" style={{ fontSize: 'var(--t-xs)' }}>{t('{n} mismatches: {why}', { n: s.why.length, why: s.why.slice(0, 2).join(t('; ')) })}</span>
            <span style={{ marginInlineStart: 'auto', display: 'flex', gap: 4 }}>
              <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }}
                      title={t('Look for each of this layer’s edits in the current text again; what is found goes back into Changes')}
                      onClick={() => onRecomputeStuck?.(s.id)}>{t('Recompute this layer')}</button>
              <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }}
                      title={t('Drop this layer (the text is untouched; only this pending item goes away)')}
                      onClick={() => onDropStuck?.(s.id)}>{t('Drop this layer')}</button>
            </span>
          </div>
        </div>
      ))}
    </div>
  )
  return (
    <div className="stack" style={{ gap: 6 }}>
      {!!feedback?.decided && (
        <div className="card writing-feedback-summary" style={{ padding: '8px 10px' }}>
          <strong style={{ fontSize: 'var(--t-md)' }}>
            {t('Last time AI changed {total} places and you kept {kept}', { total: feedback.latest.accepted + feedback.latest.reverted, kept: feedback.latest.accepted })}
          </strong>
          <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '3px 0 0' }}>
            {t('Reverted {reverted}; kept {accepted} of the last {decided} decisions. The next Smart Continue will treat these decisions as writing constraints for this note.', { reverted: feedback.latest.reverted, decided: feedback.decided, accepted: feedback.accepted })}
          </p>
        </div>
      )}
      {!!feedback?.run_retention?.generated_chars && (
        <div className="card writing-feedback-summary" style={{ padding: '8px 10px' }}>
          <strong style={{ fontSize: 'var(--t-md)' }}>
            {t('You kept {pct}% of what the last Smart Continue added', { pct: feedback.run_retention.kept_percent })}
          </strong>
          <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '3px 0 0' }}>
            {t('{kept} / {total} chars', { kept: feedback.run_retention.kept_chars, total: feedback.run_retention.generated_chars })}
            {feedback.run_retention.changed_section ? t('; changes were mostly in “{section}”', { section: feedback.run_retention.changed_section }) : ''}{t('. This is the real outcome signal for the next tuning.')}
          </p>
        </div>
      )}
      {stuckCards}
      {!view || layers.length === 0
        ? <>
          {}
          <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>{t('AI edits are listed here as layers, one per action: accept or revert a whole layer.')}{stuck.length ? t('Apart from the layers above, there are no pending changes.') : t('No pending changes right now.')}</p>
          {settledLines}
        </>
        : <>
          <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>{t('{n} layers, oldest first. Turn a layer off to compare before/after; “Accept” finalizes, “Discard” restores the original.', { n: layers.length })}</p>
          {layers.map((l, i) => (
            <div key={l.id} className={'card layer-card' + (l.off ? ' off' : '')} style={{ padding: '6px 10px' }}>
              <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                <button className={'switch' + (l.off ? '' : ' on')} role="switch" aria-checked={!l.off} title={l.off ? t('Turn this layer on: write its edits back') : t('Turn this layer off: restore each place to before the edit; can be turned on again anytime')} onClick={() => toggle(l.id, l.off)}><span /></button>
                <strong style={{ fontSize: 'var(--t-md)' }}>{layerLabel(l.label)} {layers.filter((x) => x.label === l.label).length > 1 ? '①②③④⑤⑥⑦⑧⑨'[layers.filter((x, j) => x.label === l.label && j <= i).length - 1] ?? '' : ''}</strong>
                <span className="muted" style={{ fontSize: 'var(--t-xs)' }}>{when(l.at)} · {t('{n} places', { n: l.count })}{(() => { const x = settledOn(l.id); return x ? ` · ${t('settled: {accepted} accepted / {reverted} reverted', { accepted: x.accepted, reverted: x.reverted })}` : '' })()}</span>
                <span style={{ marginInlineStart: 'auto', display: 'flex', gap: 4 }}>
                  {!l.off && <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} title={t('Keep everything this layer changed (finalize)')} onClick={() => view.dispatch({ effects: acceptLayer.of(l.id) })}>{t('Accept')}</button>}
                  <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} title={l.off ? t('Forget this layer (the text is already the original)') : t('Restore every place this layer changed and forget it')} onClick={() => dropLayer(view, l.id)}>{l.off ? t('Discard') : t('Revert')}</button>
                </span>
              </div>
            </div>
          ))}
          {settledLines}
        </>}
      {runs.length > 0 && (
        <div className="stack run-history" style={{ gap: 6, marginTop: layers.length ? 10 : 4 }}>
          <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>{t('Rounds remain after being baked into the text: “Back to before this round” restores that version (saving one first); “Undo only this round” reverses its edits on the current text, keeping other rounds.')}</p>
          {runs.map((run, ri) => (
            <details key={run.run_id} className="run-card" open={ri === 0}>
              <summary className="run-title"><strong>{runTitle(run)}</strong><span className="muted" style={{ fontSize: 'var(--t-xs)' }}> · {when(run.at)}</span></summary>
              <div className="stack" style={{ gap: 4, marginTop: 4 }}>
                {run.rounds.map((r) => {
                  const delta = r.after ? r.after.chars - r.before.chars : null
                  return (
                    <div key={r.before.id} className="card run-round" style={{ padding: '5px 10px' }}>
                      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                        <strong style={{ fontSize: 'var(--t-md)' }}>{t('Round {n}', { n: r.round_no })}</strong>
                        <span className="muted" style={{ fontSize: 'var(--t-xs)' }}>{when(r.before.created_at)}{delta == null ? ` · ${t('not finished')}` : ` · ${t('{n} chars', { n: `${delta >= 0 ? '+' : ''}${delta}` })}`}</span>
                        <span style={{ marginInlineStart: 'auto', display: 'flex', gap: 4 }}>
                          <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} disabled={busy}
                                  title={t('Restore the text to before round {n} began (this and later rounds are gone; the current text is saved as a version first, so you can come back)', { n: r.round_no })}
                                  onClick={() => onRestoreBefore?.(r)}>{t('Back to before this round')}</button>
                          <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} disabled={busy || !r.after}
                                  title={r.after ? t('Undo only round {n}’s edits, keeping other rounds; mismatches will be reported', { n: r.round_no }) : t('This round is not finished; there is no “after” to compare')}
                                  onClick={() => onUndoRound?.(r)}>{t('Undo only this round')}</button>
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </details>
          ))}
        </div>
      )}
    </div>
  )
}
