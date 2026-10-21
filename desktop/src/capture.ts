
import { execFile } from 'node:child_process'
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { promisify } from 'node:util'

const run = promisify(execFile)

export const INTERVAL_MS = 15_000
const HASH_SIZE = 8
const NEW_SEG_BITS = 18        // above this the picture counts as "changed", cut a segment
const MAX_SEG_MIN = 20         // longest a segment may be, force a cut
export const BLIP_SEC = 60     // switched away and back in less than this: an interlude, merge back into the original segment
const WIDE_RATIO = 2.1         // this much wider than 16:9 is treated as "two windows side by side"
const FRAME_LONG = 1600        // long side of what is stored for description. **Measured: sent as a whole screen, the model cannot read it**
// Once description is done the large image is deleted (plan section 1 item 3: 8 hours = ~960
// images = ~300MB/day, 9GB a month, and that leaves risk sitting on disk). Only a thumbnail this
// long is kept, to find one's way when looking back.
const THUMB_LONG = 256


export const DENY_APPS = [
  '1Password', '1Password 7', 'Keychain Access',
  '\u94a5\u5319\u4e32\u8bbf\u95ee', // Chinese name of Keychain Access (matched against the localized app name)
  'Bitwarden', 'LastPass', 'Dashlane', 'Enpass',
]
// Data, not code text: these match Chinese window titles, so they are kept as \u escapes.
//   \u5bc6\u7801 = "password", \u9690\u79c1\u6d4f\u89c8 = "private browsing", \u65e0\u75d5 = "incognito" (Chinese browser UI),
//   \u94f6\u884c = "bank", \u8f6c\u8d26 = "transfer", \u8d26\u5355 = "bill/statement"
export const DENY_TITLE_WORDS = [
  '\u5bc6\u7801', 'password', '\u9690\u79c1\u6d4f\u89c8', 'private browsing', '\u65e0\u75d5', 'incognito',
  // **The informed-choice screen says "bank"** (the Chinese word for it), while this list
  // originally only blocked "online banking" - "China Merchants Bank", "ICBC" and the like were

  // In this direction err on the side of blocking more: a wrong block just loses one segment, a miss records a bank page.
  '\u94f6\u884c', 'online banking', '\u8f6c\u8d26', '\u8d26\u5355',
]

export type Segment = {
  start: string
  end: string
  app: string
  title: string
  /** Large images for description. **The backend deletes them once description is done**, so this array is empty most of the time. */
  frames: string[]
  /** 256px thumbnail kept to find one's way when looking back - a description without any evidence leaves the user unable to tell whether it is true. */
  thumb?: string
  n: number
}

export type CaptureState = 'off' | 'running' | 'paused' | 'no-permission'

const FRONT_SCRIPT = `
tell application "System Events"
  set p to first application process whose frontmost is true
  set appName to name of p
  try
    set winTitle to name of front window of p
  on error
    set winTitle to ""
  end try
end tell
return appName & "\\n" & winTitle
`

export async function frontApp(): Promise<{ app: string; title: string }> {
  try {
    const { stdout } = await run('osascript', ['-e', FRONT_SCRIPT], { timeout: 5000 })
    const [app = '?', title = ''] = stdout.trim().split('\n')
    return { app, title }
  } catch {
    return { app: '?', title: '' }
  }
}

/** Blacklist. **App names are compared as a whole string, titles by word** - a title is free text, so only keywords can be checked. */
/**
 * Whether this moment should be recorded. **The built-in list is the floor: the user can only add to it, never take from it** -
 * "put the password manager back into the recorded scope" is not an option that should be offered.
 *
 * `extra` is what the user added (exact match for app names, substring for title words). The
 * default blacklist blocks the generic categories, but not "that internal system of our
 * company" or "that website I use for medical visits" - **if users cannot add their own, this
 * feature can only be turned off and left unused** (plan section 1 item 2).
 */
export function denied(app: string, title: string,
                       extra: { apps?: string[]; words?: string[] } | string[] = []): boolean {
  const ex = Array.isArray(extra) ? { apps: extra, words: [] } : extra
  if ([...DENY_APPS, ...(ex.apps ?? [])].includes(app)) return true
  const low = `${app} ${title}`.toLowerCase()
  return [...DENY_TITLE_WORDS, ...(ex.words ?? [])]
    .some((w) => w && low.includes(w.toLowerCase()))
}

