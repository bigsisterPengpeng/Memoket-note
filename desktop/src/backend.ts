/**
 * Manage the FastAPI backend as a child process.
 *
 * The desktop app does not rewrite the backend - the 17k-line harness, the KITE adapter and
 * sqlite all live there, and rewriting them would throw away the core of the product. So all
 * Electron does is "start it, wait for it, shut it down".
 */
import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import { createServer } from 'node:net'
import path from 'node:path'

import { t } from './i18n.js'

/** Cut stream data chunks into whole lines before handing them to emit; a half line waits for the next chunk, and whatever is left is flushed when the stream ends. */
export function lineTagger(emit: (line: string) => void) {
  let rest = ''
  const push = (b: Buffer | string) => {
    rest += String(b)
    const parts = rest.split(/\r?\n/)
    rest = parts.pop() ?? ''
    for (const l of parts) emit(l)
  }
  const flush = () => { if (rest) { emit(rest); rest = '' } }
  return { push, flush }
}

export type Backend = {
  port: number

  pid: number
  stop: () => void
}


export class PortTakenError extends Error {
  constructor(readonly port: number, readonly theirPid: number, readonly myPid: number) {
    super(`the backend answering on port ${port} belongs to another instance (pid ${theirPid}, mine is ${myPid})`)
    this.name = 'PortTakenError'
  }
}

/** Get a port: the fixed one first, random only if it is taken.
 *
 * **Do not hard-code 8000.** A backend is often already running by hand on a dev machine (I hit
 * it myself); with a hard-coded port the desktop app either cannot start or silently connects to
 * that stale process - worse than not starting, because the UI looks fine while running
 * someone else's code.
 *
 * **But it cannot be random every time either.** The page origin is `http://127.0.0.1:<port>`,
 * and localStorage is isolated per origin - once the port changes, the state kept in localStorage
 * (tabs, split view, right bar, appearance) is wiped on every launch (seen in practice: pick dark
 * in settings, reopen is light). So first try an unusual fixed port; only if it is really taken
 * (a second copy is open, or the last process has not fully exited) fall back to random, losing
 * state once, which beats failing to start. */

const PREFERRED_PORT = { packaged: 47231, dev: 47232 }

function listenFree(port: number): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer()
    srv.on('error', reject)
    srv.listen(port, '127.0.0.1', () => {
      const addr = srv.address()
      if (addr && typeof addr === 'object') srv.close(() => resolve(addr.port))
      else reject(new Error('could not get a port'))
    })
  })
}


export async function freePort(isPackaged: boolean, log: (line: string) => void = () => {},
                               taken: ReadonlySet<number> = new Set()): Promise<number> {
  const preferred = isPackaged ? PREFERRED_PORT.packaged : PREFERRED_PORT.dev
  // After the previous process got Cmd+Q, uvicorn still needs a second or two to really exit and
  // release the port; reopening right away runs into it. Wait a little before giving up,
  // otherwise "restart once" would wipe the state.
  if (!taken.has(preferred)) {
    for (let i = 0; i < 20; i++) {
      try { return await listenFree(preferred) } catch { await new Promise((r) => setTimeout(r, 250)) }
    }
  }

  // random port every time - the origin differed every time and localStorage was wiped every time
  // (tabs / theme / tray all gone). Try the next few fixed ports in order, so a second copy on the
  // same machine also stays on the same origin.
  for (let k = 1; k <= 8; k++) {
    if (taken.has(preferred + k)) continue
    try {
      const p = await listenFree(preferred + k)
      log(`[desktop] fixed port ${preferred} is taken, using ${p} (tried first next time too)\n`)
      return p
    } catch { /* next one */ }
  }
  const p = await listenFree(0)
  // Goes through onLog rather than console.warn: this line must reach the on-disk log (when a user reports "all my settings are gone", it is the only clue)
  log(`[desktop] fixed port ${preferred} stayed taken, falling back to random port ${p} (localStorage state is lost this time)\n`)
  return p
}

/** Find the python interpreter and the backend directory.
 *
 * In development use the venv in the repo; after packaging it is a single-file executable
 * built by PyInstaller, and then the user's machine **does not need python installed**. */
function locate(isPackaged: boolean, resourcesPath: string) {
  if (isPackaged) {
    const exe = path.join(resourcesPath, 'backend', 'memoket-note-backend')
    return { kind: 'bundled' as const, exe, cwd: path.dirname(exe) }
  }
  const repo = path.resolve(__dirname, '..', '..')
  const venv = path.join(repo, 'backend', '.venv', 'bin', 'python')
  if (!existsSync(venv)) {
    throw new Error(
      t('Cannot find the backend venv: {venv}\nDevelopment mode needs it. Create the virtual environment under backend/ and install the dependencies first.', { venv }))
  }
  return { kind: 'dev' as const, exe: venv, cwd: path.join(repo, 'backend') }
}

/** Wait until the backend can really answer.
 *
 * **Looking at whether the process started is not enough.** A uvicorn process existing does not
 * mean it can take requests: importing the whole app (KITE, model config, sqlite migrations)
 * takes several seconds on a slow machine, and opening the window in that time is a white
 * screen with a refused connection. So poll /api/health until it returns 200. */
