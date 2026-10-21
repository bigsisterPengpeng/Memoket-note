/** Conflict inbox (docs/agent-native-editor.md §3.3.1): "new fact vs old fact" detected at ingest;
 *  the user clicks "New replaces old" / "Old one counts" / "Keep both", instead of silently storing. */
import { useEffect, useState } from 'react'
import { clickable } from '../../util/clickable'

import { kbConflicts, resolveConflict, type KbConflict } from '../../api'
import { toast } from '../../toast'
import { KbSection, type KbActions } from './KbBits'
import Icon from '../Icon'
import { t } from '../../i18n'

export default function ConflictInbox({ actions, onCount }: { actions: KbActions; onCount?: (n: number) => void }) {
  const [rows, setRows] = useState<KbConflict[] | null>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const load = () => kbConflicts().then((r) => { setRows(r.conflicts); onCount?.(r.open) }).catch(() => setRows([]))
  useEffect(() => { void load() }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  async function act(c: KbConflict, action: 'new_wins' | 'old_wins' | 'keep_both') {
    setBusy(c.id)
    try {
      await resolveConflict(c.id, action)
      toast(action === 'new_wins' ? t('New replaces old') : action === 'old_wins' ? t('Old one counts; the new one is marked superseded') : t('Keeping both'))
      await load()
    } catch (e) { toast(String(e), 'error') }
    finally { setBusy(null) }
  }
  if (!rows || rows.length === 0) return null
  const Side = ({ f, label }: { f: KbConflict['new']; label: string }) => (
    <div>
      <div className="muted" style={{ fontSize: 'var(--t-xs)' }}>{label} · {f.when || '—'}{f.note_id ? <> · <a href="#" onClick={(e) => { e.preventDefault(); actions.onOpenNote(f.note_id) }}>{t('From a note')}</a></> : null}</div>
      <div style={{ cursor: 'pointer' }} {...clickable(() => actions.onOpen('kb:fact:' + f.id))} title={t('Open this one')}>{f.text}</div>
    </div>
  )
  return (
    <KbSection title={t('Pending conflicts · {n}', { n: rows.length })} extra={<span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('New records that collided with old ones at ingest; one click decides which counts')}</span>}>
      <div className="stack conflict-inbox" style={{ gap: 6 }}>
        {rows.slice(0, 20).map((c) => (
          <div key={c.id} className="card" style={{ padding: '8px 10px' }}>
            <div style={{ fontSize: 'var(--t-md)' }}><Icon n="bx-error" style={{ color: 'var(--warn)' }} /> {c.say}</div>
            <div className="cf-side">
              <Side f={c.old} label={t('Old record')} />
              <Side f={c.new} label={t('New record')} />
            </div>
            <div className="row" style={{ gap: 4, marginTop: 6 }}>
              <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} disabled={busy === c.id} onClick={() => void act(c, 'new_wins')}>{t('New replaces old')}</button>
              <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} disabled={busy === c.id} onClick={() => void act(c, 'old_wins')}>{t('Old one counts')}</button>
              <button style={{ fontSize: 'var(--t-sm)', padding: '2px 8px' }} disabled={busy === c.id} onClick={() => void act(c, 'keep_both')}>{t('Keep both')}</button>
            </div>
          </div>
        ))}
      </div>
    </KbSection>
  )
}
