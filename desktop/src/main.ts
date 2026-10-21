/**
 * Main process of the MEMOKET NOTE desktop app.
 *
 * Three jobs: start the backend, open the window, clean up on quit. The UI itself lives entirely
 * in the renderer and is the same code as the web version - **desktop and web do not fork**,
 * which is what the backend hosting the frontend itself buys.
 */
import { nativeTheme, app, BrowserWindow, Menu, Tray, nativeImage, powerMonitor, dialog, shell, ipcMain, session, screen } from 'electron'
import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs'
import path from 'node:path'

import { startBackend, type Backend } from './backend.js'
import { fakeSource, makeRecorder, onPowerEvent, type CaptureSource, type CaptureState, type FakeSpec, type Recorder } from './capture.js'
import { setLang, t } from './i18n.js'

// **--dev only decides whether devtools open.** "Where the frontend comes from" must follow
// app.isPackaged: if a command-line flag decided it, forgetting --dev would look for a directory
// that only exists after packaging, the backend could not mount the frontend, and the window
// would show a bare {"detail":"Not Found"} - hit on the very first run.
const wantDevTools = process.argv.includes('--dev')
/** `--user=xxx`: open with the given identity. For development and debugging - without it the
 *  renderer invents a random user for itself and sees an empty library. */
const forcedUser = process.argv.find((a) => a.startsWith('--user='))?.slice(7)


const forcedTheme = process.argv.includes('--dark') ? 'dark' : process.argv.includes('--light') ? 'light' : null

const shotPath = process.argv.find((a) => a.startsWith('--shot='))?.slice(7)
// Separate several delays with commas: `--shot-delay=20000,60000` -> one shot each (file name
// gets -1 / -2), to see what a process that runs for minutes (smart continue) looks like midway.
const shotDelays = (process.argv.find((a) => a.startsWith('--shot-delay='))?.slice(13) ?? '9000')
  .split(',').map((s) => Number(s)).filter((n) => n > 0)


const identityFile = () => path.join(app.getPath('userData'), 'identity.json')
function readIdentityFile(): { user?: unknown; lang?: unknown } {
  try { return JSON.parse(readFileSync(identityFile(), 'utf8')) as { user?: unknown; lang?: unknown } } catch { return {} }
}
function loadIdentity(): string | undefined {
  const u = readIdentityFile().user
  return typeof u === 'string' && /^[\w.-]{1,64}$/.test(u) ? u : undefined
}
function loadLang(): 'en' | 'zh' { return readIdentityFile().lang === 'zh' ? 'zh' : 'en' }
function saveIdentity(patch: { user?: string; lang?: 'en' | 'zh' }) {
  // merge: writing only one of the two fields must not drop the other
  try { writeFileSync(identityFile(), JSON.stringify({ ...readIdentityFile(), ...patch, saved_at: new Date().toISOString() })) } catch { /* cannot write: try again next time */ }
}

function appUrl(port: number): string {
  const q = new URLSearchParams()
  const user = forcedUser ?? loadIdentity()
  if (user) q.set('user', user)
  const s = q.toString()
  return `http://127.0.0.1:${port}/` + (s ? `?${s}` : '')
}
let backend: Backend | null = null
let win: BrowserWindow | null = null
const logs: string[] = []

function remember(line: string) {
  logs.push(line.trimEnd())
  if (logs.length > 400) logs.shift()      // keep only the most recent, do not eat all memory
  process.stdout.write(line)
  persistLog(line)
}

/** The log is also written to disk (~/Library/Logs/<app>/memoket-note.log): those 400 in-memory
 *  lines are invisible exactly when the app crashed / will not start and they are needed most
 *  ("Export backend log" needs the app to be alive to click). Rolled to .1 above 2MB, one
 *  generation kept. */
const LOG_MAX_BYTES = 2 * 1024 * 1024
let logFile: string | null = null
function persistLog(line: string) {
  try {
    if (logFile === null) {
      const dir = app.getPath('logs')
      mkdirSync(dir, { recursive: true })
      // app.getPath('logs') uses the name from package.json (memoket-note-desktop), the same

      // do not interleave lines
      logFile = path.join(dir, app.isPackaged ? 'memoket-note.log' : 'memoket-note-dev.log')
    }
    if (existsSync(logFile) && statSync(logFile).size > LOG_MAX_BYTES) renameSync(logFile, logFile + '.1')
    appendFileSync(logFile, line.endsWith('\n') ? line : line + '\n', 'utf8')
  } catch { /* a log that cannot be written must not affect real work */ }
}