export async function waitHealthy(port: number, timeoutMs: number, ownPid?: number): Promise<number> {
  const deadline = Date.now() + timeoutMs
  let lastErr = ''
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/health`)
      if (r.ok) {


        // taken by someone else, and here we still get a perfectly nice 200 - **of someone else's
        // library**. The health check carries the backend's own pid, and comparing two integers
        // tells; a mismatch is a `PortTakenError`, and `startBackend` picks another port and

        const who = (await r.json().catch(() => null)) as { backend?: { pid?: number } } | null
        const theirPid = Number(who?.backend?.pid ?? 0)
        if (ownPid && theirPid && theirPid !== ownPid) throw new PortTakenError(port, theirPid, ownPid)
        return theirPid
      }
      lastErr = `HTTP ${r.status}`
    } catch (e) {
      if (e instanceof PortTakenError) throw e
      lastErr = String((e as Error).message ?? e)
    }
    await new Promise((r) => setTimeout(r, 200))
  }
  throw new Error(t('The backend did not come up within {sec} seconds (last error: {err})', { sec: timeoutMs / 1000, err: lastErr }))
}

export async function startBackend(opts: {
  isPackaged: boolean
  resourcesPath: string
  webDir: string
  /** Where the data goes. **After packaging it must be the system user-data directory** - if not
   *  given, the backend uses the relative path ./data, which inside a .app resolves to the inside
   *  of the bundle: a macOS app bundle is read-only in a real installation, and **on update the
   *  whole bundle is replaced, taking the user's notes with it**.
   *  Hit in practice: the first packaged .app created notes.sqlite3 in
   *  Contents/Resources/backend/data/. */
  dataDir?: string

  journeyDir?: string
  onLog?: (line: string) => void
  timeoutMs?: number
  /** The child process exited **without us asking it to** (crashed, killed by the system). The main process uses this to decide whether to start a new one. */
  onCrash?: (info: string) => void
}): Promise<Backend> {
  const log = opts.onLog ?? (() => {})


  // losing the race, record that port in `taken` and start over with another one. Three attempts
  // because "three copies started at once on one machine" is not a user scenario, while unbounded
  // retries would turn "the backend will not start" into a spinner that never ends.
  const taken = new Set<number>()
  for (let attempt = 1; ; attempt++) {
    try {
      return await spawnOn(opts, log, taken)
    } catch (e) {
      if (!(e instanceof PortTakenError) || attempt >= 3) throw e
      taken.add(e.port)
      log(`[desktop] ${e.message} - trying another port (attempt ${attempt})\n`)
    }
  }
}

async function spawnOn(opts: Parameters<typeof startBackend>[0], log: (line: string) => void,
                       taken: ReadonlySet<number>): Promise<Backend> {
  const port = await freePort(opts.isPackaged, log, taken)
  const { kind, exe, cwd } = locate(opts.isPackaged, opts.resourcesPath)

  const args = kind === 'dev'
    ? ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port)]
    : ['--host', '127.0.0.1', '--port', String(port)]

  const child: ChildProcess = spawn(exe, args, {
    cwd,
    env: {
      ...process.env,
      PYTHONPATH: cwd,
      // The backend uses this to mount the packaged frontend at /, so every relative `/api/...`
      // path in the frontend works unchanged, and desktop and web do not fork.
      MEMOKET_NOTE_WEB_DIR: opts.webDir,
      // Let the backend watch us itself. **stop() is not reliable**: Cmd+Q reaches it, but
      // SIGKILL, a crash, or "Force Quit" in Activity Monitor do not; measured, after a force kill
      // uvicorn survived and kept holding sqlite and the port. The backend exits when it sees os.getppid() change.
      MEMOKET_NOTE_PARENT_PID: String(process.pid),
      ...(opts.dataDir ? { KITE_DATA_DIR: opts.dataDir } : {}),
      ...(opts.journeyDir ? { MEMOKET_JOURNEY_DIR: opts.journeyDir } : {}),
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  // Tag with [backend] line by line: one data chunk often carries several lines (uvicorn's startup
  // lines arrive together), and the old code prefixed only the first line of a chunk, leaving a

  // lines checked). A half line waits for the next chunk; do not split one line into two entries.
  const out = lineTagger((l) => log(`[backend] ${l}\n`)); const err = lineTagger((l) => log(`[backend] ${l}\n`))
  child.stdout?.on('data', out.push)
  child.stderr?.on('data', err.push)
  child.stdout?.on('end', out.flush)
  child.stderr?.on('end', err.flush)

  let exited: string | null = null
  let stopping = false
  let healthy = false
  child.on('exit', (code, signal) => {
    exited = `exit code ${code}${signal ? ` signal ${signal}` : ''}`
    log(`[backend] process ended: ${exited}`)
    // It came up and we did not ask it to stop -> it crashed. Failures during startup take the waitHealthy error path.
    if (healthy && !stopping) opts.onCrash?.(exited)
  })

  try {
    await waitHealthy(port, opts.timeoutMs ?? 60_000, child.pid)
    healthy = true
  } catch (e) {
    // The lost-race case: **our own child process still has to be cleaned up** (it is most
    // likely spinning in EADDRINUSE, or has not yet had time to fail). After killing it, rethrow
    // the `PortTakenError` as is, and `startBackend` starts over on another port; any other
    // error is wrapped as before and reported upward.
    child.kill('SIGKILL')
    if (e instanceof PortTakenError) throw e
    throw new Error(`${(e as Error).message}${exited ? `; child process had ${exited}` : ''}`)
  }

  return {
    port,
    pid: child.pid ?? 0,
    stop: () => {
      stopping = true
      // Ask nicely first, force it if it does not listen. SIGTERM gives uvicorn a chance to close the sqlite connection.
      if (child.exitCode === null && child.signalCode === null) {
        child.kill('SIGTERM')
        setTimeout(() => { try { child.kill('SIGKILL') } catch { /* already gone */ } }, 3000)
      }
    },
  }
}
