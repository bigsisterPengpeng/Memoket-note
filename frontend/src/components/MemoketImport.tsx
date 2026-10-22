import { useId, useState } from 'react'
import { memoketAvailable, memoketImport, memoketRead } from '../api'
import type { JobOut } from '../api'
import { friendlyError } from '../util/friendlyError'
import { t } from '../i18n'
import { memoketMatches, type RecordingMatch } from '../util/memoketResults'
import { ConnectionStatus, useConnectionAvailability } from './ConnectionAvailability'

export default function MemoketImport({ to, disabled, onImported }: {
  to: 'notes' | 'both' | 'kb'; disabled: boolean; onImported: (job: JobOut) => void
}) {
  const [query, setQuery] = useState('')
  const [recordingId, setRecordingId] = useState('')
  const [title, setTitle] = useState('')
  const [result, setResult] = useState('')
  const [matches, setMatches] = useState<RecordingMatch[]>([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const { state, retry } = useConnectionAvailability(memoketAvailable)
  const statusId = useId()

  async function run(action: () => Promise<void>) {
    setBusy(true)
    setMessage('')
    try { await action() } catch (error) { setMessage(friendlyError(error)) }
    finally { setBusy(false) }
  }

  return <details className="memoket-import card">
    <summary><strong>{t('Memoket recordings')}</strong> — {t('Bring a conversation into your next draft')}</summary>
    <p className="muted">{t('Use the official Memoket CLI login on the machine running this workspace. Search your recordings, then import a selected brief as a local source. Nothing is written back to Memoket.')}</p>
    <p><code>npm install -g @memoket-ai/cli</code><br /><code>memoket login</code></p>
    <ConnectionStatus id={statusId} name="Memoket CLI" state={state} onRetry={retry} disabled={busy} />
    {state.status === 'ready' && <p className="muted">{t('CLI found. Search to check your existing Memoket login.')}</p>}
    {state.status === 'unavailable' && <p className="muted">{t('A Docker workspace cannot use your host Memoket login. Use the native app for this connection.')}</p>}
    <fieldset className="memoket-fields" disabled={busy || state.status !== 'ready'}
      aria-label={t('Search and import Memoket recordings')} aria-describedby={statusId}>
    <div className="memoket-import-row">
      <input aria-label={t('Search Memoket recordings')} placeholder={t('Search a project, decision or conversation')}
        value={query} onChange={(e) => setQuery(e.target.value)} />
      <button disabled={busy || !query.trim()} onClick={() => void run(async () => {
        setResult('')
        setMatches([])
        setRecordingId('')
        setTitle('')
        const data = await memoketRead('search_recordings', { query: query.trim() })
        setResult(JSON.stringify(data, null, 2))
        setMatches(memoketMatches(data))
      })}>{busy ? t('Working…') : t('Search recordings')}</button>
    </div>
    {matches.length > 0 && <ul className="memoket-matches" aria-label={t('Matching recordings')}>
      {matches.map((match) => <li key={match.id}>
        <button aria-pressed={recordingId === match.id} onClick={() => {
          setRecordingId(match.id)
          setTitle(match.title || query.trim())
        }}>{match.title || t('Recording')} <span className="muted">{match.id}</span></button>
      </li>)}
    </ul>}
    {result && <details><summary>{t('Source response and recording IDs')}</summary>
      <pre className="memoket-results">{result}</pre></details>}
    <p className="muted">{t('Select a recording above or enter its conversation ID. Import keeps the source ID and preserves local edits on re-import. Briefs are summaries; read the transcript for exact wording.')}</p>
    <div className="memoket-import-row">
      <input aria-label={t('Memoket conversation ID')} placeholder="conversation_id" value={recordingId}
        onChange={(e) => setRecordingId(e.target.value)} />
      <input aria-label={t('Imported recording title')} placeholder={t('Title for the imported note')} value={title}
        onChange={(e) => setTitle(e.target.value)} />
      <button disabled={busy || disabled || !recordingId.trim() || !title.trim()} onClick={() => void run(async () => {
        const job = await memoketImport(recordingId.trim(), title.trim(), to)
        onImported(job)
        setMessage(t('Import queued. Follow its progress below.'))
      })}>{t('Import selected brief')}</button>
    </div>
    <p className="muted">{t('Uses the Import to choice above. Knowledge extraction sends the selected report to your configured model; notes-only import skips extraction. The source recording date is not inferred.')}</p>
    </fieldset>
    {message && <p role="status">{message}</p>}
  </details>
}