const boundsFile = () => path.join(app.getPath('userData'), 'window.json')


async function clearCacheOnUpgrade() {
  const f = path.join(app.getPath('userData'), 'version.json')
  const now = app.getVersion()
  let seen = ''
  try { seen = JSON.parse(readFileSync(f, 'utf8')).version ?? '' } catch { /* first run, no such file */ }
  if (seen === now) return
  try {
    await session.defaultSession.clearCache()
    remember(`[desktop] version ${seen || '(first run)'} -> ${now}, HTTP cache cleared\n`)
  } catch (e) {
    remember(`[desktop] clearing the cache failed (not fatal): ${e instanceof Error ? e.message : String(e)}\n`)
  }
  try { writeFileSync(f, JSON.stringify({ version: now })) } catch { /* cannot write: clear once more next time */ }
}

function loadBounds(): { x?: number; y?: number; width: number; height: number } | null {
  try {
    const b = JSON.parse(readFileSync(boundsFile(), 'utf8')) as { x?: number; y?: number; width: number; height: number }
    if (!b || !b.width || !b.height) return null
    // The display changed (external screen unplugged): do not put the window somewhere invisible
    const onScreen = screen.getAllDisplays().some((d) => {
      const a = d.workArea
      return b.x !== undefined && b.y !== undefined && b.x >= a.x - 50 && b.y >= a.y - 50
        && b.x < a.x + a.width - 100 && b.y < a.y + a.height - 100
    })
    return onScreen ? b : { width: b.width, height: b.height }
  } catch { return null }
}

let boundsTimer: NodeJS.Timeout | null = null
function rememberBounds(w: BrowserWindow) {
  if (boundsTimer) clearTimeout(boundsTimer)
  boundsTimer = setTimeout(() => {
    try { if (!w.isDestroyed() && !w.isFullScreen()) writeFileSync(boundsFile(), JSON.stringify(w.getBounds())) } catch { /* does not matter */ }
  }, 400)
}

// Before quitting, let the UI save any unsaved body text: autosave has a 1.5 s debounce, and
// Cmd+Q landing right inside those 1.5 s loses the last few sentences. The main process
// intercepts the quit once, asks the UI, and really quits after it has saved (or 800 ms with no reply).
let flushed = false
function flushThenQuit(e: Electron.Event) {
  if (flushed || !win || win.isDestroyed()) return
  e.preventDefault()
  const started = Date.now()
  const done = () => { if (flushed) return; flushed = true; remember(`[desktop] save before quit: UI responded after ${Date.now() - started}ms`); app.quit() }
  ipcMain.once('flushed', done)
  win.webContents.send('flush')
  setTimeout(done, 800)
}