/** The user's own blacklist. **Shared with the backend as `<userData>/journey/deny.json`**:
 *  that directory is already one both sides recognize (the shell writes segments, the backend
 *  reads them); the UI edits this list through the backend, and here it is re-read by file
 *  modification time - no new channel between shell and UI. */
export function readDeny(dir: string): { apps: string[]; words: string[] } {
  try {
    const j = JSON.parse(readFileSync(path.join(dir, 'deny.json'), 'utf8')) as Record<string, unknown>
    const list = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [])
    return { apps: list(j.apps), words: list(j.words) }
  } catch {
    return { apps: [], words: [] }
  }
}

export function hamming(a: bigint, b: bigint): number {
  let x = a ^ b
  let n = 0
  while (x) { n += Number(x & 1n); x >>= 1n }
  return n
}


export function mergeBlips(segs: Segment[]): Segment[] {
  const secs = (s: Segment) => (Date.parse(s.end) - Date.parse(s.start)) / 1000
  const touching = (a: Segment, b: Segment) => (Date.parse(b.start) - Date.parse(a.end)) / 1000 < BLIP_SEC
  const out: Segment[] = []
  for (const seg of segs) {
    const last = out[out.length - 1]
    if (last && secs(seg) < BLIP_SEC && last.app === seg.app && touching(last, seg)) {
      last.end = seg.end
      last.n += seg.n
      continue
    }
    out.push({ ...seg })
  }
  const merged: Segment[] = []
  for (let i = 0; i < out.length; i++) {
    const cur = out[i]
    const prev = merged[merged.length - 1]
    const next = out[i + 1]
    if (prev && next && secs(cur) < BLIP_SEC && prev.app === next.app && prev.app !== cur.app
        && touching(prev, cur) && touching(cur, next)) {
      prev.end = next.end
      prev.n += cur.n + next.n
      i++
      continue
    }
    merged.push(cur)
  }
  return merged
}

/** Where today is written: `<userData>/journey/<YYYY-MM-DD>/`. */
export function dayDir(root: string, when = new Date()): string {
  const d = `${when.getFullYear()}-${String(when.getMonth() + 1).padStart(2, '0')}-${String(when.getDate()).padStart(2, '0')}`
  return path.join(root, 'journey', d)
}


const SHELL_OWNED = ['start', 'end', 'app', 'title', 'n'] as const

/** Put the **fields the backend wrote** from the copy on disk back onto the copy about to be
 *  written. Aligned by `start` (the timestamp at the moment the segment was created, never
 *  changed afterwards). A tombstone is taken whole from disk - deleting a segment clears app / title / n together. */
export function keepBackendFields(fresh: Segment[], disk: Segment[]): Segment[] {
  if (!disk.length) return fresh
  const byStart = new Map(disk.map(s => [s.start, s as unknown as Record<string, unknown>]))
  return fresh.map(seg => {
    const old = byStart.get(seg.start)
    if (!old) return seg
    if (old.deleted) return old as unknown as Segment
    const out: Record<string, unknown> = { ...old }
    for (const k of SHELL_OWNED) out[k] = (seg as unknown as Record<string, unknown>)[k]
    return out as unknown as Segment
  })
}


const ORPHAN_GRACE_MS = 2 * 60_000
/** How often to sweep ownerless images. See the comment in `flush()`. */
const SWEEP_EVERY_MS = 10 * 60_000

export function sweepOrphans(dir: string, segs: Segment[], now = Date.now()): number {
  const keep = new Set<string>()
  for (const s of segs) {
    for (const f of s.frames || []) keep.add(path.basename(f))
    if (s.thumb) keep.add(path.basename(s.thumb))
  }
  let n = 0
  for (const sub of ['shots', 'thumbs']) {
    let names: string[] = []
    try { names = readdirSync(path.join(dir, sub)) } catch { continue }
    for (const name of names) {
      if (keep.has(name)) continue
      const f = path.join(dir, sub, name)
      try {
        if (now - statSync(f).mtimeMs < ORPHAN_GRACE_MS) continue
        rmSync(f, { force: true })
        n++
      } catch { /* cannot delete: next time, not worth interrupting recording for */ }
    }
  }
  return n
}

