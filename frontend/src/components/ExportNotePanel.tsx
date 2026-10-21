import { useEffect, useState } from 'react'

import { noteRemotes, type NoteRemote } from '../api'
import { toast } from '../toast'
import { fmtDate } from '../util/time'
import { CRED_HOWTO, canRememberCreds, credsNote, loadCreds, saveCreds } from '../util/exportCreds'
import { WHERE_LABEL, loadVault, openRemote, remoteUrl, saveVault, useExportBack, type ExportWhere } from '../util/useExportBack'
import Icon from './Icon'
import { t } from '../i18n'


export default function ExportNotePanel({ noteId, title, onClose }:
  { noteId: string; title: string; onClose: () => void }) {
  const [remotes, setRemotes] = useState<NoteRemote[] | null>(null)
  const [where, setWhere] = useState<ExportWhere | null>(null)
  const [vault, setVault] = useState(loadVault)
  const [force, setForce] = useState(false)
  const [token, setToken] = useState('')
  const [parent, setParent] = useState('')
  const [appId, setAppId] = useState('')
  const [secret, setSecret] = useState('')
  const [folder, setFolder] = useState('')
  const ex = useExportBack([noteId])

  useEffect(() => {
    let alive = true
    noteRemotes(noteId).then((r) => { if (alive) setRemotes(r) }).catch(() => { if (alive) setRemotes([]) })
    // Desktop version: prefill credentials entered last time
    void loadCreds().then((c) => {
      if (!alive) return
      if (c.notion_token) setToken(c.notion_token); if (c.notion_parent) setParent(c.notion_parent)
      if (c.feishu_app_id) setAppId(c.feishu_app_id); if (c.feishu_app_secret) setSecret(c.feishu_app_secret); if (c.feishu_folder) setFolder(c.feishu_folder)
    })
    return () => { alive = false }
  }, [noteId])

  // Default to "the one this note already has a copy on" — repeated export back is the norm, the first time is the exception
  useEffect(() => {
    if (where || remotes === null) return
    const had = remotes[0]?.platform as ExportWhere | undefined
    setWhere(had && WHERE_LABEL[had] ? had : (loadVault() ? 'obsidian' : 'obsidian'))
  }, [remotes, where])

  async function pickVault() {
    const pick = window.memoketDesktop?.pickDirectory
    if (!pick) { toast(t('The web version cannot pick a local folder; paste the path into the box'), 'error'); return }
    const dir = await pick(t('Choose the Obsidian vault folder'))
    if (dir) { setVault(dir); saveVault(dir) }
  }

  const has = (w: ExportWhere) => !!remotes?.some((r) => r.platform === w)
  const remember = canRememberCreds()
  const HINT: Record<ExportWhere, string> = {
    obsidian: t('Tree levels become folders; images and recordings are copied into _assets/.'),
    notion: t('Becomes a child page under the parent; connect the page to this integration first. Tables / lists / code / bold become Notion blocks; local images go through Notion file upload. {creds}', { creds: remember ? credsNote() : t('Credentials are not stored; enter them each time.') }),
    feishu: t('The app needs docx / drive write permission and must be a collaborator on the target folder. Tables / images / lists / code become Feishu blocks; mermaid diagrams are rendered to images here and sent along. {creds}', { creds: remember ? credsNote() : t('Credentials are not stored; enter them each time.') }),
  }
  // Folder token / parent page id are needed only when **creating**: updating a note that already has a copy shouldn't be blocked by them (§4.8)
  const ready = where === 'obsidian' ? !!vault.trim()
    : where === 'notion' ? !!token.trim() && (has('notion') || !!parent.trim())
      : !!appId.trim() && !!secret.trim() && (has('feishu') || !!folder.trim())

  async function go() {
    let out = null
    if (where === 'obsidian') out = await ex.toObsidian(vault, force)
    else if (where === 'notion') out = await ex.toNotion(token, parent, force)
    else if (where === 'feishu') out = await ex.toFeishu(appId, secret, folder, force)
    if (!out) return
    if (where === 'notion') void saveCreds({ notion_token: token.trim(), notion_parent: parent.trim() })
    if (where === 'feishu') void saveCreds({ feishu_app_id: appId.trim(), feishu_app_secret: secret.trim(), feishu_folder: folder.trim() })
    noteRemotes(noteId).then(setRemotes).catch(() => { /* none is fine */ })
  }

  const howto = where && where !== 'obsidian' ? CRED_HOWTO[where] : null

  return (
    <div className="export-note">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h2>{t('Export back “')}<span className="plain-case">{title}</span>{t('”')}</h2>
        <button className="icon-btn" title={t('Close (Esc)')} aria-label={t('Close')} onClick={onClose}><Icon n="bx-x" /></button>
      </div>

      {/* ① State first. In a repeated action this line beats any explanation; copies link to the other side */}
      <p className="muted export-note-state">
        {remotes === null ? '…'
          /* "Exporting again overwrites" is a muddled sentence for a note **never exported**: there's no "same place" yet.
             Say both steps clearly: this time creates, after that it overwrites. */
          : remotes.length === 0 ? t('This note has never been exported back — this time a new copy is created on the other side; later exports overwrite it.')
            : remotes.map((r, i) => {
              const url = remoteUrl(r, vault)
              const label = t('{where} · exported {date}', { where: t(WHERE_LABEL[r.platform as ExportWhere] ?? r.platform), date: fmtDate(r.exported_at) })
              return (
                <span key={r.platform}>
                  {i > 0 && t('; ')}
                  {url ? <a href={url} className="link" onClick={(e) => { e.preventDefault(); openRemote(url) }} title={url}>{label}<Icon n="bx-link-external" /></a> : label}
                </span>
              )
            })}
      </p>

      {/* ② Ask about one destination at a time */}
      <div className="seg export-note-seg">
        {(['obsidian', 'notion', 'feishu'] as ExportWhere[]).map((w) => (
          <button key={w} className={where === w ? 'on' : ''} aria-pressed={where === w}
                  onClick={() => setWhere(w)}>
            {WHERE_LABEL[w]}
            {has(w) && <Icon n="bx-check" />}
          </button>
        ))}
      </div>

      {/* ③ Show only the selected one's fields */}
      <div className="export-note-fields">
        {where === 'obsidian' && (
          <div className="row" style={{ gap: 6 }}>
            <input aria-label={t('Obsidian vault folder path')} placeholder={t('vault folder path')} value={vault} style={{ flex: 1, minWidth: 0 }}
                   onChange={(e) => { setVault(e.target.value); saveVault(e.target.value) }} />
            <button className="icon-btn" aria-label={t('Choose folder')} onClick={() => void pickVault()} title={t('Choose folder')}><Icon n="bx-dots-horizontal-rounded" /></button>
          </div>
        )}
        {where === 'notion' && (
          <>
            <input aria-label="Notion Integration token" type="password" placeholder={t('Integration token (ntn_… / secret_…)')} value={token} onChange={(e) => setToken(e.target.value)} />
            <input aria-label={t('Notion parent page id')} placeholder={has('notion') ? t('Parent page id (a copy exists; not needed to update)') : t('Parent page id (the 32 characters at the end of the page link)')} value={parent} onChange={(e) => setParent(e.target.value)} />
          </>
        )}
        {where === 'feishu' && (
          <>
            <input aria-label={t('Feishu App ID')} placeholder={t('App ID (cli_…)')} value={appId} onChange={(e) => setAppId(e.target.value)} />
            <input aria-label={t('Feishu App Secret')} type="password" placeholder="App Secret" value={secret} onChange={(e) => setSecret(e.target.value)} />
            <input aria-label={t('Feishu folder token')} placeholder={has('feishu') ? t('Folder token (a copy exists; not needed to update)') : t('Folder token (required: new documents are created under it)')} value={folder} onChange={(e) => setFolder(e.target.value)} />
          </>
        )}
        <label className="muted" style={{ fontSize: 'var(--t-sm)' }}>
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} /> {t('Overwrite edits made on the other side')}
        </label>
      </div>

      <p className="muted export-note-hint">
        {where ? HINT[where] : ''}
        {howto && <> <a href={howto.url} className="link" title={t(howto.text)} onClick={(e) => { e.preventDefault(); openRemote(howto.url) }}>{t('How to get credentials')}</a></>}
      </p>

      <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
        <button onClick={onClose}>{t('Cancel')}</button>
        <button className="primary" disabled={!ready || !!ex.busy} onClick={() => void go()}>
          {ex.busy ? <span className="spinner" /> : t('Write to {where}', { where: where ? t(WHERE_LABEL[where]) : '' })}
        </button>
      </div>

      {ex.result && (ex.result.out.conflicts?.length ?? 0) > 0 && (
        <p className="muted export-note-hint">
          {t('Edited on the other side, skipped: {list}. Tick “Overwrite edits made on the other side” and write again.', { list: ex.result.out.conflicts?.join(t(', ')) ?? '' })}
        </p>
      )}
      {ex.result && (ex.result.out.failed?.length ?? 0) > 0 && (
        <p className="export-note-hint" style={{ color: 'var(--del)' }}>
          {t('Failed: {list}', { list: ex.result.out.failed?.join(t('; ')) ?? '' })}
        </p>
      )}
    </div>
  )
}