function createWindow(url: string) {

  const winArg = process.argv.find((a) => a.startsWith('--win='))?.slice(6).split('x').map(Number)

  const saved = winArg ? null : loadBounds()
  win = new BrowserWindow({
    ...(saved ?? {}),
    width: winArg?.[0] || saved?.width || 1440,
    height: winArg?.[1] || saved?.height || 900,
    minWidth: 900,
    minHeight: 600,
    // Leave room for the traffic lights at the top left - following Trilium, the title bar is
    // drawn by the UI itself, and the top of the launch bar leaves a gap for the system buttons.
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#ffffff',
    show: false,
    webPreferences: {
      // The renderer runs plain web code and does not need node. Turning it off is the posture
      // that should be the default: this UI renders knowledge-base content and model-written text.
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  })

  win.once('ready-to-show', () => win?.show())
  win.on('closed', () => { win = null })

  // External links go to the system browser, not to a window without an address bar inside the app.
  win.webContents.setWindowOpenHandler(({ url: target }) => {
    if (/^(https?|obsidian):/.test(target)) void shell.openExternal(target)   // obsidian:// is the "open" after exporting back to Obsidian
    return { action: 'deny' }
  })

  win.on('resize', () => win && rememberBounds(win))
  win.on('move', () => win && rememberBounds(win))
  // Load failures (backend port taken / page not packaged) used to be a blank window saying nothing: log them
  win.loadURL(url).catch((e) => remember(`[desktop] page load failed ${url}: ${e}\n`))
  // The renderer only reports its language when it changes; on every load ask it once for the
  // language it currently has, so menus follow it even when it was chosen in an earlier session
  win.webContents.on('did-finish-load', () => { void syncLangFromRenderer() })
  if (wantDevTools) win.webContents.openDevTools({ mode: 'detach' })
  if (shotPath) {
    win.webContents.once('did-finish-load', () => {
      shotDelays.forEach((delay, i) => {
        setTimeout(async () => {
          const file = shotDelays.length === 1 ? shotPath : shotPath.replace(/\.png$/, '') + `-${i + 1}.png`
          try {
            const img = await win!.webContents.capturePage()
            writeFileSync(file, img.toPNG())
            process.stdout.write(`[shot] ${file} ${img.getSize().width}x${img.getSize().height}\n`)
          } catch (e) { process.stderr.write(`[shot] failed: ${e}\n`) }
          if (i === shotDelays.length - 1) app.quit()
        }, delay)
      })
    })
  }
}

let quitting = false
let restarts = 0


async function launchBackend(webDir: string): Promise<Backend> {
  return startBackend({
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    webDir,
    // After packaging the data goes to the system user-data directory (on macOS
    // ~/Library/Application Support/<appName>). In development it is not passed, and the
    // backend keeps the relative ./data, the same library as when the backend is started by hand.
    dataDir: app.isPackaged ? path.join(app.getPath('userData'), 'data') : undefined,
    // Screen activity **must line up in development too**: capture writes <userData>/journey, and
    // the same path is told to the backend here, so the two sides do not each guess once (see the
    // comment on journeyDir in backend.ts).
    journeyDir: path.join(app.getPath('userData'), 'journey'),
    onLog: remember,
    onCrash: (info) => {
      if (quitting) return
      remember(`[desktop] backend crashed (${info}), ${restarts < 2 ? 'restarting' : 'not retrying'}`)
      if (restarts >= 2) {
        dialog.showErrorBox(t('Backend keeps crashing'),
          t('It has already been restarted twice automatically and will not be retried.\n\nLast log lines:\n{log}\n\nFull log: {file}',
            { log: logs.slice(-12).join('\n') || t('(no output)'), file: logFile ?? app.getPath('logs') }))
        return
      }
      restarts += 1
      const oldPort = backend?.port
      backend = null
      setTimeout(() => {
        void launchBackend(webDir).then((b) => {
          backend = b
          if (b.port !== oldPort) {
            remember(`[desktop] backend moved to ${b.port} (was ${oldPort}), window follows the new address\n`)
          }
          // `loadURL` rather than `reload()`: if the port changed, `reload()` refreshes the old

          win?.loadURL(appUrl(b.port)).catch((e) =>
            remember(`[desktop] page load failed after restarting the backend ${appUrl(b.port)}: ${e}\n`))
        }).catch((e) => {
          dialog.showErrorBox(t('The backend could not be restarted'),
            t('{error}\n\nLast log lines:\n{log}\n\nFull log: {file}',
              { error: (e as Error).message, log: logs.slice(-12).join('\n') || t('(no output)'), file: logFile ?? app.getPath('logs') }))
        })
      }, 800)
    },
  })
}

async function boot() {
  const webDir = app.isPackaged
    ? path.join(process.resourcesPath, 'web')
    : path.resolve(__dirname, '..', '..', 'frontend', 'dist')

  // If the frontend has not been built, say so on the spot. Without the check the symptom is a
  // line of JSON 404 in the window - an error message with nothing to do with the real cause
  // (one `npm run build` was skipped).
  if (!existsSync(path.join(webDir, 'index.html'))) {
    dialog.showErrorBox(
      t('The frontend has not been built'),
      t('{dir} has no index.html.\n\n', { dir: webDir }) +
      (app.isPackaged
        ? t('This installer is incomplete, please reinstall.')
        : t('In development mode, build the frontend once first:\n    cd frontend && npm run build')))
    app.quit()
    return
  }

  try {
    backend = await launchBackend(webDir)
  } catch (e) {
    // **When it cannot start, say why.** With a blank window or a silent exit the user can do
    // nothing but reinstall; the last few backend log lines almost always point at the real problem.
    dialog.showErrorBox(
      t('The backend could not start'),
      t('{error}\n\nLast log lines:\n{log}', { error: (e as Error).message, log: logs.slice(-12).join('\n') || t('(no output)') }))
    app.quit()
    return
  }
  createWindow(appUrl(backend.port))
}

if (forcedTheme) nativeTheme.themeSource = forcedTheme

ipcMain.on('remember-user', (_e, user: unknown) => {
  if (forcedUser) return
  if (typeof user === 'string' && /^[\w.-]{1,64}$/.test(user) && user !== loadIdentity()) {
    saveIdentity({ user })
    remember(`[desktop] remembered identity ${user}`)
  }
})
/** The renderer's UI language changed (or was reported on load): persist it in identity.json
 *  and rebuild everything this process draws itself (application menu, tray). */
function applyLang(lang: unknown, persist: boolean) {
  const l = lang === 'zh' ? 'zh' : 'en'
  const changed = setLang(l)
  if (persist && !forcedUser && loadLang() !== l) saveIdentity({ lang: l })
  if (changed) { installMenu(); refreshTray() }
}
ipcMain.on('remember-lang', (_e, lang: unknown) => {
  if (lang !== 'en' && lang !== 'zh') return
  applyLang(lang, true)
})
/** Ask the page which language it is in (localStorage key `memoket-note-lang`, see
 *  frontend/src/i18n/index.ts). The renderer only calls rememberLang on a change, so a language
 *  chosen in an earlier session would otherwise leave this process on the stored/default one. */
async function syncLangFromRenderer() {
  try {
    const v = await win?.webContents.executeJavaScript(`(() => { try { return localStorage.getItem('memoket-note-lang') } catch { return null } })()`)
    if (v === 'en' || v === 'zh') applyLang(v, true)
  } catch { /* page gone or no localStorage: keep what we have */ }
}

const credsFile = () => path.join(app.getPath('userData'), 'export-credentials.json')
function loadCreds(): Record<string, string> {
  try {
    const raw = JSON.parse(readFileSync(credsFile(), 'utf8')) as Record<string, unknown>
    return Object.fromEntries(Object.entries(raw).filter(([k, v]) => /^[a-z_]{1,32}$/.test(k) && typeof v === 'string').map(([k, v]) => [k, (v as string).slice(0, 512)]))
  } catch { return {} }
}
ipcMain.handle('export-creds:load', () => loadCreds())
ipcMain.handle('export-creds:save', (_e, patch: unknown) => {
  if (!patch || typeof patch !== 'object') return
  const merged = { ...loadCreds() }
  for (const [k, v] of Object.entries(patch as Record<string, unknown>)) {
    if (!/^[a-z_]{1,32}$/.test(k)) continue
    if (typeof v === 'string' && v.trim()) merged[k] = v.trim().slice(0, 512)
    else if (v === '' || v === null) delete merged[k]
  }
  try { writeFileSync(credsFile(), JSON.stringify(merged, null, 2), { mode: 0o600 }) } catch { /* cannot write: fill in again next time */ }
})

ipcMain.handle('backend:info', () => (backend ? {
  port: backend.port,
  pid: backend.pid,
  dataDir: app.isPackaged ? path.join(app.getPath('userData'), 'data') : '',
} : null))
// Exporting back to Obsidian needs a vault directory: the web cannot get a local path, only the main process can show the system dialog
ipcMain.handle('pick-directory', async (_e, title: unknown) => {
  const r = await dialog.showOpenDialog({ title: typeof title === 'string' ? title : t('Choose a folder'), properties: ['openDirectory', 'createDirectory'] })
  return r.canceled ? '' : (r.filePaths[0] || '')
})
/** Slides -> PDF (the last step of pain point 6). **Zero new dependencies**: Electron can
 *  `printToPDF` by itself, so all that is needed is a laid-out HTML (generated by the frontend `util/slideHtml`).
 *
 *  Printed in an **offscreen window**, not in the current window: the current window holds the
 *  editor, and swapping its DOM out and back would lose cursor, scroll position and unsaved changes.
 */
ipcMain.handle('slides:pdf', async (_e, html: unknown, name: unknown) => {
  if (typeof html !== 'string' || !html) return ''
  const r = await dialog.showSaveDialog({
    title: t('Export slides'),
    defaultPath: `${typeof name === 'string' && name ? name : t('Slides')}.pdf`,
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  })
  if (r.canceled || !r.filePath) return ''
  const off = new BrowserWindow({ show: false, width: 1280, height: 720,
                                  webPreferences: { javascript: false } })
  try {
    await off.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html))
    // One 16:9 page: aligned with the @page size in slideHtml (1280x720 CSS px = 13.33x7.5 inches)
    const pdf = await off.webContents.printToPDF({
      pageSize: { width: 13.333, height: 7.5 }, printBackground: true, margins: { top: 0, bottom: 0, left: 0, right: 0 },
    })
    writeFileSync(r.filePath, pdf)
    remember(`[desktop] slides exported ${r.filePath} (${(pdf.length / 1024).toFixed(0)}KB)\n`)
    return r.filePath
  } catch (e) {
    remember(`[desktop] slide export failed: ${String(e)}\n`)
    throw e
  } finally {
    off.destroy()
  }
})

