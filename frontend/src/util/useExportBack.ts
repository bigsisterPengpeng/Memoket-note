import { useState } from 'react'

import { exportFeishu, exportNotion, exportObsidian, type ExportBackOut, type NoteRemote } from '../api'
import { toast, toastAction } from '../toast'
import { exportMermaidRenders } from './mermaidPng'
import { t } from '../i18n'


export type ExportWhere = 'obsidian' | 'notion' | 'feishu'

export const WHERE_LABEL: Record<ExportWhere, string> = {
  obsidian: 'Obsidian', notion: 'Notion', feishu: 'Feishu',
}

export type ExportOutcome = { kind: 'ok' | 'none' | 'missing' | 'conflict'; text: string; url?: string }

/** Backend response -> the sentence the user sees (pure function, tested). */
export function exportOutcome(out: ExportBackOut): ExportOutcome {
  const n = (out.written ?? 0) + (out.created ?? 0) + (out.updated ?? 0)
  const failed = out.failed?.length ?? 0
  if (n) {
    const tail = failed ? t(', {n} failed', { n: failed }) : (out.conflicts?.length ? t(', {n} skipped because they changed remotely', { n: out.conflicts.length }) : '')
    return { kind: 'ok', text: t('Exported {n} notes back', { n }) + tail, url: out.url || undefined }
  }
  if (out.conflicts?.length) return { kind: 'conflict', text: t('Skipped {n} notes changed on the other side — tick “Overwrite remote changes” and export again', { n: out.conflicts.length }) }
  if (!(out.skipped ?? 0) && out.missing?.length) return { kind: 'missing', text: t('No matching note — it may have been deleted; close this dialog and reopen it') }
  if (!(out.skipped ?? 0)) return { kind: 'none', text: t('No notes to export') }
  return { kind: 'none', text: t('Nothing to write: no changes since the last export') }
}

/** The human sentence of a backend 4xx: the status code means nothing to users, keep only the sentence */
export function exportErrorText(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e ?? '')
  return raw.replace(/^Error:\s*/i, '').replace(/^4\d\d\s+(?=\S)/, '') || t('Export back failed')
}

/** Open the note on the other side. https goes to the system browser (the desktop shell's setWindowOpenHandler), obsidian:// goes to Obsidian. */
export function openRemote(url: string): void {
  window.open(url, '_blank', 'noopener')
}

/** Where the "Copies" row in the info panel / dialog can link to: Notion / Feishu store a URL; Obsidian needs the vault path built in. */
export function remoteUrl(r: NoteRemote, vault = loadVault()): string {
  if (/^https?:\/\//.test(r.remote_path)) return r.remote_path
  if (r.platform === 'obsidian' && vault && r.remote_path) return 'obsidian://open?path=' + encodeURIComponent(vault.replace(/\/+$/, '') + '/' + r.remote_path)
  return ''
}

export function useExportBack(noteIds: string[] = []) {
  const [busy, setBusy] = useState<'' | ExportWhere>('')
  const [result, setResult] = useState<{ where: ExportWhere; out: ExportBackOut } | null>(null)

  async function run(where: ExportWhere, fn: () => Promise<ExportBackOut>): Promise<ExportBackOut | null> {
    setBusy(where)
    try {
      const out = await fn()
      setResult({ where, out })
      const o = exportOutcome(out)
      if (o.url) toastAction(o.text, t('Open'), () => openRemote(o.url!), 8000)
      else toast(o.text, o.kind === 'ok' || o.kind === 'none' ? 'info' : 'error')
      // The info panel's "Copies" row refreshes along
      window.dispatchEvent(new CustomEvent('note-remotes-changed'))
      return out
    } catch (e) {
      const msg = exportErrorText(e)

      toastAction(msg, t('Copy'), () => { void navigator.clipboard?.writeText(msg) }, 15000, 'error')
      return null
    } finally {
      setBusy('')
    }
  }

  return {
    busy, result,
    toObsidian: (vaultDir: string, force: boolean) =>
      run('obsidian', () => exportObsidian(vaultDir.trim(), noteIds, force)),
    toNotion: (token: string, parentPageId: string, force = false) =>
      run('notion', () => exportNotion(token.trim(), parentPageId.trim().replace(/-/g, ''), noteIds, force)),

    toFeishu: (appId: string, secret: string, folder: string, force = false) =>
      run('feishu', async () => { await exportMermaidRenders(noteIds); return exportFeishu(appId.trim(), secret.trim(), folder.trim(), noteIds, force) }),
  }
}

/** The Obsidian vault path is not a secret and can be remembered; Notion / Feishu credentials are remembered by the main process on desktop (util/exportCreds). */
export const VAULT_KEY = 'memoket-note:vault-dir'
export function loadVault(): string {
  try { return localStorage.getItem(VAULT_KEY) || '' } catch { return '' }
}
export function saveVault(dir: string): void {
  try { localStorage.setItem(VAULT_KEY, dir) } catch { /* does not matter */ }
}
