import { useEffect, useState } from 'react'
import { friendlyError } from '../util/friendlyError'
import * as api from '../api'
import { toast } from '../toast'
import MarkdownEditor from './MarkdownEditor'
import { diffParts } from '../editor/roundDiff'
import Icon from './Icon'
import { historyGroups, revisionLabel } from '../util/runRounds'
import { t } from '../i18n'

function when(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * Ribbon "History": this note's revisions (Trilium's Note Revisions). When saving, if the body changed
 * and the last revision is more than ten minutes old, one is kept automatically; you can also "Save a revision" by hand. Click a revision to see its content;
 * before "Restore this revision" the backend saves the current body as another revision, so restoring is always reversible.
 */
export default function RevisionHistoryPanel({ noteId, currentChars, currentContent = '', onRestored, updatedAt }: {
  noteId: string
  /** When this note was last persisted: automatic revisions are kept by the server on save, so the list must re-query after persisting, or the new revision only shows after reopening the note */
  updatedAt?: string
  currentChars: number
  /** Current body: expanding a revision defaults to "compare with current" (what was deleted, what was added), not just the old full text */
  currentContent?: string
  onRestored: (n: api.Note) => void
}) {
  const [mode, setMode] = useState<'diff' | 'raw'>('diff')
  const [revs, setRevs] = useState<api.NoteRevision[] | null>(null)
  const [open, setOpen] = useState<(api.NoteRevision & { content: string }) | null>(null)
  const [busy, setBusy] = useState(false)

  const reload = () => api.listRevisions(noteId).then(setRevs).catch(() => setRevs([]))
  useEffect(() => { setOpen(null); void reload() }, [noteId])  // eslint-disable-line react-hooks/exhaustive-deps
  // Re-query the list once persisted; leave the expanded revision alone (the user may be looking at the comparison)
  useEffect(() => { if (updatedAt) void reload() }, [updatedAt])  // eslint-disable-line react-hooks/exhaustive-deps

  async function snapshot() {
    setBusy(true)
    try { await api.snapshotNote(noteId); await reload(); toast(t('Version saved')) }
    catch (e) { toast(t('Could not save version: {err}', { err: friendlyError(e) }), 'error') }
    finally { setBusy(false) }
  }
  async function view(r: api.NoteRevision) {
    if (open?.id === r.id) { setOpen(null); return }
    try { setOpen(await api.getRevision(noteId, r.id)) } catch (e) { toast(t('Could not load this version: {err}', { err: String(e) }), 'error') }
  }
  async function restore(r: api.NoteRevision) {
    setBusy(true)
    try {
      const n = await api.restoreRevision(noteId, r.id)
      onRestored(n); setOpen(null); await reload()
      toast(t('Restored the version from {when} (the content before restoring was saved as a version too)', { when: when(r.created_at) }))
    } catch (e) { toast(t('Restore failed: {err}', { err: friendlyError(e) }), 'error') }
    finally { setBusy(false) }
  }

  if (!revs) return <p className="muted" style={{ margin: 0 }}>…</p>
  return (
    <div className="stack" style={{ fontSize: 'var(--t-md)', gap: 8 }}>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
        <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>
          {revs.length === 0 ? t('No versions yet — a version is saved automatically every ten minutes after edits.') : t('{n} versions · currently {chars} chars', { n: revs.length, chars: currentChars })}
        </span>
        <span style={{ flex: 1 }} />
        <button className="chip chip-action" disabled={busy || !currentContent.trim()} title={!currentContent.trim() ? t('The note is empty; nothing to save') : undefined} onClick={snapshot}><Icon n="bx-bookmark-plus" /> {t('Save a version now')}</button>
      </div>
      {revs.length > 0 && (
        <div className="revision-list">
          {}
          {historyGroups(revs).map((g) => g.kind === 'rev' ? row(g.rev) : (
            <details key={'run:' + g.run_id} className="revision-run">
              <summary className="run-title">
                <Icon n="bx-git-compare" /> {t('Smart Continue · {n} rounds', { n: g.revs.filter((x) => x.reason === 'round').length })} · {when(g.revs[g.revs.length - 1].created_at)}
                <span className="muted" style={{ fontSize: 'var(--t-xs)' }}> · {t('A version before each round; expand to see')}</span>
              </summary>
              {g.revs.map(row)}
            </details>
          ))}
        </div>
      )}
    </div>
  )

  function row(r: api.NoteRevision) {
    return (
            <div key={r.id} className={'revision-row' + (open?.id === r.id ? ' open' : '')}>
              <a className="kb-link" onClick={() => void view(r)}>
                <Icon n={(open?.id === r.id ? 'bx-chevron-down' : 'bx-chevron-right')} />
                <span>{when(r.created_at)}</span>
                <span className="muted" style={{ fontSize: 'var(--t-xs)' }}>{revisionLabel(r)} · {t('{n} chars', { n: r.chars })}
                  {r.chars !== currentChars && <> · {r.chars > currentChars ? '+' : ''}{r.chars - currentChars}</>}</span>
                <span style={{ flex: 1 }} />
                <button className="chip chip-action" disabled={busy} onClick={(e) => { e.stopPropagation(); void restore(r) }}><Icon n="bx-undo" /> {t('Restore this version')}</button>
              </a>
              {open?.id === r.id && (
                <div className="revision-body">
                  <div className="row" style={{ gap: 6, marginBottom: 6 }}>
                    <button className={'chip' + (mode === 'diff' ? ' active' : '')} onClick={() => setMode('diff')}>{t('Compare with current')}</button>
                    <button className={'chip' + (mode === 'raw' ? ' active' : '')} onClick={() => setMode('raw')}>{t('Full text of this version')}</button>
                  </div>
                  {mode === 'raw'
                    ? <MarkdownEditor content={open.content} readOnly />
                    : <RevisionDiff from={open.content} to={currentContent} />}
                </div>
              )}
            </div>
    )
  }
}


/** Word-level diff old revision → current: red is what that revision had and is gone now; green is newly added.
 *  Same diffParts (big documents by line first, then by word), the same semantics as the round highlights in the editor. */
function RevisionDiff({ from, to }: { from: string; to: string }) {
  const parts = diffParts(from, to)
  const changed = parts.filter((p) => p.type !== 'keep')
  if (changed.length === 0) return <p className="muted" style={{ margin: 0, fontSize: 'var(--t-sm)' }}>{t('Identical to the current text (only whitespace differs).')}</p>
  // Fold long unchanged runs (keep only 120 characters of context before and after each change): changes are often in the middle of thousands of characters,

  const CTX = 120
  return (
    <div className="revision-diff">
      {parts.map((p, i) => {
        if (p.type !== 'keep') return <span key={i} className={p.type === 'ins' ? 'rd-ins' : 'rd-del'}>{p.text}</span>
        if (p.text.length <= CTX * 2 + 40) return <span key={i}>{p.text}</span>
        const head = i === 0 ? '' : p.text.slice(0, CTX)
        const tail = i === parts.length - 1 ? '' : p.text.slice(-CTX)
        const hidden = p.text.length - head.length - tail.length
        return <span key={i}>{head}<span className="rd-skip">{t('… {n} unchanged chars …', { n: hidden })}</span>{tail}</span>
      })}
    </div>
  )
}