ipcMain.on('set-theme', (_e, theme: unknown) => {
  if (forcedTheme) return
  if (theme === 'system' || theme === 'light' || theme === 'dark') nativeTheme.themeSource = theme
})

/** Application menu. Without it on macOS, role shortcuts like Cmd+C / Cmd+V do not work in
 *  Electron; the zoom trio (Cmd+= / Cmd+- / Cmd+0) also comes from here - following Trilium's
 *  zoomIn/Out/Reset. Rebuilt whenever the UI language changes. */
function installMenu() {
  const isMac = process.platform === 'darwin'
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    ...(isMac ? [{ role: 'appMenu' as const }] : []),
    {

      // The accelerators are display only: the real key handling is in the renderer, and click here sends the event of the same name.
      label: t('File'),
      submenu: [
        // registerAccelerator: false = the menu only shows the shortcut and does not register it
        // with the system - the renderer still handles the key, otherwise Cmd+N would be eaten by
        // the menu and the event sent again (or each side would create a note)
        { label: t('New note'), accelerator: 'CommandOrControl+N', registerAccelerator: false, click: () => win?.webContents.send('menu', 'new-note') },
        { label: t("Today's journal"), accelerator: 'CommandOrControl+Shift+D', registerAccelerator: false, click: () => win?.webContents.send('menu', 'today') },
        { type: 'separator' as const },
        { label: t('Import…'), click: () => win?.webContents.send('menu', 'import') },
        { label: t('Export all notes…'), click: () => win?.webContents.send('menu', 'export-all') },
        { label: t('Recently deleted'), click: () => win?.webContents.send('menu', 'trash') },
        { label: t('Screen activity'), click: () => openJourneyPage() },
        { type: 'separator' as const },
        { role: 'close' as const, label: t('Close window') },
      ],
    },
    { role: 'editMenu' as const },
    // Tabs menu (browsers / Trilium have one): the renderer wires up the shortcuts itself
    // (registerAccelerator: false only shows the key in the menu); clicking the menu goes through
    // the 'menu' channel -> main.tsx -> window 'tab-action' event
    {
      label: t('Tabs'),
      submenu: [
        { label: t('New tab'), accelerator: 'CommandOrControl+T', registerAccelerator: false, click: () => win?.webContents.send('menu', 'new-note') },
        { label: t('Close tab'), accelerator: 'CommandOrControl+W', registerAccelerator: false, click: () => win?.webContents.send('menu', 'tab:close') },
        { label: t('Reopen closed tab'), accelerator: 'CommandOrControl+Shift+T', registerAccelerator: false, click: () => win?.webContents.send('menu', 'tab:reopen') },
        { type: 'separator' as const },
        { label: t('Next tab'), accelerator: 'Control+Tab', registerAccelerator: false, click: () => win?.webContents.send('menu', 'tab:next') },
        { label: t('Previous tab'), accelerator: 'Control+Shift+Tab', registerAccelerator: false, click: () => win?.webContents.send('menu', 'tab:prev') },
        { label: t('List all tabs'), click: () => win?.webContents.send('menu', 'tab:list') },
        { type: 'separator' as const },
        { label: t('Close other tabs'), click: () => win?.webContents.send('menu', 'tab:close-others') },
      ],
    },
    {
      label: t('View'),
      submenu: [
        { role: 'resetZoom' as const, label: t('Actual size') },
        { role: 'zoomIn' as const, label: t('Zoom in'), accelerator: 'CommandOrControl+=' },
        { role: 'zoomOut' as const, label: t('Zoom out') },
        { type: 'separator' as const },
        { role: 'togglefullscreen' as const },
        { role: 'toggleDevTools' as const },
      ],
    },
    { role: 'windowMenu' as const },
    {
      // Trilium's Help menu: shortcuts, where the data is, where the logs are, where to report problems
      label: t('Help'),
      submenu: [
        { label: t('Keyboard shortcuts'), accelerator: 'CommandOrControl+/', click: () => win?.webContents.send('menu', 'shortcuts') },
        { type: 'separator' as const },
        { label: t('Export all notes…'), click: () => win?.webContents.send('menu', 'export-all') },
        { label: t('Open backups folder'), click: () => { void shell.openPath(path.join(app.isPackaged ? path.join(app.getPath('userData'), 'data') : path.resolve(__dirname, '..', '..', 'backend', 'data'), 'backups')) } },
        { label: t('Open data folder'), click: () => { void shell.openPath(app.isPackaged ? path.join(app.getPath('userData'), 'data') : path.resolve(__dirname, '..', '..', 'backend', 'data')) } },
        { label: t('Open logs folder'), click: () => { void shell.openPath(app.getPath('logs')) } },
        { label: t('Export backend log…'), click: () => {
          const file = path.join(app.getPath('logs'), `memoket-note-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.log`)
          try { writeFileSync(file, logs.join('\n') + '\n', 'utf8'); shell.showItemInFolder(file) }
          catch (e) { dialog.showErrorBox(t('Export failed'), String(e)) }
        } },
        { type: 'separator' as const },
        { label: t('Report an issue'), click: () => { void shell.openExternal('https://github.com/huilongan/Memoket-note/issues') } },
      ],
    },
  ]))
}


