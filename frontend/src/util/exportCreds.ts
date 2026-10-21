
import { t } from '../i18n'
export type ExportCreds = {
  notion_token?: string
  notion_parent?: string
  feishu_app_id?: string
  feishu_app_secret?: string
  feishu_folder?: string
}

export type CredsPlace = 'desktop' | 'browser'
export const WEB_CREDS_KEY = 'memoket-note:export-creds'
const KEYS: (keyof ExportCreds)[] = ['notion_token', 'notion_parent', 'feishu_app_id', 'feishu_app_secret', 'feishu_folder']

/** Where it is stored: the main process if the desktop shell has the IPC hook; otherwise this browser's localStorage */
export const credsPlace = (): CredsPlace => (window.memoketDesktop?.exportCreds ? 'desktop' : 'browser')

export const canRememberCreds = (): boolean => true

/** The sentence in the dialog: where it is stored and what that means */
export function credsNote(place: CredsPlace = credsPlace()): string {
  return place === 'desktop'
    ? t('Credentials are saved on this machine (app data folder) after a successful export and filled in next time.')
    : t('Credentials are saved in this browser (localStorage) after a successful export: another browser needs them again, clearing site data removes them; do not save on a shared computer.')
}

/** Keep only whitelisted keys and string values -- the same rule as the desktop shell's whitelist */
export function pickCreds(raw: unknown): ExportCreds {
  const out: ExportCreds = {}
  if (!raw || typeof raw !== 'object') return out
  for (const k of KEYS) {
    const v = (raw as Record<string, unknown>)[k]
    if (typeof v === 'string' && v) out[k] = v.slice(0, 512)
  }
  return out
}

function loadWeb(): ExportCreds {
  try { return pickCreds(JSON.parse(localStorage.getItem(WEB_CREDS_KEY) || '{}')) } catch { return {} }
}

function saveWeb(patch: ExportCreds): void {
  try { localStorage.setItem(WEB_CREDS_KEY, JSON.stringify({ ...loadWeb(), ...pickCreds(patch) })) } catch { /* cannot remember: fill in again next time */ }
}

export async function loadCreds(): Promise<ExportCreds> {
  if (credsPlace() === 'browser') return loadWeb()
  try { return pickCreds(await window.memoketDesktop?.exportCreds?.load()) } catch { return {} }
}

export async function saveCreds(patch: ExportCreds): Promise<void> {
  if (credsPlace() === 'browser') { saveWeb(patch); return }
  try { await window.memoketDesktop?.exportCreds?.save(pickCreds(patch) as Record<string, string>) } catch { /* cannot remember: fill in again next time */ }
}


export const CRED_HOWTO = {
  notion: { url: 'https://www.notion.so/profile/integrations', text: 'notion.so → Settings → Connections → Develop or manage integrations → New integration → copy the Internal Integration Secret; the parent page id is the 32 characters at the end of the page link, and the page must first be connected to the integration via “⋯ → Connections”' },
  feishu: { url: 'https://open.feishu.cn/app', text: 'open.feishu.cn → Apps → Credentials & Basic Info (App ID / App Secret); enable docx:document and drive:drive under Permissions; the folder token is the part after /drive/folder/ in the folder link, and the folder must add the app as an editing collaborator' },
} as const
