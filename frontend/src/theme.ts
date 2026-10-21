/** Appearance: follow system / light / dark.
 *
 * The UI's dark mode relies entirely on CSS `prefers-color-scheme`; in the desktop shell that value is decided by the main process's
 * nativeTheme, so this only stores the choice and passes it to the main process via preload.
 * A plain browser has no such channel and can only follow the system -- the settings page explains that. */
export type Theme = 'system' | 'light' | 'dark'

const KEY = 'memoket.theme'

declare global {
  /** Screen activity capture lives in the **main process** (it must stay resident, keep running after the window closes, react to screen lock);
   *  the UI is just one view of it -- the menu bar icon is another (daily-journey-plan §8.3). */
  type JourneyState = 'off' | 'running' | 'paused' | 'no-permission'
  interface Window { memoketDesktop?: { setTheme(theme: Theme): void; onMenu?(cb: (name: string) => void): void; onFlush?(cb: () => void): void; flushed?(): void; rememberUser?(user: string): void; pickDirectory?(title: string): Promise<string>; exportCreds?: { load(): Promise<Record<string, string>>; save(patch: Record<string, string>): Promise<void> }; slidesToPdf?(html: string, name: string): Promise<string>; backendInfo?(): Promise<{ port: number; pid: number; dataDir: string } | null>; journey?: { state(): Promise<{ state: JourneyState; today: number }>; start(): Promise<void>; pause(minutes?: number): Promise<void>; resume(): Promise<void>; stop(): Promise<void> } } }
}

export function getTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch { return 'system' }
}

export function applyTheme(theme: Theme) {
  try { localStorage.setItem(KEY, theme) } catch { /* private window etc.: works without storing */ }
  window.memoketDesktop?.setTheme(theme)
}

export const canSwitchTheme = () => !!window.memoketDesktop

/** Pass the last choice again at startup -- every cold start of the main process is "follow system". */
export function restoreTheme() {
  const t = getTheme()
  if (t !== 'system') applyTheme(t)
}