// Keep development preferences and Chromium storage separate from installed builds.
if (!app.isPackaged) app.setPath('userData', app.getPath('userData') + '-dev')

if (!app.isPackaged && process.env.MEMOKET_USER_DATA) app.setPath('userData', process.env.MEMOKET_USER_DATA)

// Single instance (same as Trilium): a second one just brings the first one's window to the
// front. Two running at once would fight over the same sqlite and localStorage, the UI would
// look fine, and the data would be written separately by each.
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (win) { if (win.isMinimized()) win.restore(); win.focus() }
  })
  // Anything unexpected that boot() does not catch (thrown while opening the window / reading
  // the identity file) used to be an unhandled rejection: process alive, no window.
  app.whenReady().then(() => { setLang(loadLang()); installMenu(); setupJourney(); return clearCacheOnUpgrade() }).then(boot).catch((e) => {
    remember(`[desktop] startup failed: ${e instanceof Error ? e.stack ?? e.message : String(e)}\n`)
    dialog.showErrorBox(t('Startup failed'), t('{error}\n\nFull log: {file}', { error: e instanceof Error ? e.message : String(e), file: logFile ?? app.getPath('logs') }))
    app.quit()
  })
}

// ——— Screen activity (Daily Journey, docs/daily-journey-plan.md) ——————————————
//
// **Off by default.** The macOS Screen Recording permission pops up a system prompt anyway, so
// "silently on by default" does not exist - since it will be interrupted at that moment, turn it