/** How long away counts as "the person is not here". Five minutes is the usual value for this
 *  kind of judgment, and wide enough - reading a long page or listening in a meeting without touching anything never reaches five minutes. */
export const IDLE_SEC = 5 * 60


export function trimIdleTail(segs: Segment[], now: number, idleSec: number): boolean {
  const last = segs[segs.length - 1]
  if (!last) return false
  const at = new Date(now - idleSec * 1000).toISOString()
  if (at >= last.end) return false          // already pulled back / not there yet
  last.end = at < last.start ? last.start : at
  return true
}


export function staleTick(lastAt: number, now: number): boolean {
  return lastAt > 0 && now - lastAt > BLIP_SEC * 1000
}

export function readSegments(dir: string): Segment[] {
  try {
    return JSON.parse(readFileSync(path.join(dir, 'segments.json'), 'utf8')) as Segment[]
  } catch { return [] }
}


//
// Uses `screencapture` + `sips` rather than Electron's `desktopCapturer`: the latter gives
// thumbnails of restricted size, and **measured, the success of this feature hinges on
// resolution** (sent as a whole screen the model cannot read it; cut to one window it can
// recognize the text). Both need the same system permission.

async function shot(to: string): Promise<boolean> {
  try {
    await run('screencapture', ['-x', '-C', '-t', 'png', to], { timeout: 20_000 })
    return existsSync(to) && statSync(to).size > 0
  } catch { return false }
}

/** Image size (`sips` ships with the system, no third-party image library is pulled in). */
async function sizeOf(file: string): Promise<{ w: number; h: number }> {
  const { stdout } = await run('sips', ['-g', 'pixelWidth', '-g', 'pixelHeight', file])
  const w = Number(/pixelWidth:\s*(\d+)/.exec(stdout)?.[1] ?? 0)
  const h = Number(/pixelHeight:\s*(\d+)/.exec(stdout)?.[1] ?? 0)
  return { w, h }
}

/**
 * Perceptual hash (dHash): scale to 9x8 grayscale, compare the size relation of adjacent pixels in each row.
 * Purely local, a few milliseconds - **the vast majority of frames should die at this step**, since the screen does not move most of the day.
 */
async function dhash(file: string, tmpDir: string): Promise<bigint> {
  const small = path.join(tmpDir, '_hash.png')
  await run('sips', ['-z', String(HASH_SIZE), String(HASH_SIZE + 1), file, '--out', small])
  const buf = readFileSync(small)
  // Do not decode the PNG: a rolling hash over the bytes after `sips` scaling already reflects "did the picture change" stably enough
  let bits = 0n
  for (let i = 0; i < buf.length; i++) bits = (bits * 31n + BigInt(buf[i])) & ((1n << 64n) - 1n)
  return bits
}


async function saveFrame(src: string, dst: string, thumb: string, tmpDir: string): Promise<void> {
  const { w, h } = await sizeOf(src)
  let from = src
  if (w / h >= WIDE_RATIO) {
    from = path.join(tmpDir, '_half.png')
    await run('sips', ['-c', String(h), String(Math.floor(w / 2)), src, '--out', from])
  }
  await run('sips', ['-Z', String(FRAME_LONG), from, '--out', dst])
  // **The thumbnail is made here too**: once description is done the large image is deleted
  // (plan section 1 item 3), and by then there is no source left to shrink. This one is kept to
  // find one's way when looking back - a description without any evidence leaves the user unable to tell whether it was made up.
  try { await run('sips', ['-Z', String(THUMB_LONG), from, '-s', 'format', 'jpeg', '--out', thumb]) }
  catch { /* a thumbnail that cannot be stored does not affect this segment */ }
}


export function onPowerEvent(ev: 'lock' | 'unlock', state: CaptureState,
                             autoPaused: boolean): 'pause' | 'resume' | null {
  if (ev === 'lock') return state === 'running' ? 'pause' : null
  return autoPaused && state === 'paused' ? 'resume' : null
}

// ——— Capture source: the real one vs an injected fake ——————————————————————
//

// functions above all need the real Screen Recording permission - if `screencapture` cannot
// capture, the whole path stops. So the cells "a 1-hour pause wakes itself up on time", "locking
// the screen must not undo a pause the user pressed" and "automatic description stopped:

