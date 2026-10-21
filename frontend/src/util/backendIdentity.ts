
import { t } from '../i18n'

export type ShellBackend = { port: number; pid: number; dataDir: string }
export type HealthWho = { pid?: number; data_dir?: string; started_at?: string }

export type Mismatch = { kind: 'port' | 'pid'; text: string }

/** Pure function, easy to test: who the shell says to connect to + who this screen actually connected to -> the mismatches. */
export function compareIdentity(
  shell: ShellBackend | null | undefined,
  pageOrigin: string,
  who: HealthWho | null | undefined,
): Mismatch[] {
  if (!shell) return []                       // web build / shell not ready: no "who it should connect to"
  const out: Mismatch[] = []
  const port = Number(new URL(pageOrigin).port || 0)
  if (port && shell.port && port !== shell.port) {
    out.push({
      kind: 'port',
      text: t('This window is connected to 127.0.0.1:{port}, but this app’s own backend is on {shellPort}. ', { port, shellPort: shell.port })
        + t('The notes on screen most likely belong to another memoket-NOTE on this machine — do not edit here; close this window first.'),
    })
  }
  // **Do not judge when `pid` is unavailable**: old backends lack that field, and reading "unknown" as "different"
  // would show a false alarm to every user halfway through an upgrade (§21 "the criterion should be narrow").
  const theirs = Number(who?.pid ?? 0)
  if (theirs && shell.pid && theirs !== shell.pid) {
    out.push({
      kind: 'pid',
      text: t('The backend answering on this port is process {theirs}, but this app started {pid}. ', { theirs, pid: shell.pid })
        + t('Two instances are writing the same database — close one of them first.'),
    })
  }
  return out
}

/** Make the noise. **Use the dumbest way**: a banner pinned to the top of the window that cannot be dismissed.
 *
 * Not a toast: a toast disappears by itself, and "you are editing someone else's library" **should not disappear by itself**.
 * Not React: this must live outside App (App itself is reading that wrong backend),
 * and this batch does not touch `App.tsx` (another agent's territory).
 */
function shout(lines: string[]) {
  const id = 'memoket-wrong-backend'
  if (document.getElementById(id)) return
  const bar = document.createElement('div')
  bar.id = id
  bar.setAttribute('role', 'alert')
  // Color / layer / font size all go through tokens (`docs/UI_SPEC.md` §1, watched by `check-ui-tokens`):
  // `--live` is the one red in this design, `--z-toast` is the "always on top" layer
  // -- exactly the two things this banner needs.
  bar.style.cssText = [
    'position:fixed', 'inset:0 0 auto 0', 'z-index:var(--z-toast)',
    'padding:var(--s-3) var(--s-5)', 'font-size:var(--t-sm)', 'line-height:1.5',
    'background:var(--live)', 'color:#fff', 'white-space:pre-wrap',
  ].join(';')
  bar.textContent = '⚠︎ ' + t('Connected to the wrong backend') + '\n' + lines.join('\n')
  document.body.appendChild(bar)
}

/** Check once at startup. Failures (no health / no shell) all return quietly -- **the self-check is not load-bearing**. */
export async function checkBackendIdentity(
  fetchHealth: () => Promise<{ backend?: HealthWho } | null> = defaultHealth,
): Promise<Mismatch[]> {
  let shell: ShellBackend | null = null
  try {
    shell = (await window.memoketDesktop?.backendInfo?.()) ?? null
  } catch { return [] }
  if (!shell) return []
  let who: HealthWho | null = null
  try {
    who = (await fetchHealth())?.backend ?? null
  } catch { who = null }
  const bad = compareIdentity(shell, location.origin, who)
  if (bad.length) {
    shout(bad.map((m) => m.text))

    try {
      const { clientLog } = await import('../api')
      void clientLog('error', bad.map((m) => `${m.kind}: ${m.text}`).join(' | '), '', 'backend-identity')
    } catch { /* when connected to the wrong backend this may well fail to send anyway */ }
  }
  return bad
}

async function defaultHealth(): Promise<{ backend?: HealthWho } | null> {
  const r = await fetch('/api/health')
  if (!r.ok) return null
  return (await r.json()) as { backend?: HealthWho }
}