let journey: Recorder | null = null
let tray: Tray | null = null

let autoPaused = false
/** Why the last automatic description did not succeed (empty string = last time succeeded).
 *  **The page must be able to say it**: when the vision model is unreachable the log shows an
 *  HTTP 502 every 3 minutes, while the user only sees a whole page of "not described yet". */
let describeStalled = ''

const TRAY_GLYPH: Record<CaptureState, string> = {
  off: '○', running: '●', paused: '⏸', 'no-permission': '⚠',
}
// A function, not a table built at load time, so it follows the current UI language
const traySay = (st: CaptureState): string => ({
  off: t('Screen activity: not recording'),
  running: t('Screen activity: recording'),
  paused: t('Screen activity: paused'),
  'no-permission': t('Screen activity: cannot capture the screen (grant Screen Recording permission in System Settings)'),
})[st]

/** The menu-bar icon. **The app is in the background most of the time, and this is the only
 *  place the state is always visible** - "is it recording right now" must be answerable without
 *  opening any page (section 8.1). */
function refreshTray() {
  if (!journey) return
  const st = journey.state()
  const n = journey.today().length
  if (!tray) {
    tray = new Tray(nativeImage.createEmpty())
    tray.setIgnoreDoubleClickEvents(true)
  }
  tray.setTitle(`${TRAY_GLYPH[st]}`)
  tray.setToolTip(traySay(st))
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: traySay(st), enabled: false },
    { type: 'separator' },
    // **The menu bar is where the user spends their time**, and "what was recorded today" must
    // be reachable from here - otherwise that page can only be found from the left-bar icon,
    // while the app is mostly not in the foreground at all.
    { label: t('{n} segments recorded today - open', { n }), click: () => openJourneyPage() },
    { type: 'separator' },
    ...(st === 'off'
      ? [{ label: t('Start recording'), click: () => { userStart() } }]
      : st === 'paused'
        ? [{ label: t('Resume recording'), click: () => { userResume() } }]
        : [
            { label: t('Pause for 1 hour'), click: () => { userPause(60) } },
            { label: t('Pause until I turn it on again'), click: () => { userPause() } },
          ]),
    { type: 'separator' },
    { label: t('Stop and turn off'), enabled: st !== 'off', click: () => { journey?.stop(); autoPaused = false; refreshTray() } },
  ]))
}