// laying them out takes really pressing "start recording", which would make the walkthrough's
// shell **really start recording the screen and really pop a permission prompt**.
//
// The approach is exactly like `idleSec`: **injected by the caller, this file does not touch
// electron** (`frontend/scripts/check-journey-merge.mts` imports it as a plain module, and one
// added electron line would bring it all down). The default is the real one, so product behavior is unchanged by a single word.

export type CaptureSource = {
  /** Foreground app + window title */
  front: () => Promise<{ app: string; title: string }>
  /** Capture one into `to`. **Returning false = could not capture** (most likely the system took away the Screen Recording permission) */
  shot: (to: string) => Promise<boolean>
  /** Perceptual hash: did the picture change compared with the previous frame */
  hash: (file: string, tmpDir: string) => Promise<bigint>
  /** Store one frame for description + make the thumbnail along the way */
  frame: (src: string, dst: string, thumb: string, tmpDir: string) => Promise<void>
}

/** The real one: `screencapture` + `sips` + `osascript`. **The default**. */
export const REAL_SOURCE: CaptureSource = { front: frontApp, shot, hash: dhash, frame: saveFrame }

/** What the fake capture source should act out. */
export type FakeSpec = {
  /** Take turns being the foreground window. Switch to the next one every `hold` ticks (default 1). */
  windows: { app: string; title: string }[]
  hold?: number
  /** `true` = cannot capture a single frame (takes the `no-permission` path). */
  blind?: boolean
}

/** A 1x1 PNG. **The content does not matter, whether it exists and is non-empty is the criterion** (what `shot()` checks is
 *  `existsSync && size > 0`). */
const PNG_1PX = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64')

/**
 * **Fake capture source**: not one byte of the screen is captured, and no permission is needed.
 *
 * The hash is computed directly from "which window is it now", so "the picture changed" is
 * **laid out on purpose** rather than left to chance: switching windows = the hash differs in all
 * 64 bits, not switching = not one bit differs. This way the whole chain of `changed` checks
 * (segment cut / `tooLong` / `staleTick`) still goes down the real path.
 */
export function fakeSource(spec: FakeSpec): CaptureSource {
  const hold = Math.max(1, spec.hold ?? 1)
  let tick = 0
  const at = () => spec.windows[Math.floor(tick / hold) % spec.windows.length]
  return {
    async front() { const w = at(); tick++; return { app: w.app, title: w.title } },
    async shot(to: string) {
      if (spec.blind) return false
      mkdirSync(path.dirname(to), { recursive: true })
      writeFileSync(to, PNG_1PX)
      return true
    },
    async hash() {
      // A distinct 64-bit number per window: the hamming distance between two adjacent windows is 64,
      // far above NEW_SEG_BITS (18); the distance between two ticks on the same window is 0.
      const i = Math.floor(Math.max(0, tick - 1) / hold) % spec.windows.length
      return ~BigInt(i) & ((1n << 64n) - 1n)
    },
    async frame(_src: string, dst: string, thumb: string) {
      mkdirSync(path.dirname(dst), { recursive: true })
      mkdirSync(path.dirname(thumb), { recursive: true })
      writeFileSync(dst, PNG_1PX)
      writeFileSync(thumb, PNG_1PX)
    },
  }
}

// ——— Loop ————————————————————————————————————————————————

export type Recorder = {
  state: () => CaptureState
  today: () => Segment[]
  /** If it was on when we last quit, turn it back on. Called once at startup. */
  restore: () => void
  start: () => void
  pause: (until?: number) => void
  resume: () => void
  stop: () => void
  /** Until what time "pause for 1 hour" lasts (millisecond timestamp); 0 for an untimed pause / not paused. */
  pausedUntil: () => number
}

/**
 * Resident capture. **Off by default** - the caller must explicitly `start()`, and before that
 * step the user should have seen the informed-choice screen (section 1: the macOS Screen
 * Recording permission pops up a prompt anyway, silently-on-by-default does not exist, so make good use of that moment).
 */
