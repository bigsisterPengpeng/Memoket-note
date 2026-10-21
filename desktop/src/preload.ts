/**
 * The only door the renderer has into the main process. Nothing but a few narrow calls is
 * exposed: first, switching the theme - the UI's dark mode relies entirely on
 * `prefers-color-scheme`, and in Electron that value is decided by nativeTheme.themeSource, so
 * "pick dark in settings" has to go through the main process to change it, with no CSS change.
 */
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('memoketDesktop', {
  setTheme(theme: 'system' | 'light' | 'dark') { ipcRenderer.send('set-theme', theme) },
  /** An item in the application menu that the UI must respond to was clicked, e.g. "Help > Keyboard shortcuts" */
  onMenu(cb: (name: string) => void) { ipcRenderer.on('menu', (_e, name: string) => cb(name)) },
  /** Before quitting, the main process asks "is anything unsaved"; the UI replies flushed() after saving */
  onFlush(cb: () => void) { ipcRenderer.on('flush', () => cb()) },
  flushed() { ipcRenderer.send('flushed') },
  /** The UI settled on the current identity: the main process records it in identity.json, so it is recognized even if localStorage is lost */
  rememberUser(user: string) { ipcRenderer.send('remember-user', user) },
  /** The UI language changed ('en' | 'zh'): the main process records it in identity.json as `lang`
   *  and redraws what it owns (application menu, tray) in that language. */
  rememberLang(lang: string) { ipcRenderer.send('remember-lang', lang) },

  backendInfo(): Promise<{ port: number; pid: number; dataDir: string } | null> {
    return ipcRenderer.invoke('backend:info')
  },
  /** Show the system folder-picker dialog (choosing a vault when exporting back to Obsidian); returns an empty string on cancel */
  pickDirectory(title: string): Promise<string> { return ipcRenderer.invoke('pick-directory', title) },
  /** Credentials for exporting back to Notion / Feishu: kept in the main process's export-credentials.json (next to identity.json); the web version has no such door */
  exportCreds: {
    load(): Promise<Record<string, string>> { return ipcRenderer.invoke('export-creds:load') },
    save(patch: Record<string, string>): Promise<void> { return ipcRenderer.invoke('export-creds:save', patch) },
  },

  /** Screen activity (Daily Journey). **Capture runs in the main process** - it has to be
   *  resident, keep going after the window is closed, and respond to screen lock, none of which
   *  the renderer can do. The UI is just one view of this state: the menu-bar icon is another
   *  (docs/daily-journey-plan.md section 8.3). */
  /** Slides -> PDF: the main process runs printToPDF in an offscreen window (zero new dependencies).
   *  Returns where it was saved; an empty string if the user cancelled. */
  slidesToPdf(html: string, name: string): Promise<string> {
    return ipcRenderer.invoke('slides:pdf', html, name)
  },
  journey: {
    state(): Promise<{ state: 'off' | 'running' | 'paused' | 'no-permission'; today: number }> {
      return ipcRenderer.invoke('journey:state')
    },
    start(): Promise<void> { return ipcRenderer.invoke('journey:start') },
    pause(minutes?: number): Promise<void> { return ipcRenderer.invoke('journey:pause', minutes) },
    resume(): Promise<void> { return ipcRenderer.invoke('journey:resume') },
    stop(): Promise<void> { return ipcRenderer.invoke('journey:stop') },
  },
})