// The UI and the menu bar are two views of the same state, not two sets of switches (section 8.2) - both go through these four.
function userStart() { journey?.start(); autoPaused = false; refreshTray() }
function userResume() { journey?.resume(); autoPaused = false; refreshTray() }
function userPause(minutes?: number) {
  journey?.pause(minutes ? Date.now() + minutes * 60_000 : undefined)
  autoPaused = false
  refreshTray()
}

/** Bring the window to the front and flip to the "today" page. Shared by the menu bar and the File menu. */
function openJourneyPage() {
  if (!win || win.isDestroyed()) { void boot(); return }
  if (win.isMinimized()) win.restore()
  win.show()
  app.focus({ steal: true })
  win.webContents.send('menu', 'journey')
}

function setupJourneyIpc() {
  // The UI and the menu bar are two views of the same state, not two sets of switches (section 8.2) - both go through here.
  ipcMain.handle('journey:state', () => ({
    state: journey?.state() ?? 'off', today: journey?.today().length ?? 0,
    // Until what time a timed pause lasts, and where automatic description is stuck: the page
    // must be able to answer "why is it not recording / why is nothing described"
    until: journey?.pausedUntil() ?? 0, stalled: describeStalled,
    // While a fake capture source is attached the page must say so (see `readFakeSource`) - the whole premise of this page is trust
    fake: fakeCapture,
  }))
  ipcMain.handle('journey:start', () => { userStart() })
  ipcMain.handle('journey:pause', (_e, minutes: unknown) => {
    userPause(typeof minutes === 'number' && minutes > 0 ? minutes : undefined)
  })
  ipcMain.handle('journey:resume', () => { userResume() })
  ipcMain.handle('journey:stop', () => { journey?.stop(); autoPaused = false; refreshTray() })
}


// Legacy _fake.json acknowledgement: "I know this is not real screen activity" in Chinese.
// Keep accepting the saved marker without printing localized contract data into diagnostics.
const FAKE_OK = '\u6211\u77e5\u9053\u8fd9\u4e0d\u662f\u771f\u7684\u5c4f\u5e55\u6d3b\u52a8'
let fakeCapture = false

function readFakeSource(userData: string): { src: CaptureSource; idleSec: number } | null {
  let j: unknown
  try {
    j = JSON.parse(readFileSync(path.join(userData, 'journey', '_fake.json'), 'utf8'))
  } catch { return null }                      // no such file = the normal case, no noise
  const spec = j as Partial<FakeSpec> & { fake?: unknown; idleSec?: unknown }
  if (spec?.fake !== FAKE_OK) {
    remember('[journey] journey/_fake.json has no valid fake-capture acknowledgement - treating it as absent\n')
    return null
  }
  if (!Array.isArray(spec.windows) || !spec.windows.length) {
    remember('[journey] windows is empty in journey/_fake.json - treating it as absent\n')
    return null
  }

  // over CDP with not one real keyboard or mouse event, so `powerMonitor.getSystemIdleTime()`
  // exceeds `IDLE_SEC` within minutes, and every tick returns at the "person is away, do not
  // record yet" line - not one segment accumulates, which looks like "pressed start recording
  // and nothing happened".
  return { src: fakeSource({ windows: spec.windows, hold: spec.hold, blind: spec.blind }),
           idleSec: typeof spec.idleSec === 'number' ? spec.idleSec : 0 }
}