export function makeRecorder(userData: string, log: (s: string) => void,
                            /** Seconds since the last keyboard / mouse input. **Injected by the shell** -
                             *  this file must be importable as a plain module from the cross-check scripts, so it cannot touch electron. */
                            idleSec: () => number = () => 0,
                            /** Where to get the picture from. **The default is the real one** (`REAL_SOURCE`);
                             *  when a walkthrough needs to lay out the "pause / tray / automatic description stopped" cells,
                             *  the shell swaps in `fakeSource(...)`, so real screen recording is not needed. See `CaptureSource`. */
                            src: CaptureSource = REAL_SOURCE): Recorder {
  let state: CaptureState = 'off'
  let timer: NodeJS.Timeout | null = null
  let pauseUntil = 0
  let segs: Segment[] = []
  let dir = ''
  let prevHash: bigint | null = null
  let sweptAt = 0                            // 0 = never swept, sweep on the first write after boot
  let tickAt = 0                             // the moment of the last real sample (see staleTick)
  let wasAway = false                        // log a line only when the state flips, not one every 15 seconds
  const tmp = path.join(userData, 'journey', '_tmp')
  // Whether it is on is **the user's choice, not the process's state**: after quit and reopen it
  // must still be on, otherwise a stretch of some day's record goes silently missing while the user thinks it was always recording.
  // A pause is not written to disk - "pause for an hour" is temporary, and reopening treats it as over.
  const optIn = path.join(userData, 'journey', 'on')
  // The user's own blacklist: re-read only when the file changed (a tick every 15 seconds is not worth reading the disk each time)
  const denyFile = path.join(userData, 'journey', 'deny.json')
  let denyAt = 0
  let denyList = { apps: [] as string[], words: [] as string[] }
  const deny = () => {
    let at = 0
    try { at = statSync(denyFile).mtimeMs } catch { /* no such file = never added */ }
    if (at !== denyAt) { denyAt = at; denyList = readDeny(path.join(userData, 'journey')) }
    return denyList
  }
  const remember = (on: boolean) => {
    try { on ? (mkdirSync(path.dirname(optIn), { recursive: true }), writeFileSync(optIn, '1')) : rmSync(optIn, { force: true }) }
    catch (e) { log(`[journey] could not remember the switch: ${String(e)}\n`) }
  }

  const flush = () => {
    try {
      const out = keepBackendFields(mergeBlips(segs), readSegments(dir))
      writeFileSync(path.join(dir, 'segments.json'), JSON.stringify(out, null, 1), 'utf8')
      // **Not swept on every write.** Writes happen on every segment cut (measured, every 25
      // seconds when busy), and `mergeBlips` merges a few short segments on the spot each time,
      // leaving a few ownerless images - so the log got a "cleared 2" line every 25 seconds and
      // the disk kept churning. These images are not urgent: the current policy keeps
      // **undescribed large images** for 3 days anyway (`FRAME_KEEP_DAYS`), and sweeping every ten
      // minutes is already far stricter. Sweep once at boot (what the last quit left behind).
      if (Date.now() - sweptAt >= SWEEP_EVERY_MS) {
        sweptAt = Date.now()
        const gone = sweepOrphans(dir, out)
        if (gone) log(`[journey] cleared ${gone} unclaimed screenshots\n`)
      }
    } catch (e) { log(`[journey] writing to disk failed: ${String(e)}\n`) }
  }

  async function tick() {

    // walkthrough: the first line used to be `state !== 'running' -> return`, and `pause(until)`
    // sets state to paused, so "pause for 1 hour" was exactly the same as "pause until I turn it
    // on again" - come back from lunch, and the whole afternoon was not one segment recorded,
    // with the tray still showing the pause icon.
    if (state === 'paused' && pauseUntil && Date.now() >= pauseUntil) {
      pauseUntil = 0
      state = 'running'
      log('[journey] pause expired, resuming recording\n')
    }
    if (state !== 'running') return

    const today = dayDir(userData)
    if (today !== dir) {                       // new day: switch to that day's directory, start over
      dir = today
      mkdirSync(path.join(dir, 'shots'), { recursive: true })
      mkdirSync(path.join(dir, 'thumbs'), { recursive: true })
      segs = readSegments(dir)
      prevHash = null
    } else if (!existsSync(dir)) {

      // walkthrough: the backend's `DELETE /day` rmtree's the whole directory, while the segment
      // table in memory here is still there - every write after that gave ENOENT (not one segment
      // could be recorded all afternoon, the log flooded with "writing to disk failed"), and
      // worse, once the backend's next `_save` recreates the directory, **this code would write
      // the dozens of deleted segments back as they were** - the user thinks the day they wiped has grown back. Treat it as a new day and record from scratch.
      mkdirSync(path.join(dir, 'shots'), { recursive: true })
      mkdirSync(path.join(dir, 'thumbs'), { recursive: true })
      segs = []
      prevHash = null
      log('[journey] today\'s directory is gone (most likely the day was deleted), recording from scratch\n')
    }

    // **No recording while the person is away.** Screen on != someone is working (see the
    // comment on `trimIdleTail`). Same reason as lock-screen / sleep auto pause: "still recording while I am away from my seat" is the most unsettling thing.
    const away = idleSec()
    if (away >= IDLE_SEC) {
      if (trimIdleTail(segs, Date.now(), away)) flush()
      if (!wasAway) { wasAway = true; log(`[journey] person is away (${Math.round(away / 60)} minutes idle), not recording for now\n`) }
      return
    }
    if (wasAway) { wasAway = false; log('[journey] person is back, recording again\n') }

    const { app, title } = await src.front()

    // forward either** - it used to be extended to now here, so two hours on a bank page showed up

    if (denied(app, title, deny())) return

    const raw = path.join(tmp, 'now.png')
    if (!await src.shot(raw)) {
      // **The system taking the permission away is the nastiest kind**: the user thinks it is
      // recording, but it broke long ago. Change state actively, and the tray icon follows to the warning icon (docs/daily-journey-plan.md section 8.5).
      if (state !== ('no-permission' as CaptureState)) {
        state = 'no-permission'
        log('[journey] cannot capture the screen - most likely Screen Recording permission was not granted\n')
      }
      return
    }
    if ((state as CaptureState) === 'no-permission') state = 'running'

    const h = await src.hash(raw, tmp)
    const now = new Date().toISOString()
    const cur = segs[segs.length - 1]
    const tooLong = cur && Date.now() - Date.parse(cur.start) > MAX_SEG_MIN * 60_000
    // **Start a new segment after a gap** (see `staleTick`): after sleeping three hours and
    // waking, the foreground window is still the same one, and without cutting a segment this
    // segment's `end` would jump straight to now - the daily report would say "3 hours without interruption".
    const gap = staleTick(tickAt, Date.now())
    const changed = !cur || cur.app !== app || cur.title !== title
      || (prevHash !== null && hamming(prevHash, h) > NEW_SEG_BITS) || tooLong || gap
    tickAt = Date.now()

    if (changed) {
      const stem = String(segs.length + 1).padStart(3, '0')
      const frame = path.join(dir, 'shots', `${stem}.png`)
      const thumb = path.join(dir, 'thumbs', `${stem}.jpg`)
      try { await src.frame(raw, frame, thumb, tmp) } catch { /* cannot store: this segment has no image */ }
      segs.push({ start: now, end: now, app, title, frames: [frame], thumb, n: 1 })
      flush()                                  // write once per segment cut: a crash must not lose everything
    } else {
      cur.end = now
      cur.n += 1
    }
    prevHash = h
    try { rmSync(raw, { force: true }) } catch { /* the original image is not kept */ }
  }

  return {
    state: () => state,
    today: () => mergeBlips(readSegments(dayDir(userData))),
    restore() {
      if (existsSync(optIn)) { log('[journey] it was on last time, continuing\n'); this.start() }
    },
    start() {
      if (timer) return
      remember(true)
      mkdirSync(tmp, { recursive: true })
      state = 'running'
      pauseUntil = 0
      log('[journey] recording started\n')
      timer = setInterval(() => { void tick() }, INTERVAL_MS)
      void tick()
    },
    pause(until?: number) {
      pauseUntil = until ?? 0
      state = 'paused'
      log(until ? `[journey] paused until ${new Date(until).toLocaleTimeString()}\n` : '[journey] paused\n')
    },
    resume() {
      if (!timer) return
      pauseUntil = 0
      state = 'running'
      log('[journey] recording resumed\n')
    },
    pausedUntil: () => (state === 'paused' ? pauseUntil : 0),
    stop() {
      if (timer) { clearInterval(timer); timer = null }
      remember(false)
      state = 'off'
      try { rmSync(tmp, { recursive: true, force: true }) } catch { /* does not matter */ }
      log('[journey] recording stopped\n')
    },
  }
}
