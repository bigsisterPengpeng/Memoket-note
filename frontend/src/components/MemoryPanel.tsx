import { useEffect, useRef, useState } from 'react'
import {
  cancelJob, ingestBatch, jobStatus, listJobs, memoryFacts, memoryStats, resumeImportJob, watchJob,
  importApple, importFeishu, importFiles, importNotion,
} from '../api'
import type { FactDetail, JobOut } from '../api'
import { getNote } from '../api'
import { toast } from '../toast'
import { friendlyError } from '../util/friendlyError'
import { landNotesInTray, TRAY_MAX_ITEMS } from '../util/tray'
import { trayByDefault } from '../util/trayDefaults'
import ExportBack from './ExportBack'
import FilePicker from './FilePicker'
import WritingFlow from './WritingFlow'
import MemoketImport from './MemoketImport'
import AppleNotesImport from './AppleNotesImport'
import { getLang, t } from '../i18n'

/** Notes produced by a finished import -> tray items (pure function): only those that became notes (`note_id` set, status done), one per note, capped at the tray limit */
export function importedTrayItems(items: { status: string; note_id?: string; filename: string }[]): { note_id: string; filename: string }[] {
  const seen = new Set<string>()
  const out: { note_id: string; filename: string }[] = []
  for (const it of items) {
    if (it.status !== 'done' || !it.note_id || seen.has(it.note_id)) continue
    seen.add(it.note_id)
    out.push({ note_id: it.note_id, filename: it.filename })
    if (out.length >= TRAY_MAX_ITEMS) break
  }
  return out
}


export async function landImportInTray(jobId: string, trayNoteId: string): Promise<number> {
  if (!trayByDefault()) return 0
  const j = await jobStatus(jobId)
  const landed = importedTrayItems(j.items)
  if (!landed.length) return 0
  if (!trayNoteId) { toast(t('Imported {n} notes; no note is open, so they were not added to this note\'s materials', { n: landed.length })); return 0 }
  const notes = await Promise.all(landed.map((l) => getNote(l.note_id).catch(() => null)))
  const n = await landNotesInTray(trayNoteId, landed.map((l, i) => ({
    id: l.note_id, title: notes[i]?.title || l.filename.replace(/\.[^.]+$/, ''), content: notes[i]?.content ?? '',
  })))
  if (n) toast(t('{n} imported notes were added to this note\'s materials; the AI will prefer them when writing this note', { n }))
  return n
}

const STATUS_LABEL: Record<string, string> = {
  queued: 'Queued', extracting: 'Extracting text', transcribing: 'Transcribing',
  chunking: 'Chunking', remembering: 'Extracting into the knowledge base', done: 'Done',
  failed: 'Failed', cancelled: 'Cancelled',

  // between chunks; when the model is stuck, this chunk may in the worst case wait 300 s x 3 retries ~ 15 minutes before it gets there
  // (measured `providers/llm.py`: timeout=300 / retries=2; pointed at an endpoint that accepts and never replies,
  // the 3 s x 2 tier raised ProviderError after 8.0 s). The status bar already says so; this follows.
  cancelling: 'Stopping... (waiting for this chunk\'s model call to finish)', interrupted: 'Interrupted (can resume)',
}

const fmtDur = (s: number) => (s < 60 ? t('{n} s', { n: s }) : s < 3600 ? t('{n} min', { n: Math.round(s / 60) }) : t('{n} h', { n: (s / 3600).toFixed(1) }))
const fmtTokens = (n: number) => (n >= 10000 ? (getLang() === 'zh' ? t('{n} ten-thousand', { n: (n / 10000).toFixed(1) }) : `${(n / 1000).toFixed(1)}k`) : String(n))

/** Progress bar + estimate + usage. Batch import is hours of work; before clicking and while it runs, the user should know how long it takes and how much it costs. */
function JobProgress({ j }: { j: JobOut }) {
  const total = j.chunks_total ?? 0
  const done = j.chunks_done ?? 0
  const running = j.status === 'running' || j.status === 'queued' || j.status === 'cancelling'
  return (
    <div className="stack" style={{ gap: 4, marginTop: 6 }}>
      {total > 0 && (
        <div className="progress" title={t('{done}/{total} chunks', { done, total })}><div className="progress-bar" style={{ width: `${Math.min(100, Math.round(done / total * 100))}%` }} /></div>
      )}
      <div className="muted" style={{ fontSize: 'var(--t-sm)' }}>
        {total > 0 && <>{t('{done}/{total} chunks', { done, total })}</>}
        {running && j.current && <> · {t('Processing "{name}"', { name: j.current })}</>}
        {running && (j.eta_s ?? 0) > 0 && <> · {t('about {dur} left', { dur: fmtDur(j.eta_s!) })}</>}
        {(j.elapsed_s ?? 0) > 0 && <> · {t('{dur} elapsed', { dur: fmtDur(j.elapsed_s!) })}</>}
        {(j.tokens_est ?? 0) > 0 && <> · {t('about {n} tokens', { n: fmtTokens(j.tokens_est!) })}</>}
      </div>
    </div>
  )
}

