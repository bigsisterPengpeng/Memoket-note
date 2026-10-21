import { useEffect, useState } from 'react'
import { toast } from '../toast'
import { CRED_HOWTO, canRememberCreds, credsNote, loadCreds, saveCreds } from '../util/exportCreds'
import { openRemote, useExportBack } from '../util/useExportBack'
import Icon from './Icon'
import { t } from '../i18n'


export default function ExportBack() {
  const [vaultDir, setVaultDir] = useState(() => { try { return localStorage.getItem('memoket-note:vault-dir') || '' } catch { return '' } })
  const [force, setForce] = useState(false)
  const [notionToken, setNotionToken] = useState('')
  const [notionParent, setNotionParent] = useState('')
  const [feishuAppId, setFeishuAppId] = useState('')
  const [feishuSecret, setFeishuSecret] = useState('')
  const [feishuFolder, setFeishuFolder] = useState('')
  const remember = canRememberCreds()
  useEffect(() => {
    let alive = true
    void loadCreds().then((c) => {
      if (!alive) return
      if (c.notion_token) setNotionToken(c.notion_token); if (c.notion_parent) setNotionParent(c.notion_parent)
      if (c.feishu_app_id) setFeishuAppId(c.feishu_app_id); if (c.feishu_app_secret) setFeishuSecret(c.feishu_app_secret); if (c.feishu_folder) setFeishuFolder(c.feishu_folder)
    })
    return () => { alive = false }
  }, [])

  async function pickVault() {
    const pick = window.memoketDesktop?.pickDirectory
    if (!pick) { toast(t('The web version cannot pick a local folder; paste the path into the box'), 'error'); return }
    const dir = await pick(t('Choose the Obsidian vault folder'))
    if (dir) { setVaultDir(dir); try { localStorage.setItem('memoket-note:vault-dir', dir) } catch { /* doesn't matter */ } }
  }

  // Shared logic (util/useExportBack): what drifts is "how to call, how memoket_id overwrites,
  // how conflicts are reported", not the layout. Whole-library export = no noteIds passed.
  const { busy, result, toObsidian, toNotion, toFeishu } = useExportBack()

  const spin = (w: string, label: string) => busy === w ? <span className="spinner" /> : label

  return (
    <>
      <h2>{t('Export back')}</h2>
      <div className="stack export-back">
        <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>
          {t('Write notes from here back to other places. This is the source of truth: every note carries a ')}<code>memoket_id</code>{t('; exporting again ')}<strong>{t('overwrites')}</strong>{t(' rather than creating anew. Notes edited on the other side are skipped and listed; they are never pulled back automatically.')}
          <br />
          {}
          {remember ? t('Notion / Feishu: {note}', { note: credsNote() }) : t('Notion / Feishu credentials are not stored and must be re-entered each time; the Obsidian path is just a local path and is remembered.')}
        </p>

        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span style={{ width: 88 }}>Obsidian</span>
          <input aria-label={t('Obsidian vault folder path')} placeholder={t('vault folder path')} value={vaultDir} onChange={(e) => setVaultDir(e.target.value)} style={{ flex: 1, minWidth: 0 }} />
          <button className="icon-btn" aria-label={t('Choose folder')} onClick={() => void pickVault()} title={t('Choose folder')}><Icon n="bx-dots-horizontal-rounded" /></button>
          <label className="muted" style={{ fontSize: 'var(--t-sm)', whiteSpace: 'nowrap' }}>
            <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} /> {t('Overwrite edits made on the other side')}
          </label>
          <button onClick={() => void toObsidian(vaultDir, force)} disabled={!vaultDir.trim() || !!busy}
                  title={!vaultDir.trim() ? t('Fill in the vault folder first') : busy ? t('Writing; wait for this one to finish') : undefined}>
            {spin('obsidian', t('Write'))}
          </button>
        </div>
        <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '0 0 6px 96px' }}>
          {t('Tree levels become folders, clones become .link.txt, images / recordings are copied into _assets/. Open the vault in Obsidian to see them.')}
        </p>

        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span style={{ width: 88 }}>Notion</span>
          <input aria-label="Notion Integration token" type="password" placeholder="Integration token" value={notionToken} onChange={(e) => setNotionToken(e.target.value)} style={{ flex: 1, minWidth: 0 }} />
          <input placeholder={t('Parent page id')} title={t('The 32 characters at the end of the page link')} value={notionParent} onChange={(e) => setNotionParent(e.target.value)} style={{ flex: 1, minWidth: 0 }} />
          <button onClick={() => void toNotion(notionToken, notionParent, force).then((o) => { if (o) void saveCreds({ notion_token: notionToken.trim(), notion_parent: notionParent.trim() }) })} disabled={!notionToken.trim() || !notionParent.trim() || !!busy}
                  title={!notionToken.trim() ? t('Fill in the Integration token first') : !notionParent.trim() ? t('Fill in the parent page id first') : busy ? t('Writing; wait for this one to finish') : undefined}>
            {spin('notion', t('Write'))}
          </button>
        </div>
        <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '0 0 6px 96px' }}>
          {t('Each note becomes a child page under the parent; headings / paragraphs / lists / tables / code / quotes / bold become Notion blocks (the Notion API rejects local images, so they become a one-line note). Connect the parent page to this integration first.')}
          {' '}<a href={CRED_HOWTO.notion.url} className="link" title={t(CRED_HOWTO.notion.text)} onClick={(e) => { e.preventDefault(); openRemote(CRED_HOWTO.notion.url) }}>{t('How to get credentials')}</a>
        </p>

        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span style={{ width: 88 }}>{t('Feishu')}</span>
          <input aria-label={t('Feishu App ID')} placeholder={t('App ID (cli_…)')} value={feishuAppId} onChange={(e) => setFeishuAppId(e.target.value)} style={{ flex: 1, minWidth: 0 }} />
          <input aria-label={t('Feishu App Secret')} type="password" placeholder="App Secret" value={feishuSecret} onChange={(e) => setFeishuSecret(e.target.value)} style={{ flex: 1, minWidth: 0 }} />
          {}
          <input aria-label={t('Feishu folder token')} placeholder={t('Folder token (required)')} title={t('The part after /drive/folder/ in the folder link; new documents are created under it')} value={feishuFolder} onChange={(e) => setFeishuFolder(e.target.value)} style={{ flex: 1, minWidth: 0 }} />
          <button onClick={() => void toFeishu(feishuAppId, feishuSecret, feishuFolder, force).then((o) => { if (o) void saveCreds({ feishu_app_id: feishuAppId.trim(), feishu_app_secret: feishuSecret.trim(), feishu_folder: feishuFolder.trim() }) })} disabled={!feishuAppId.trim() || !feishuSecret.trim() || !feishuFolder.trim() || !!busy}
                  title={!feishuAppId.trim() ? t('Fill in the App ID first') : !feishuSecret.trim() ? t('Fill in the App Secret first') : !feishuFolder.trim() ? t('Fill in the folder token first') : busy ? t('Writing; wait for this one to finish') : undefined}>
            {spin('feishu', t('Write'))}
          </button>
        </div>
        <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '0 0 6px 96px' }}>
          {t('The app needs docx / drive write permission, and the target folder must add it as an editing collaborator. Tables / images / lists / code / bold become Feishu blocks.')}
          {' '}<a href={CRED_HOWTO.feishu.url} className="link" title={t(CRED_HOWTO.feishu.text)} onClick={(e) => { e.preventDefault(); openRemote(CRED_HOWTO.feishu.url) }}>{t('How to get credentials')}</a>
        </p>

        {result && (
          <div className="card export-back-result">
            <strong style={{ fontSize: 'var(--t-md)' }}>
              {result.where === 'obsidian' ? 'Obsidian' : result.where === 'notion' ? 'Notion' : t('Feishu')}{t(': ')}
              {result.out.written != null && <> {t('Wrote {written} · unchanged {skipped}', { written: result.out.written, skipped: result.out.skipped ?? 0 })}</>}
              {result.out.created != null && <> {t('Created {created} · overwrote {updated}', { created: result.out.created, updated: result.out.updated ?? 0 })}</>}
            </strong>
            {!!result.out.conflicts?.length && (
              <div style={{ marginTop: 6 }}>
                <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('Edited on the other side, left alone this time (tick “Overwrite edits made on the other side” and write again to overwrite):')}</span>
                <ul style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 'var(--t-sm)' }}>
                  {result.out.conflicts.slice(0, 20).map((p) => <li key={p}>{p}</li>)}
                </ul>
              </div>
            )}
            {!!result.out.missing?.length && (
              <div className="muted" style={{ marginTop: 6, fontSize: 'var(--t-sm)' }}>{t('{n} note ids were not found in the database (possibly deleted).', { n: result.out.missing.length })}</div>
            )}
            {!!result.out.untried && (
              <div className="muted" style={{ marginTop: 6, fontSize: 'var(--t-sm)' }}>{t('The same error kept recurring; {n} remaining notes were not attempted — fix the error above and try again.', { n: result.out.untried })}</div>
            )}
            {!!result.out.urls?.length && (
              <ul style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 'var(--t-sm)' }}>
                {result.out.urls.slice(0, 20).map((u) => <li key={u.note_id}><a href={u.url} className="link" onClick={(e) => { e.preventDefault(); openRemote(u.url) }}>{u.title}</a></li>)}
              </ul>
            )}
            {!!result.out.failed?.length && (
              <div style={{ marginTop: 6 }}>
                <span className="muted" style={{ fontSize: 'var(--t-sm)', color: 'var(--del)' }}>{t('Failed: ')}</span>
                <ul style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 'var(--t-sm)' }}>
                  {result.out.failed.slice(0, 20).map((p) => <li key={p}>{p}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