function setupJourney() {
  const fake = readFakeSource(app.getPath('userData'))
  fakeCapture = !!fake
  if (fake) {
    remember('[journey] **fake capture source**: journey/_fake.json exists, what this instance records is not real screen activity, '
             + `and not one screen is captured (fake "time since last activity" = ${fake.idleSec} seconds). Delete that file and reopen to really record.\n`)
  }
  journey = makeRecorder(app.getPath('userData'), remember,
                         fake ? () => fake.idleSec : () => powerMonitor.getSystemIdleTime(),
                         fake?.src)
  journey.restore()                    // if it was on last time, keep it on - see optIn in capture.ts
  setupJourneyIpc()
  refreshTray()
  setInterval(refreshTray, 60_000)     // segment count and state keep up, no need to wait for the user to open it
  // Auto-pause on lock screen / sleep: there is nothing worth recording on a screen saver, and
  // "still recording while I am away from my seat" is the most unsettling thing.
  // **Only resume a pause that we pressed ourselves.** A "pause until I turn it on again" / "pause
  // for 1 hour" pressed by the user is not turned on again by a lock-screen unlock - that was his

  // "Should pause / should resume / do nothing" is `onPowerEvent` (a pure function in capture.ts,
  // because these four events cannot be laid out in a walkthrough, so a gate has to guard them);
  // only the wiring is left here.
  const onPower = (ev: 'lock' | 'unlock') => {
    const what = onPowerEvent(ev, journey?.state() ?? 'off', autoPaused)
    if (what === 'pause') { journey?.pause(); autoPaused = true; refreshTray() }
    if (what === 'resume') { journey?.resume(); autoPaused = false; refreshTray() }
  }
  const autoPause = () => onPower('lock')
  const autoResume = () => onPower('unlock')
  powerMonitor.on('lock-screen', autoPause)
  powerMonitor.on('suspend', autoPause)
  powerMonitor.on('unlock-screen', autoResume)
  powerMonitor.on('resume', autoResume)
  // While the app is open, catch up on a batch first, so the user does not wait a whole cycle to see the first description.
  setTimeout(() => void describeBacklog(), 30_000)
  setInterval(() => void describeBacklog(), DESCRIBE_EVERY_MS)
}

/** How often to catch up on descriptions and how many segments at a time.
 *  Describing one segment runs the vision model once (measured 15-20 seconds / 2k tokens on the
 *  local GPU), so **small batches, slowly**: do not fight the user for the machine, and do not
 *  pile up a big batch in the background. */
const DESCRIBE_EVERY_MS = 3 * 60_000
const DESCRIBE_BATCH = 4


async function describeBacklog() {
  if (journey?.state() !== 'running') return          // paused / off: do not run
  if (!backend) return
  // **If nothing is left to describe today, catch up on yesterday.** Read from real data in round

  // described - they were captured in that day's last hour; after midnight this only asked about
  // "today", so their turn never came, and three days later the large images expire, so that
  // hour stays "not described yet" forever.
  const days = ['', new Date(Date.now() - 86_400_000).toISOString().slice(0, 10)]
  for (const date of days) {
    try {
      const q = `limit=${DESCRIBE_BATCH}${date ? `&date=${date}` : ''}`
      const r = await fetch(`http://127.0.0.1:${backend.port}/api/journey/catch-up?${q}`, {
        method: 'POST',
        headers: { 'X-User-Id': loadIdentity() ?? '' },
      })
      if (!r.ok) {
        // The backend puts the reason in detail (the "vision failed: ..." one) - keep it for the page to say
        let why = `HTTP ${r.status}`
        try { const d = (await r.json() as { detail?: unknown }).detail; if (typeof d === 'string' && d) why = d } catch { /* no body */ }
        if (describeStalled !== why) remember(`[journey] automatic description failed: ${why}\n`)
        describeStalled = why
        return
      }
      const j = await r.json() as { described?: number; skipped?: number; left?: number }
      if (j.described) remember(`[journey] automatically described ${j.described} segments${date ? ` (${date})` : ''}\n`)
      describeStalled = ''                     // this round went through, the hint on the page should be withdrawn
      // If this day still has work (a batch was described, or some remain), do not touch the day before; only go back when it is really empty
      if (j.described || j.left) break
    } catch (e) {
      // The vision service being unreachable is the normal case (when not on the intranet) and must not flood the log - one line only
      const why = `unreachable: ${e instanceof Error ? e.message : String(e)}`
      if (describeStalled !== why) remember(`[journey] automatic description skipped: ${why}\n`)
      describeStalled = why
      return
    }
  }
}

app.on('window-all-closed', () => {
  // The macOS habit is that closing the window does not quit; but the backend is a child process
  // of this app, and keeping it idling makes no sense - boot() starts another on reactivation.
  backend?.stop()
  backend = null
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (win) return
  if (backend) createWindow(appUrl(backend.port))
  else void boot()
})

// There is more than one exit path (Cmd+Q, closing the window, a crash), and each one has to
// clean up the child process, otherwise an orphan holding the port and sqlite is left behind.
// localStorage (tabs / split view / appearance...) is flushed to disk slowly by Chromium, and
// quitting fast loses it: seen in practice as "pick dark in settings -> reopen is light",
// and client-log confirmed that the value stored last time under the same origin was gone. Force a flush on quit.
app.on('before-quit', (e) => {
  flushThenQuit(e)
  if (!flushed) return
  quitting = true
  try { session.defaultSession.flushStorageData() } catch { /* no session: does not matter */ }
  backend?.stop()
})
process.on('exit', () => backend?.stop())