export default function MemoryPanel({ pendingJob, trayNoteId = '' }: { pendingJob: string; trayNoteId?: string }) {
  const [stats, setStats] = useState<{ facts: number; entities: number } | null>(null)
  const [job, setJob] = useState('')
  const [batchJob, setBatchJob] = useState<JobOut | null>(null)
  const batchAbort = useRef<AbortController | null>(null)
  const [notionToken, setNotionToken] = useState('')
  const [feishuAppId, setFeishuAppId] = useState('')
  const [feishuSecret, setFeishuSecret] = useState('')
  const [feishuScope, setFeishuScope] = useState<'wiki' | 'drive'>('wiki')
  // The paste-a-link path: documents shared with the app as a single-doc collaborator **can be read but not listed** (measured on a real account);
  // without this box the feature only works for "people who can grant the app permission on the wiki space".
  const [feishuDocs, setFeishuDocs] = useState('')
  const [importing, setImporting] = useState(false)
  // Where to import: extracting a vault of hundreds of notes into the knowledge base takes a long time, so let people choose
  const [importTo, setImportTo] = useState<'both' | 'kb' | 'notes'>('both')
  const [recentFacts, setRecentFacts] = useState<FactDetail[]>([])
  const lastSeenFactCount = useRef(-1)

  const refresh = () => memoryStats().then(setStats).catch(() => {})
  useEffect(() => { void refresh() }, [])
  // Imports interrupted by a service restart whose content was written to disk: list them with "Resume"
  const [interrupted, setInterrupted] = useState<JobOut[]>([])
  const loadInterrupted = () => listJobs(20).then((js) => setInterrupted(js.filter((j) => j.status === 'interrupted' && j.resumable))).catch(() => {})
  useEffect(() => { void loadInterrupted() }, [])
  async function doResume(j: JobOut) {
    try {
      const r = await resumeImportJob(j.job_id)
      setInterrupted((xs) => xs.filter((x) => x.job_id !== j.job_id))
      setBatchJob(r)
      watchJob(r.job_id, (x) => { setBatchJob(x); void pollRecentFacts(x.facts) }, () => { void refresh(); setRecentFacts([]); void loadInterrupted(); void landImportInTray(r.job_id, trayNoteId).catch((e) => toast(t('Could not add to this note\'s materials: ') + friendlyError(e), "error")) })
    } catch (e) { toast(t('Could not resume: ') + friendlyError(e), 'error') }
  }
  // Estimate before starting: how long this batch will run, roughly how many tokens
  function announceEstimate(r: JobOut) {
    const e = r.estimate
    if (e && e.chunks > 0) toast(t('{notes} notes · {chunks} chunks · about {dur} · about {tokens} tokens', { notes: r.items.length, chunks: e.chunks, dur: fmtDur(e.seconds), tokens: fmtTokens(e.tokens) }))
  }
  useEffect(() => () => batchAbort.current?.abort(), [])

  /** Extraction runs in chunks (one LLM call per chunk), and the facts count goes up
   * after each chunk -- follow that number here, and whenever it changes fetch the latest few facts,
   * giving a "see content while it extracts" effect instead of waiting for the whole job to finish and refreshing at once. */
  function pollRecentFacts(factCount: number) {
    if (factCount > 0 && factCount !== lastSeenFactCount.current) {
      lastSeenFactCount.current = factCount
      memoryFacts({ limit: 3 }).then((r) => setRecentFacts(r.facts)).catch(() => {})
    }
  }

  // Ingest is a background job; poll until done, then refresh the stats
  useEffect(() => {
    const id = pendingJob || job
    if (!id) return
    const timer = setInterval(async () => {
      try {
        const s = await jobStatus(id)
        pollRecentFacts(s.facts)
        if (s.status === 'done' || s.status === 'error') {
          clearInterval(timer)
          setJob('')
          setRecentFacts([])
          void refresh()
          if (s.status === 'error') toast(t('Ingest failed: {detail}', { detail: s.detail ?? '' }), 'error')
        }
      } catch { clearInterval(timer) }
    }, 3000)
    return () => clearInterval(timer)
  }, [pendingJob, job])



  async function doBatchIngest(files: FileList | null) {
    if (!files || files.length === 0) return
    batchAbort.current?.abort()
    const controller = new AbortController()
    batchAbort.current = controller
    const r = await ingestBatch(Array.from(files))
    setBatchJob(r)
    watchJob(r.job_id, (j) => { setBatchJob(j); pollRecentFacts(j.facts) },
      () => { void refresh(); setRecentFacts([]) }, controller.signal)
  }

  async function doImport(files: File[], source: 'obsidian' | 'evernote') {
    if (!files.length) return
    setImporting(true)
    try {
      const r = await importFiles(files, source, importTo)
      announceEstimate(r)
      setBatchJob(r)
      watchJob(r.job_id, (j) => { setBatchJob(j); pollRecentFacts(j.facts) },
        () => { void refresh(); setRecentFacts([]); void landImportInTray(r.job_id, trayNoteId).catch((e) => toast(t('Could not add to this note\'s materials: ') + friendlyError(e), "error")) })
    } catch (e) {

      toast(t('Import failed: ') + friendlyError(e), 'error')
    } finally {
      setImporting(false)
    }
  }

  async function doImportApple() {
    setImporting(true)
    try {
      const r = await importApple(importTo)
      announceEstimate(r)
      setBatchJob(r)
      watchJob(r.job_id, (j) => { setBatchJob(j); pollRecentFacts(j.facts) },
        () => { void refresh(); setRecentFacts([]); void landImportInTray(r.job_id, trayNoteId).catch((e) => toast(t('Could not add to this note\'s materials: ') + friendlyError(e), "error")) })
    } catch (e) {
      toast(t('Import failed: ') + friendlyError(e), 'error')
    } finally {
      setImporting(false)
    }
  }

  async function doImportNotion() {
    setImporting(true)
    try {
      const r = await importNotion(notionToken.trim(), importTo)
      announceEstimate(r)
      setBatchJob(r)
      watchJob(r.job_id, (j) => { setBatchJob(j); pollRecentFacts(j.facts) },
        () => { void refresh(); setRecentFacts([]); void landImportInTray(r.job_id, trayNoteId).catch((e) => toast(t('Could not add to this note\'s materials: ') + friendlyError(e), "error")) })
    } catch (e) {
      toast(t('Import failed: ') + friendlyError(e), 'error')
    } finally {
      setImporting(false)
    }
  }

  async function doImportFeishu() {
    setImporting(true)
    try {
      const r = await importFeishu(feishuAppId.trim(), feishuSecret.trim(), feishuScope, importTo, feishuDocs)
      announceEstimate(r)
      setBatchJob(r)
      watchJob(r.job_id, (j) => { setBatchJob(j); pollRecentFacts(j.facts) },
        () => { void refresh(); setRecentFacts([]); void landImportInTray(r.job_id, trayNoteId).catch((e) => toast(t('Could not add to this note\'s materials: ') + friendlyError(e), "error")) })
    } catch (e) {
      toast(t('Import failed: ') + friendlyError(e), 'error')
    } finally {
      setImporting(false)
    }
  }

  async function doCancelBatch() {
    if (!batchJob) return
    await cancelJob(batchJob.job_id)
  }

  const working = pendingJob || job

  return (
    <div>
      <div className="workspace-intro">
        <h2>{t('Bring your notes. Keep your workflow.')}</h2>
        <p className="muted">{t('Import existing notes, extract lasting knowledge with your configured model, then use it while writing. Your drafts can leave as Markdown or go to a connected tool.')}</p>
      </div>
      <WritingFlow current="import" />
      <p className="muted" style={{ fontSize: 'var(--t-sm)' }}>
        {t('Knowledge base now has')} {stats ? t('{facts} facts · {entities} entities', { facts: stats.facts, entities: stats.entities }) : '…'}
        {working && <> · <span className="spinner" /> {t('Extracting')}</>}
        {' '}· <a href="#" onClick={(e) => { e.preventDefault(); window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb' })) }}>{t('View overview')}</a>
      </p>

      {recentFacts.length > 0 && (
        <div className="stack" style={{ marginBottom: 10 }}>
          <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>
            {t('Just extracted (extraction runs in chunks; a few more appear after each chunk):')}
          </p>
          {recentFacts.map((f) => (
            <div className="card" key={f.id} style={{ fontSize: 'var(--t-sm)' }}>{f.text}</div>
          ))}
        </div>
      )}

      <p className="section-label">{t('Import from files and apps')}</p>
      <div className="stack import-connections">
        <p className="muted" style={{ fontSize: 'var(--t-sm)', marginTop: 0 }}>
          {t('Cleaned per source on import: original dates and folder structure are kept, each app\'s private syntax is removed (')}<code>{t('[[wiki links]]')}</code>{t(', ')}<code>{t('![[attachments]]')}</code>{t(', dataview blocks, Evernote attachment placeholders). ')}<strong>{t('Re-importing is incremental')}</strong>{t(' -- content already imported is skipped, never doubled, and does not spend extraction time again.')}
        </p>

        <label className="row import-target" style={{ gap: 8, alignItems: 'center' }}>
          <span style={{ width: 88 }}>{t('Import to')}</span>
          <select aria-label={t('Import to')} value={importTo} onChange={(e) => setImportTo(e.target.value as 'both' | 'kb' | 'notes')} disabled={importing}>
            <option value="both">{t('Notes + knowledge base (facts extracted per note; many notes take a long time)')}</option>
            <option value="notes">{t('Notes only (you can "Save to knowledge base" per note later)')}</option>
            <option value="kb">{t('Knowledge base only (no notes created)')}</option>
          </select>
        </label>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span style={{ width: 88 }}>Markdown</span>
          <FilePicker label={t('Choose Markdown files')} accept=".md,.markdown,.txt" multiple disabled={importing}
            disabledReason={t('Wait for the current import to finish')}
            onPick={(files) => void doImport(Array.from(files), 'obsidian')} />
        </div>
        <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '0 0 6px 96px' }}>
          {t('Original dates in front matter are preserved. Choose notes, knowledge extraction, or both above.')}
        </p>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span style={{ width: 88 }}>Obsidian</span>
          <FilePicker label={t('Choose Obsidian vault')} directory multiple disabled={importing}
            disabledReason={t('Wait for the current import to finish')}
            onPick={(files) => void doImport(Array.from(files), 'obsidian')} />
        </div>
        <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '0 0 6px 96px' }}>
          {t('Pick the whole vault directory.')} <code>.obsidian/</code> {t('and')} <code>.trash/</code> {t('are skipped automatically.')}
        </p>

        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span style={{ width: 88 }}>Evernote</span>
          <FilePicker label={t('Choose Evernote files')} accept=".enex" multiple disabled={importing}
            disabledReason={t('Wait for the current import to finish')}
            onPick={(files) => void doImport(Array.from(files), 'evernote')} />
        </div>
        <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '0 0 6px 96px' }}>
          {t('In Evernote, "Export notebook as .enex", then pick the file here.')}
        </p>

        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span style={{ width: 88 }}>Notion</span>
          <input aria-label="Notion Integration token"
            type="password"
            placeholder={t('Integration token (ntn_… / secret_…)')}
            value={notionToken}
            onChange={(e) => setNotionToken(e.target.value)}
            style={{ flex: 1, minWidth: 0 }}
          />
          <button onClick={doImportNotion} disabled={!notionToken.trim() || importing} title={!notionToken.trim() ? t('Fill in the Notion integration token first') : undefined}>
            {importing ? <span className="spinner" /> : t('Import')}
          </button>
        </div>
        <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '0 0 6px 96px' }}>
          {t('First, in Notion, connect the target pages ')}<strong>{t('to this integration')}</strong>{t(',')}
          {t('otherwise nothing at all can be fetched -- the most common cause of "imported but empty".')}
        </p>

        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span style={{ width: 88 }}>{t('Feishu')}</span>
          <input aria-label={t('Feishu App ID')} placeholder={t('App ID (cli_…)')} value={feishuAppId} onChange={(e) => setFeishuAppId(e.target.value)} style={{ flex: 1, minWidth: 0 }} />
          <input aria-label={t('Feishu App Secret')} type="password" placeholder="App Secret" value={feishuSecret} onChange={(e) => setFeishuSecret(e.target.value)} style={{ flex: 1, minWidth: 0 }} />
          <select aria-label={t('Feishu scope')} value={feishuScope} onChange={(e) => setFeishuScope(e.target.value as 'wiki' | 'drive')}
                  disabled={!!feishuDocs.trim()} title={feishuDocs.trim() ? t('With links filled in, only those documents are imported, not the scope listing') : undefined}>
            <option value="wiki">{t('Wiki')}</option>
            <option value="drive">{t('Drive')}</option>
          </select>
          <button onClick={doImportFeishu} disabled={!feishuAppId.trim() || !feishuSecret.trim() || importing} title={!feishuAppId.trim() || !feishuSecret.trim() ? t('Fill in the Feishu custom app\'s App ID and Secret first') : undefined}>
            {importing ? <span className="spinner" /> : t('Import')}
          </button>
        </div>
        <div className="row" style={{ gap: 8, alignItems: 'center', margin: '6px 0 0 96px' }}>
          <input aria-label={t('Feishu document links')} placeholder={t('Or paste document links directly (one per line; if filled, only these are imported)')} value={feishuDocs}
                 onChange={(e) => setFeishuDocs(e.target.value)} style={{ flex: 1, minWidth: 0 }} />
        </div>
        <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '0 0 6px 96px' }}>
          {t('Create a custom app on the Feishu Open Platform, grant read-only docx / wiki / drive permissions, then ')}<strong>{t('add the app as a collaborator')}</strong>{t(' on the wiki or documents to import. Credentials are not stored.')}
          <br />
          <strong>{t('Documents shared only as single-doc collaborator cannot be listed')}</strong>{t(' (listing requires the app to be a member of the wiki space) -- paste that document\'s link into the box above.')}
        </p>

        <AppleNotesImport disabled={importing} onImport={() => void doImportApple()} />
      </div>

      <MemoketImport to={importTo} disabled={importing} onImported={(r) => {
        announceEstimate(r)
        setBatchJob(r)
        watchJob(r.job_id, (j) => { setBatchJob(j); pollRecentFacts(j.facts) }, () => {
          void refresh()
          setRecentFacts([])
          void landImportInTray(r.job_id, trayNoteId).catch((e) => toast(friendlyError(e), 'error'))
        })
      }} />
      <p className="section-label">{t('Batch import')}</p>
      <div className="stack">
        {interrupted.length > 0 && (
          <div className="card" style={{ borderColor: 'var(--warn)' }}>
            <strong style={{ fontSize: 'var(--t-md)' }}>{t('Imports that did not finish last time')}</strong>
            {interrupted.map((j) => (
              <div key={j.job_id} className="row" style={{ justifyContent: 'space-between', marginTop: 6, gap: 8 }}>
                <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>
                  {t('{n} notes · {done} done · {facts} facts', { n: j.items.length, done: j.items.filter((it) => it.status === 'done').length, facts: j.facts })}{j.detail ? ` · ${j.detail}` : ''}
                </span>
                <button onClick={() => void doResume(j)} style={{ fontSize: 'var(--t-sm)', padding: '2px 10px' }}>{t('Resume')}</button>
              </div>
            ))}
          </div>
        )}
        <FilePicker label={t('Choose files for batch import')} multiple
          disabledReason={t('Wait for the current import to finish')}
          accept=".pdf,.docx,.txt,.md,.markdown,.wav,.mp3,.m4a,.flac"
          onPick={(files) => void doBatchIngest(files)} />
        <p className="muted" style={{ fontSize: 'var(--t-sm)' }}>
          {t('Mixed uploads of PDF / DOCX / TXT / MD / audio are supported; each file is processed independently, and one failing does not affect the others.')}
        </p>
        {batchJob && (
          <div className="card">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong>
                {batchJob.status === 'running' || batchJob.status === 'queued' || batchJob.status === 'cancelling'
                  ? <><span className="spinner" /> {t('Processing…')}</>
                  : t(STATUS_LABEL[batchJob.status] ?? batchJob.status)}
                {' · '}{t('{n} facts', { n: batchJob.facts })}
              </strong>
              {(batchJob.status === 'running' || batchJob.status === 'queued') && (
                <button onClick={doCancelBatch}>{t('Cancel')}</button>
              )}
            </div>
            <JobProgress j={batchJob} />
            {batchJob.items.map((it) => (
              <div key={it.id} className="row" style={{ justifyContent: 'space-between', marginTop: 6 }}>
                <span>{it.filename}</span>
                <span className="muted">
                  {t(STATUS_LABEL[it.status] ?? it.status)}
                  {it.status === 'remembering' && (it.chunks_total ?? 0) > 0 && ` ${t('{done}/{total} chunks', { done: it.chunks_done ?? 0, total: it.chunks_total ?? 0 })}`}
                  {(it.status === 'remembering' || it.status === 'done') && it.facts > 0 && ` · ${t('{n} extracted', { n: it.facts })}`}
                  {it.status === 'failed' && it.detail && ` · ${it.detail}`}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
      <ExportBack />
    </div>
  )
}
