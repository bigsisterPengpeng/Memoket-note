/** Local workspace API. X-User-Id selects data; it does not authenticate requests. */
import type { DocIntent } from './util/docIntent'
import type { SavedLayer } from './util/changeLayers'
import type { NoteRoundsPayload } from './util/roundsRestore'

export type Note = {
  id: string
  user_id: string
  title: string
  content: string
  pinned: boolean
  /** Note icon (boxicons class name, empty = default) */
  icon?: string
  /** When it was ingested into the knowledge base (empty = never ingested) */
  ingested_at?: string
  /** Where it was imported from, the source-side id, last import time (empty = written locally) */
  source?: string
  source_id?: string
  imported_at?: string
  /** The writing skeleton travels with the note. It used to live only in frontend memory, lost on switching notes / refreshing / when endless writing
   * auto-followed to the next page -- while the harness uses it as the main thread every round. */
  spine: string
  beats: string[]

  intent?: DocIntent
  created_at: string
  updated_at: string
}

/** A tree node = one branch + display info of that note.
 *
 * **There is no Folder type any more.** As in Trilium: a folder is not a kind of thing; any note with children
 * is a folder. So "New folder" = new note, "Rename folder" = change the title,
 * "Delete folder" = delete the note (with its subtree). */
export type TreeRow = {
  id: string                 // branch id
  note_id: string
  parent_note_id: string     // ROOT_ID = hangs off the tree root
  position: number
  is_expanded: boolean
  title: string
  /** Start of the body. When the title is empty or still a placeholder, the tree uses it as the display name. */
  preview: string
  pinned: boolean
  /** Note icon (boxicons class name, empty = default for folder / note) */
  icon?: string
  /** Where this note came from: obsidian / notion / feishu / apple / plan, empty = written by you.
   *  The tree picks the default icon by it (util/noteSource). `created_at` is not in tree rows -- see
   *  docs/sidebar-ia-plan.md §3. */
  source: string
  updated_at: string
  child_count: number
  /** How many facts this note cites. The tree draws a badge -- telling at a glance which notes are "grounded"
   *  and which are still drafts. See docs/kb-fusion-design.md. */
  cite_count: number
  /** When it was ingested into the knowledge base. Empty = never ingested. */
  ingested_at: string
  /** Only for nodes of the knowledge-base virtual subtree: how many facts are under it. Always 0 for real notes. */
  fact_count: number
  /** How many branches this note has in total. >1 means a clone, which the tree must mark -- users must know
   *  editing here changes the other places too. */
  branch_count: number
}

export const ROOT_ID = 'root'

export type Fact = {
  id: string
  text: string
  when: string
  kind: string
  sources: string[]
}

export type Revision = {
  id: string
  op: 'insert' | 'delete' | 'replace' | 'insert_before'
  anchor: string
  /** End marker. Since the anchor contract became "locate by short markers", what changes is
   * the whole span from the start of anchor to the end of anchor_end -- the model does not have to copy the whole passage. */
  anchor_end?: string
  text: string
  reason: string
  sources: string[]
}

import { getLang } from './i18n'

const USER_KEY = 'memoket-note-user'

export function getUser(): string {
  // `?user=xxx` wins, and is remembered. The desktop app uses it to open as a given identity (`electron . --user=`),
  // and the web build uses it for "open this link as another identity" -- otherwise a new environment always gets a random
  // user, sees an empty library, and easily mistakes it for "the data is gone".
  const fromUrl = new URLSearchParams(location.search).get('user')?.trim()
  if (fromUrl) {
    localStorage.setItem(USER_KEY, fromUrl)
    rememberOnce(fromUrl)
    return fromUrl
  }
  let u = localStorage.getItem(USER_KEY)
  if (!u) {
    u = 'user-' + Math.random().toString(36).slice(2, 8)
    localStorage.setItem(USER_KEY, u)
  }
  rememberOnce(u)
  return u
}

/** Tell the desktop shell the chosen identity once (it writes identity.json). getUser is called on every request,
 *  so this reports only once; switching identity (setUser) reports again. */
let remembered = ''
function rememberOnce(u: string) {
  if (u === remembered) return
  remembered = u
  try { (window as Window & { memoketDesktop?: { rememberUser?: (u: string) => void } }).memoketDesktop?.rememberUser?.(u) } catch { /* the web build has no shell */ }
}

export function setUser(u: string) {
  localStorage.setItem(USER_KEY, u.trim() || 'default')
  rememberOnce(u.trim() || 'default')
}

/** Where to go after switching to `user`: replace `?user=` with the new identity, keep other parameters as they are.
 *  **Must not reload as-is**: the desktop app always opens with `?user=<last identity>`, and in `getUser()`
 *  the address wins -- a plain refresh would write the just-saved new identity back to the old one, identity.json included,
 *  looking like "clicking Switch user did nothing". */
export function switchUserHref(href: string, user: string): string {
  const url = new URL(href)
  url.searchParams.set('user', user)
  return url.toString()
}

function headers(extra: Record<string, string> = {}) {
  // `X-Lang`: the backend picks the language of human-facing text (errors, stop reasons, job details)
  return { 'X-User-Id': getUser(), 'X-Lang': getLang(), ...extra }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    // FastAPI's error body is {"detail": "…"}: pull out that human sentence, so no blob of JSON shows up in a toast
    const text = await res.text()
    let detail = text
    try {
      const parsed = JSON.parse(text) as { detail?: unknown }
      if (typeof parsed.detail === 'string') detail = parsed.detail
      else if (Array.isArray(parsed.detail)) detail = parsed.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ')
    } catch { /* not JSON: keep as-is */ }
    throw new Error(`${res.status} ${detail}`)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------- notes

/** Lightweight rows for ⌘K / `[[` completion: no full text (with full text a 413-note library is 580KB per fetch, fetched on every keystroke). */
export type NoteBrief = {
  id: string; title: string; updated_at: string; pinned: boolean
  /** Note icon (boxicons class name, empty = default) */
  icon?: string
  preview: string; has_body: boolean; first_body?: string
  snippet: { before: string; hit: string; after: string } | null
}
export const listNotesBrief = (q = '') =>
  fetch(`/api/notes/brief${q ? `?q=${encodeURIComponent(q)}` : ''}`, { headers: headers() }).then(json<{ notes: NoteBrief[]; total: number }>)

export const listNotes = (q = '') =>
  fetch(`/api/notes${q ? `?q=${encodeURIComponent(q)}` : ''}`, { headers: headers() }).then(json<Note[]>)

export const getNote = (id: string) =>
  fetch(`/api/notes/${id}`, { headers: headers() }).then(json<Note>)

export const createNote = (title: string, content: string, parent_note_id: string = ROOT_ID) =>
  fetch('/api/notes', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ title, content, parent_note_id }),
  }).then(json<Note>)

export const saveNote = (id: string, title: string, content: string) =>
  fetch(`/api/notes/${id}`, {
    method: 'PUT',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ title, content }),
  }).then(json<Note>)

export const deleteNote = (id: string) =>
  fetch(`/api/notes/${id}`, { method: 'DELETE', headers: headers() }).then(json)

/** Set a note's icon (Trilium's NoteIcon); empty string = clear */
export const setNoteIcon = (id: string, icon: string) =>
  fetch(`/api/notes/${id}/icon`, { method: 'POST', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify({ icon }) }).then(json<Note>)

export const togglePin = (id: string) =>
  fetch(`/api/notes/${id}/pin`, { method: 'POST', headers: headers() }).then(json<Note>)

// ---------------------------------------------------------------- note tree
//
// The subject of operations is the **branch** (which note · under which parent), not the note: one note
// can live in several places at once, so "move this note" has no clear target.

/** Get the whole tree at once. Fetching level by level on demand would make "expand a node" a network round trip,
 *  and the tree would stutter. */
export const getTree = () =>
  fetch('/api/tree', { headers: headers() }).then(json<TreeRow[]>)

/** Hang an existing note in another place = **clone**. Not a copy: the two places are the same note,
 *  editing one changes all. */
export const cloneNoteTo = (note_id: string, parent_note_id: string) =>
  fetch('/api/tree/branches', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ note_id, parent_note_id }),
  }).then(json<TreeRow>)

/** Remove a branch -- only "no longer shown in this place"; the note itself still lives elsewhere.
 *  The last one cannot be removed (the backend returns 400): that would not be deletion, it would be loss. */
export const detachBranch = (note_id: string, parent_note_id: string) =>
  fetch(`/api/tree/branches?note_id=${encodeURIComponent(note_id)}`
        + `&parent_note_id=${encodeURIComponent(parent_note_id)}`,
        { method: 'DELETE', headers: headers() }).then(json)

/** Drag reorder: renumber a parent's children in the given order. */
export const reorderBranches = (parent_note_id: string, order: string[]) =>
  fetch('/api/tree/branches/reorder', {
    method: 'PATCH',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ parent_note_id, order }),
  }).then(json<{ parent: string; count: number }>)

export const moveBranch = (
  note_id: string, from_parent_id: string, to_parent_id: string,
  position?: number,
) =>
  fetch('/api/tree/branches/move', {
    method: 'PATCH',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ note_id, from_parent_id, to_parent_id, position }),
  }).then(json)

/** Expanded state is stored in the library, not in frontend memory -- a tree that collapses on every refresh is unusable
 *  after a few dozen nodes. */
export const setBranchExpanded = (
  note_id: string, parent_note_id: string, expanded: boolean,
) =>
  fetch('/api/tree/branches/expanded', {
    method: 'PATCH',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ note_id, parent_note_id, expanded }),
  }).then(json)

/** All places of this note in the tree. After cloning "where is it" has no unique answer -- the breadcrumb must show
 *  the path the user actually came in by, so the caller picks one. */
export const notePaths = (note_id: string) =>
  fetch(`/api/tree/paths/${note_id}`, { headers: headers() }).then(json<string[][]>)

// ---------------------------------------------------------------- personal preferences
//
// Independent of the knowledge base: no LLM extraction, maintained by the user directly, read when the three writing tools generate.

export type ProfileEntry = { id: string; user_id: string; text: string; created_at: string }

export const listProfile = () =>
  fetch('/api/profile', { headers: headers() }).then(json<ProfileEntry[]>)

export const addProfileEntry = (text: string) =>
  fetch('/api/profile', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ text }),
  }).then(json<ProfileEntry>)

export const deleteProfileEntry = (id: string) =>
  fetch(`/api/profile/${id}`, { method: 'DELETE', headers: headers() }).then(json)

// ---------------------------------------------------------------- writing


export const genSkeleton = (title: string, content: string, intent = '', signal?: AbortSignal) =>
  fetch('/api/skeleton', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ title, content, intent }),
    signal,
  }).then(json<{ spine: string; beats: string[]; notes?: string[]; took_ms: number }>)


export const saveIntent = (noteId: string, intent: DocIntent) =>
  fetch(`/api/notes/${noteId}/intent`, {
    method: 'PUT', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify(intent),
  }).then(json<Note>)


export type TrayKind = 'note' | 'fact' | 'import' | 'selection'
export type TrayItem = {
  id: string; kind: TrayKind; ref_id: string; title: string; excerpt: string; position: number; added_at: string
}
export type TrayItemIn = { id?: string; kind: TrayKind; ref_id?: string; title?: string; excerpt?: string }
export const listTray = (noteId: string) =>
  fetch(`/api/notes/${noteId}/tray`, { headers: headers() }).then(json<{ items: TrayItem[] }>).then((r) => r.items)
/** Replace the whole thing (order = array order): adding, deleting and reordering all go through here. Returns the persisted copy. */
export const putTray = (noteId: string, items: TrayItemIn[]) =>
  fetch(`/api/notes/${noteId}/tray`, {
    method: 'PUT', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify({ items }),
  }).then(json<{ items: TrayItem[] }>).then((r) => r.items)
export const deleteTrayItem = (noteId: string, itemId: string) =>
  fetch(`/api/notes/${noteId}/tray/${itemId}`, { method: 'DELETE', headers: headers() })
    .then(json<{ items: TrayItem[] }>).then((r) => r.items)

export const clipToTray = (noteId: string, url: string) =>
  fetch(`/api/notes/${noteId}/tray/clip`, {
    method: 'POST', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify({ url }),
  }).then(json<{ items: TrayItem[] }>).then((r) => r.items)

// ---------------------------------------------------------------- selected-text actions
//
// Triggered by right-clicking a selected passage. All produce results of the same Revision shape,
// reusing the same accept/reject UI.


export type EditResult = {
  revisions: Revision[]
  took_ms: number
  note?: string
  unparsed?: boolean
}

export const rewriteSelection = (
  content: string, selection: string, intent: 'rewrite' | 'polish', spine: string, beats: string[], signal?: AbortSignal,

  docIntent = '',
) =>
  fetch('/api/rewrite', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ content, selection, intent, spine, beats, doc_intent: docIntent }),
    signal,
  }).then(json<EditResult>)

export const expandSelection = (content: string, selection: string, signal?: AbortSignal, intent = '', noteId = '') =>
  fetch('/api/expand', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),

    body: JSON.stringify({ content, selection, scope: memoryScope(), intent, note_id: noteId }),
    signal,
  }).then(json<EditResult>)

/** Verdict values as the backend emits them (Chinese literals, kept as unicode escapes until the backend speaks English). */
export const VERDICT = { contradicts: '\u77db\u76fe', supports: '\u652f\u6301', unknown: '\u65e0\u6cd5\u5224\u65ad' } as const
export type Verdict = typeof VERDICT[keyof typeof VERDICT]

export type VerifyFinding = {
  verdict: Verdict
  reason: string
  fact_id: string
  fact_text: string
  sources: string[]
}

export const verifySelection = (content: string, selection: string, signal?: AbortSignal, intent = '', noteId = '') =>
  fetch('/api/verify', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ content, selection, scope: memoryScope(), intent, note_id: noteId }),
    signal,
  }).then(json<VerifyResult>)


export type VerifyResult = {
  findings: VerifyFinding[]
  took_ms: number
  /** Old backends lack these two fields; they default to "0 records found / the model answered fine", and the wording falls back to the old sentence. */
  checked?: number
  unparsed?: boolean
}

export type TapMeta = {
  facts: number; recall_ms: number; grounded: boolean
  sources: string[]; fact_ids: string[]
  /** The memory scope used for this continuation (echoed back by the backend) */
  scope?: string
  /** Why not a single material was picked (filtered by scope / empty library / tail matched nothing); empty string = some were picked */
  why_empty?: string
}

/** Split one SSE stream into `{event, payload}` frames.
 *
 * Before this was extracted, the "read chunk -> split frames on blank lines -> recognize event:/data: -> JSON.parse" logic
 * had **five copies** in this file, already inconsistent: the block-generation copy put the event name inside
 * the frame loop (right), the other four outside -- so a data:-only frame would inherit the previous frame's
 * event name. The backend always sends them in pairs so it never blew up, but it was a dud bomb. Only the block-generation copy
 * skipped unparseable frames; the other four threw, cutting off the whole stream.
 *
 * Now fixed in one place, right in five: **event names are per frame**, **unparseable frames are skipped** -- giving up
 * a whole generation over one bad frame costs tens of seconds of work.
 */
export async function* sseFrames(
  res: Response,
): AsyncGenerator<{ event: string; payload: any }> {
  if (!res.body) throw new Error('no stream')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    // SSE frames are separated by blank lines; the last piece may be incomplete and stays in the buffer for the next chunk
    const frames = buf.split('\n\n')
    buf = frames.pop() ?? ''
    for (const frame of frames) {
      let event = ''
      let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      let payload: any
      try { payload = JSON.parse(data) } catch { continue }
      yield { event, payload }
    }
  }
}


/** magic tap: SSE streaming continuation. onMeta arrives first (retrieval results), onDelta chunk by chunk. */
export async function magicTap(
  content: string,
  spine: string,
  beats: string[],
  onMeta: (m: TapMeta) => void,
  onDelta: (s: string) => void,
  signal?: AbortSignal,
  /** Deterministic check after writing: how many materials were retrieved, how many were really used in the body.
   * When none was used, hint gives a one-line diagnosis -- magic tap deliberately does not wrap the full scoring loop
   * (it is meant to be one click, a paragraph in seconds), so this only hints, never interrupts or rewrites. */
  onGrounding?: (g: { facts: number; used: number; hint: string; notes?: string[] }) => void,
  /** The body already after the cursor: with it, this inserts a passage in the middle (continuing content, connecting to following). */
  following = '',
  /** Note title: while the body is still short, it is the only direction the model knows */
  title = '',

  intent = '',

  noteId = '',
): Promise<{ truncated: boolean; fakeCitations: string[] }> {
  const res = await fetch('/api/magic-tap', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ content, spine, beats, following, title, scope: memoryScope(), intent, note_id: noteId }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`magic-tap failed: ${res.status}`)

  let truncated = false
  let fakeCitations: string[] = []
  for await (const { event, payload } of sseFrames(res)) {
    if (event === 'meta') onMeta(payload as TapMeta)
    else if (event === 'delta') onDelta(payload.text as string)
    else if (event === 'grounding') onGrounding?.(payload)
    else if (event === 'done') { truncated = !!payload.truncated; fakeCitations = (payload.fake_citations as string[] | undefined) ?? [] }
    else if (event === 'error') throw new Error(payload.detail)
  }
  return { truncated, fakeCitations }
}

export type SlidesResult = {
  pages: number
  cite_coverage: number
  notes: string[]
  note_id: string
  truncated: boolean
}

/** This note -> a slides note (pain point 6). **The product is a note, not a file**:
 *  it lands as a child of the original note, so it can be found by ⌘K, carry citations, be further edited by continue, and be exported.
 *  One model call, not part of the multi-round loop -- slides are a one-shot restructuring. */
export async function makeSlides(
  noteId: string, content: string, title: string,
  style: 'points' | 'talk',
  onDelta: (s: string) => void,
  signal?: AbortSignal,
): Promise<SlidesResult> {
  const res = await fetch('/api/slides', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ note_id: noteId, content, title, style }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`slides failed: ${res.status}`)
  let out: SlidesResult = { pages: 0, cite_coverage: 0, notes: [], note_id: '', truncated: false }
  for await (const { event, payload } of sseFrames(res)) {
    if (event === 'delta') onDelta(payload.text as string)
    else if (event === 'slides') out = payload as SlidesResult
    else if (event === 'error') throw new Error(payload.detail)
  }
  return out
}

// ---------------------------------------------------------------- endless writing plan
//
// A folder-level writing harness, not the note-level "click to continue" -- a persisted
// plan (goal + ordered list of sections), each section lands as a note; after all current
// sections are written it automatically asks once "is there more", which decides when it really stops,
// not a round cap. Disconnecting (clicking stop) only pauses; the plan stays active, and the next run() continues
// from the breakpoint.

export type WritingSection = {
  id: string; plan_id: string; idx: number; title: string
  status: 'pending' | 'in_progress' | 'done'
  note_id: string; summary: string; created_at: string
}

export type WritingPlan = {
  id: string; user_id: string; parent_note_id: string; goal: string
  status: 'active' | 'done' | 'abandoned'
  doc_note_id: string; created_at: string; updated_at: string
}

export type WritingPlanOut = { plan: WritingPlan | null; sections: WritingSection[] }

export const getWritingPlan = (folderId: string) =>
  fetch(`/api/writing-plan?parent_note_id=${encodeURIComponent(folderId)}`, { headers: headers() })
    .then(json<WritingPlanOut>)


export const startWritingPlan = (folderId: string, goal: string, signal?: AbortSignal) =>
  fetch('/api/writing-plan/start', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ parent_note_id: folderId, goal, scope: memoryScope() }),
    signal,
  }).then(json<WritingPlanOut>)

/** Abandon the current plan, so the same folder can restart with a different goal.
 *  Without it, once a folder had a plan it could never be replaced -- the panel would keep showing that old goal. */
export const abandonWritingPlan = (folderId: string) =>
  fetch(`/api/writing-plan/${folderId}/abandon`, { method: 'POST', headers: headers() })
    .then(json<{ abandoned: string }>)

export type WritingPlanHandlers = {
  onPlanLoaded?: (plan: WritingPlan, sections: WritingSection[]) => void
  onSectionStart?: (d: { section_id: string; title: string; note_id: string; is_new_note: boolean; facts: number }) => void
  onDelta?: (noteId: string, text: string) => void
  /** The server's authoritative body at the end of a round / section (STEP_FINISHED / RUN_FINISHED carry content) --
   *  the same idea as the single-note harness's onRoundEnd: align what was accumulated locally with the server. */
  onNoteContent?: (noteId: string, content: string) => void
  onSectionDone?: (d: { section_id: string; summary: string; forced: boolean; blocked: boolean; blocked_reason: string | null }) => void
  onPlanExtended?: (sections: WritingSection[]) => void
  onPlanDone?: (plan: WritingPlan) => void
}

/** Run the harness main loop, streaming back over SSE; one note_id runs through all deltas of a section,
 * and once section-start switches note_id, the frontend must switch the currently open
 * note itself to keep showing the new content. Aborting via the signal = pause; the server notices the disconnect on its next loop
 * and stops, the plan state is unchanged, and calling again later continues. */
export async function runWritingPlan(
  folderId: string,
  handlers: WritingPlanHandlers,
  signal?: AbortSignal,
) {
  const res = await fetch('/api/writing-plan/run', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ parent_note_id: folderId, scope: memoryScope() }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`writing-plan run failed: ${res.status}`)

  // Events inside a section use AG-UI names (loop.run goes straight to_sse); the outer plan events still use
  // custom names. **This used to only recognize the old 'delta'**: after the backend switched to AG-UI the endless-writing follow view

  // section-start.
  let noteId = ''
  for await (const { event, payload } of sseFrames(res)) {
    if (event === 'plan-loaded') handlers.onPlanLoaded?.(payload.plan, payload.sections)
    else if (event === 'section-start') { noteId = payload.note_id; handlers.onSectionStart?.(payload) }
    else if (event === 'TEXT_MESSAGE_CONTENT') handlers.onDelta?.(noteId, payload.delta)
    else if (event === 'delta') handlers.onDelta?.(payload.note_id ?? noteId, payload.text)
    else if (event === 'STEP_FINISHED' || event === 'RUN_FINISHED') {
      if (typeof payload.content === 'string' && payload.content) handlers.onNoteContent?.(noteId, payload.content)
    }
    else if (event === 'section-done') handlers.onSectionDone?.(payload)
    else if (event === 'plan-extended') handlers.onPlanExtended?.(payload.sections)
    else if (event === 'plan-done') handlers.onPlanDone?.(payload.plan)
    else if (event === 'error') throw new Error(payload.detail)
  }
}

// ---------------------------------------------------------------- memory

/** Memory scope (database/kb/scope.py): all / only ingested notes / only meeting records / only imports.
 *  Stored in localStorage and carried by recall / relations / continue; switched at the top of the right pane's "Memory". */
export type MemoryScope = 'all' | 'notes' | 'meetings' | 'imports' | 'screen'
export const MEMORY_SCOPE_KEY = 'memoket-note:memory-scope'
/** Same as backend `kb/scope.SCOPE_LABEL`. **"All" excludes screen activity**, so the label says so:
 *  with dozens of screen-record segments a day mixed into "Related memory", this column would turn from meeting conclusions into "you looked at some web page last Tuesday". */
export const SCOPE_LABEL: Record<MemoryScope, string> = { all: 'All (excluding screen)', notes: 'Notes only', meetings: 'Meetings only', imports: 'Imports only', screen: 'Screen activity only' }
export function memoryScope(): MemoryScope {
  // 'screen' used to be missing from this whitelist: the dropdown could select "screen activity only", but reading back gave 'all' --

  try { const v = localStorage.getItem(MEMORY_SCOPE_KEY); return v === 'notes' || v === 'meetings' || v === 'imports' || v === 'screen' ? v : 'all' } catch { return 'all' }
}
export function setMemoryScope(s: MemoryScope) {
  try { localStorage.setItem(MEMORY_SCOPE_KEY, s) } catch { /* does not matter */ }
  window.dispatchEvent(new CustomEvent('memory-scope-changed', { detail: s }))
}
export const recall = (query: string, limit = 8, relaxed = false) =>
  fetch('/api/memory/recall', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ query, limit, scope: memoryScope(), relaxed }),
  }).then(json<{ facts: Fact[]; took_ms: number; terms: string[]; evidence?: RecallEvidence[]; kb_empty?: boolean; why_empty?: '' | 'no_terms' | 'weak'; relaxed?: boolean; can_expand?: boolean }>)


export type RecallEvidence = { term: string; why: 'vocab' | 'span' | 'pair'; units: number }

/** "Background": given a passage of body, return how the things it touches evolved over time.
 *
 * **There is no free-form question API any more.** The question is built by the backend; the user writes not a word -- criterion 1:
 * a chat input box appearing in the UI means we did not encapsulate the intent well. The old /api/memory/ask
 * still exists (this one is built on it), but has no external entry point any more. */
/** A fact + its original words, for the inline source popover. */
export type FactPeek = {
  id: string; text: string; when: string; kind: string; sources: string[]
  topics: string[]; entities: string[]
  entity_names?: string[]   // entity display names, one to one with entities
}

/** Get a fact by id. **404 when not found** -- a citation pointing at a nonexistent fact is a real problem
 *  (made up by the model, or the knowledge base was rebuilt); the popover must say so rather than show plain text. */
export const factPeek = (id: string) =>
  fetch(`/api/memory/facts/${encodeURIComponent(id)}`, { headers: headers() })
    .then((r) => (r.ok ? (r.json() as Promise<FactPeek>) : null))

// ---------------------------------------------------------- knowledge-base virtual subtree
//
// The knowledge base grows at the bottom of the note tree as a **virtual** subtree (docs/kb-fusion-design.md §3.2):
// not persisted, just KITE's data presented as the same kind of rows as /api/tree, drawn by the same tree control.
// Node ids start with `kb` -- that is how the frontend recognizes "this is not a real note".

export const KB_ROOT = 'kb'
/** `app:` is the app's own special notes (settings / skills), following Trilium's "options are notes in a hidden subtree" --
 *  they open as tabs in the middle pane and are treated like other notes. */
export const isVirtualId = (id: string) => id === KB_ROOT || id.startsWith('kb:') || id.startsWith('app:')
export const isFactId = (id: string) => id.startsWith('kb:fact:')

/** Category levels: root + topic tree + entities + months + recent meetings. Facts are not included; they are fetched on expand. */
export const kbTree = () =>
  fetch('/api/kb/tree', { headers: headers() }).then(json<TreeRow[]>)

/** The level fetched only when a category node is expanded: the facts under it. */
export const kbTreeChildren = (node: string) =>
  fetch(`/api/kb/tree/children?node=${encodeURIComponent(node)}`, { headers: headers() })
    .then(json<TreeRow[]>)

// Page data shown when knowledge-base nodes are opened (docs/kb-experience-plan.md §3)
export type KbMonth = { month: string; facts: number }
export type KbDashboard = {

  stats: { facts: number; topics: number; entities: number; units: number; lines: number
           start_date: string; end_date: string; full_start?: string; full_end?: string }
  /** Health check: how many facts in the whole library are **unusable by shape** (too short / only speaker + a phrase /
   *  a question not a fact / filler speech · ASR noise). This directly explains "why recall sometimes gives me a pile of junk". */
  quality?: { facts: number; unusable: number; unusable_rate: number
              reasons: Record<string, number>; speaker_labels: number; speaker_label_rate: number }
  months: KbMonth[]
  top_topics: { code: string; facts: number; children: number }[]
  top_entities: { code: string; name: string; facts: number }[]
  recent_units: { id: string; date: string; title: string; facts: number }[]
  kinds: { kind: string; facts: number }[]
  speakers: { who: string; facts: number }[]
  conflicts_open?: number
}
export type KbFactsPage = { facts_total: number; facts: FactDetail[]; limit: number; offset: number }
export type KbTopicPage = KbFactsPage & {
  code: string; aliases: string[]; parents: string[]; status: string; months: KbMonth[]
  children: { code: string; facts: number }[]
  entities: { code: string; name: string; facts: number }[]
  kinds: { kind: string; facts: number }[]
}
export type KbEntityPage = KbFactsPage & {
  code: string; name: string; type: string; aliases: string[]; months: KbMonth[]
  /** Other spellings of the same entity (rule-based grouping: case / separators / aliases; kb/entities.py) */
  variants?: string[]
  relations: { rel: string; target: string; target_name: string }[]
  topics: { code: string; facts: number }[]
  /** "How these things changed": fact threads strung together by object class (with dates, >= 2 items) */
  chains: { obj: string; facts: FactDetail[]; total: number }[]
}
export type KbTimelineMonth = { month: string; facts: number; units: number; days: { date: string; facts: number; units: number }[] }
export type KbUnitPage = KbFactsPage & {
  id: string; date: string; title: string; speakers: string[]
  /** The segments of the same material (meaningful only for multi-segment materials): segment navigation */
  parts?: { id: string; k: number }[]; part_index?: number; part_total?: number
  /** Only for segments from which not a single fact was extracted: the original words */
  lines?: { who: string; text: string }[]
  topics: { code: string; facts: number }[]
  entities: { code: string; name: string; facts: number }[]
}
export const kbDashboard = () => fetch('/api/kb/dashboard', { headers: headers() }).then(json<KbDashboard>)
export const kbTopic = (code: string, limit = 50, offset = 0) =>
  fetch(`/api/kb/topic/${encodeURIComponent(code)}?limit=${limit}&offset=${offset}`, { headers: headers() }).then(json<KbTopicPage>)
export const kbEntity = (code: string, limit = 50, offset = 0) =>
  fetch(`/api/kb/entity/${encodeURIComponent(code)}?limit=${limit}&offset=${offset}`, { headers: headers() }).then(json<KbEntityPage>)
export const kbTimeline = () => fetch('/api/kb/timeline', { headers: headers() }).then(json<KbTimelineMonth[]>)
export const kbDay = (date: string) => fetch(`/api/kb/timeline/${date}`, { headers: headers() }).then(json<FactDetail[]>)
export const kbUnit = (id: string, limit = 50, offset = 0) =>
  fetch(`/api/kb/unit/${encodeURIComponent(id)}?limit=${limit}&offset=${offset}`, { headers: headers() }).then(json<KbUnitPage>)

/** Model usage (only calls through this repo's util/llm; KITE extraction is estimated by character count within import jobs) */
export type UsageBucket = { calls: number; prompt_tokens: number; completion_tokens: number; ms: number }
export type UsageSummary = { today: UsageBucket; week: UsageBucket; month: UsageBucket; all: UsageBucket; by_feature: { feature: string; calls: number; tokens: number }[]; models: string[] }
export const usageSummary = () => fetch('/api/settings/usage', { headers: headers() }).then(json<UsageSummary>)


export const todayNote = (day = '') =>
  fetch('/api/notes/today' + (day ? `?day=${encodeURIComponent(day)}` : ''), { method: 'POST', headers: headers() }).then(json<Note>)

/** Recently deleted (recoverable within 30 days) */
export type TrashItem = { note_id: string; title: string; chars: number; deleted_at: string }
export const listTrash = () => fetch('/api/notes/trash', { headers: headers() }).then(json<TrashItem[]>)
export const restoreTrash = (id: string) => fetch(`/api/notes/trash/${id}/restore`, { method: 'POST', headers: headers() }).then(json<Note>)
export const purgeTrash = (id: string) => fetch(`/api/notes/trash/${id}`, { method: 'DELETE', headers: headers() }).then(json<{ ok: boolean }>)

/** Notes citing a given fact. Used by the right pane's "Backlinks". */
export type CitingNote = { id: string; title: string; updated_at: string; preview?: string; icon?: string }

/** Revisions (Trilium's note revisions). The list carries no body; a revision is fetched when opened. */

export type NoteRevision = { id: string; note_id: string; title: string; reason: string; created_at: string; chars: number; run_id: string; round_no: number }
export const listRevisions = (noteId: string) =>
  fetch(`/api/notes/${noteId}/revisions`, { headers: headers() }).then(json<NoteRevision[]>)
export const snapshotNote = (noteId: string) =>
  fetch(`/api/notes/${noteId}/revisions`, { method: 'POST', headers: headers() }).then(json<NoteRevision>)
export const getRevision = (noteId: string, revId: string) =>
  fetch(`/api/notes/${noteId}/revisions/${revId}`, { headers: headers() }).then(json<NoteRevision & { content: string }>)
export const restoreRevision = (noteId: string, revId: string) =>
  fetch(`/api/notes/${noteId}/revisions/${revId}/restore`, { method: 'POST', headers: headers() }).then(json<Note>)


export type ChangeLayersSave = {
  saved: number
  evicted: { label: string; at: string; why: string }[]
  rejected: { label: string; at: string; why: string }[]
}
export const listChangeLayers = (noteId: string) =>
  fetch(`/api/notes/${noteId}/change-layers`, { headers: headers() })
    .then(json<{ layers: SavedLayer[] }>).then((r) => r.layers ?? [])
export const saveChangeLayers = (noteId: string, layers: SavedLayer[], keepalive = false) =>
  fetch(`/api/notes/${noteId}/change-layers`, {
    method: 'PUT', headers: { ...headers(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ layers }),
    // The request sent at the moment the window closes: without keepalive the browser kills it as soon as the page unloads,
    // and the "save once before closing the app" path would effectively not exist.
    keepalive,
  }).then(json<ChangeLayersSave>)

export const burnChangeLayers = (noteId: string, keepalive = false) =>
  fetch(`/api/notes/${noteId}/change-layers`, { method: 'DELETE', headers: headers(), keepalive })
    .then(json<{ dropped: number }>)

export type WritingFeedback = {
  accepted: number
  reverted: number
  decided: number
  latest: { layer_id: string; label: string; accepted: number; reverted: number; decided_at: string }
  items: { layer_id: string; hunk_key: number; run_id: string; source: string; label: string;
    decision: 'accepted' | 'reverted'; del_text: string; ins_text: string; decided_at: string }[]
  run_retention?: { run_id: string; generated_chars: number; kept_chars: number;
    kept_percent: number; changed_section: string; edited_at: string } | null
}
export const getWritingFeedback = (noteId: string) =>
  fetch(`/api/notes/${noteId}/writing-feedback`, { headers: headers() }).then(json<WritingFeedback>)


export const listNoteRounds = (noteId: string) =>
  fetch(`/api/notes/${noteId}/rounds`, { headers: headers() }).then(json<NoteRoundsPayload>)

/** Links between notes: what this note links out to + what links in (Trilium's note links / referenced by). */
export type NoteGraph = { facts: number; topics: TopicNode[]; entities: EntityNode[]; links: TopicEntityLink[] }
/** What surrounds this note: which topics / entities the cited + contributed facts hang on (the local graph in the ribbon's "Citations") */
export const noteGraph = (noteId: string) =>
  fetch(`/api/notes/${noteId}/graph`, { headers: headers() }).then(json<NoteGraph>)

export type NoteLinks = { outgoing: CitingNote[]; backlinks: CitingNote[]; /** linked note ids that no longer exist */ dangling?: string[] }
export const noteLinks = (noteId: string) =>
  fetch(`/api/notes/${noteId}/links`, { headers: headers() }).then(json<NoteLinks>)

/** **Which notes cite this fact.** The reverse lookup -- key to the whole "notes x knowledge base" fusion.
 *  It answers "is this fact still alive, and whom would changing it affect". Modeled on Trilium's Backlinks. */
export const notesCiting = (factId: string) =>
  fetch(`/api/memory/facts/${encodeURIComponent(factId)}/citing`,
        { headers: headers() }).then(json<CitingNote[]>)


export type TraceOut = { answer: string; facts: Fact[]; recalled?: number | null; took_ms: number }

export const traceMemory = (passage: string, limit = 10, signal?: AbortSignal) =>
  fetch('/api/memory/trace', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ passage, limit }),
    signal,
  }).then(json<TraceOut>)

export type MemoryStats = {
  facts: number; topics: number; entities: number; units: number; lines: number
  speakers: string[]; start_date: string | null; end_date: string | null; codebook: string
}

export type Digest = {
  summary: string; fact_count: number; date_from: string; date_to: string; took_ms: number
}

export const digest = (days = 7) =>
  fetch('/api/digest', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ days, scope: memoryScope() }),
  }).then(json<Digest>)

export const memoryStats = () =>
  fetch('/api/memory/stats', { headers: headers() }).then(json<MemoryStats>)

// ---------------------------------------------------------------- knowledge-base visualization

export type TopicNode = {
  code: string; parents: string[]; status: string; aliases: string[]; fact_count: number
}
export type EntityNode = {
  code: string; name: string; type: string; aliases: string[]
  relations: [string, string][]; fact_count: number
}
export type TopicEntityLink = { topic: string; entity: string; weight: number }
export type FactDetail = {
  id: string; text: string; when: string; kind: string; who: string; conf: string
  topics: string[]; entities: string[]; unit: string
  /** Entity display names, one to one with entities (given by page APIs; recall APIs do not have them) */
  entity_names?: string[]
  /** Which note it was ingested from (knowledge-base pages link back to notes); manually added ones have manual=true */
  note_id?: string
  manual?: boolean
  /** What superseded it (after "new replaces old" the old one carries this); merged = merged in by "merge into one" */
  superseded_by?: string
  merged?: boolean
}

// ---------------------------------------------------------- memory relations
//
// How a passage of body relates to the knowledge base (docs/agent-native-editor.md §3.3.1): conflict / continuation / confirmation /
// no grounding. Candidates are judged by code; for conflicts the model confirms one sentence.
export type MemoryRelationKind = 'conflict' | 'continuation' | 'corroborated' | 'unsupported' | 'accumulation' | 'merge'
export type MemoryRelation = {
  relation: MemoryRelationKind
  say: string
  unit: string
  values: string[]
  fact_ids: string[]
  facts: Fact[]

  why?: string
}
export const memoryRelations = (passage: string, confirm = true) =>
  fetch('/api/memory/relations', {
    method: 'POST', headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ passage, confirm, scope: memoryScope() }),
  }).then(json<{ relations: MemoryRelation[]; took_ms: number }>)
/** Margin dots: the most important relation for each paragraph of a batch (zero LLM); null for none */
export const memoryRelationsBatch = (passages: string[]) =>
  fetch('/api/memory/relations/batch', {
    method: 'POST', headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ passages, scope: memoryScope() }),
  }).then(json<{ marks: ({ relation: MemoryRelation['relation']; say: string; fact_ids: string[]; kinds?: number; facts?: Fact[]; why?: string } | null)[]; took_ms: number }>)
export const supersedeFact = (oldId: string, newId: string) =>
  fetch(`/api/kb/fact/${encodeURIComponent(oldId)}`, {
    method: 'PATCH', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify({ superseded_by: newId }),
  }).then(json<{ id: string; superseded_by: string }>)
/** "Merge into one": mark drop as superseded by keep (merged); keep's text can be edited in passing; the merge result is remembered */
export const mergeFacts = (keep: string, drop: string, text = '') =>
  fetch('/api/kb/fact/merge', {
    method: 'POST', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify({ keep, drop, text }),
  }).then(json<{ id: string; text: string; merged_from: string }>)
/** Conflict inbox: "new fact vs old fact" detected during ingest */
export type KbConflictFact = { id: string; text: string; when: string; note_id: string; unit: string }
export type KbConflict = { id: number; new_fact_id: string; old_fact_id: string; unit: string; say: string; source: string; status: string; resolution: string; created_at: string; new: KbConflictFact; old: KbConflictFact }
export const kbConflicts = () => fetch('/api/kb/conflicts', { headers: headers() }).then(json<{ conflicts: KbConflict[]; open: number }>)
export const resolveConflict = (id: number, action: 'new_wins' | 'old_wins' | 'keep_both') =>
  fetch(`/api/kb/conflicts/${id}/resolve`, {
    method: 'POST', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify({ action }),
  }).then(json<KbConflict>)
export type FactsPage = { facts: FactDetail[]; total: number; limit: number; offset: number }
export type SourceLine = { id: string; unit: string; date: string; who: string; text: string }

export const memoryTopics = () =>
  fetch('/api/memory/topics', { headers: headers() }).then(json<TopicNode[]>)

export const createTopic = (code: string, parent = '', aliases: string[] = []) =>
  fetch('/api/memory/topics', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ code, parent, aliases }),
  }).then(json<TopicNode>)

export const memoryEntities = () =>
  fetch('/api/memory/entities', { headers: headers() }).then(json<EntityNode[]>)

export const topicEntityLinks = () =>
  fetch('/api/memory/topic-entity-links', { headers: headers() }).then(json<TopicEntityLink[]>)

/** Topic clusters: a coarse view layered above fine topics.
 *
 *  Fine topics make Q&A accurate, and are exactly what makes writing repetitive -- one section's materials spread over six sibling topics.
 *  Measured on this library: 196 topics, median 10 facts, 51% <= 10; after clustering the median is 18.
 *  A cluster with `merged=false` is a topic big enough on its own, never merged. */
export type TopicCluster = {
  key: string; label: string; topics: string[]; facts: number; merged: boolean
}

export const listClusters = () =>
  fetch('/api/kb/clusters', { headers: headers() })
    .then(json<{ clusters: TopicCluster[]; topics: number }>)

export type FactsFilter = {
  kind?: string; who?: string; topic?: string; entity?: string; conf_min?: string
  limit?: number; offset?: number
}

export const memoryFacts = (filter: FactsFilter = {}) => {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(filter)) {
    if (v !== undefined && v !== '') q.set(k, String(v))
  }
  return fetch(`/api/memory/facts?${q}`, { headers: headers() }).then(json<FactsPage>)
}

export const factSources = (factId: string) =>
  fetch(`/api/memory/facts/${factId}/sources`, { headers: headers() }).then(json<SourceLine[]>)

// ---------------------------------------------------------------- ingest

/** `source_id`: which note is being ingested. **Required when ingesting a note** -- after ingest finishes the backend uses it
 *  to mark that note "ingested", which is what makes the ⇡ visible in the tree; KITE also uses it to build a stable
 *  session_id, so ingesting the same note again does not duplicate it. */
export const ingestText = (content: string, title = '', source = 'doc', source_id = '', replace = false) =>
  fetch('/api/ingest/text', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ content, title, source, source_id, replace }),
  }).then(json<{ job_id: string; status: string; detail: string }>)

// ---------------------------------------------------------- note <-> knowledge base link layer
//
// Which facts this note contributed (the ingest session is named note-<id>-<chunk>), whether it changed without syncing (stale),
// adding/deleting/editing facts, sync (the server reads the latest body, deletes the old session and re-extracts; manually added ones stay).

export type NoteKbFact = {
  id: string; text: string; when: string; kind: string; who: string; conf: string
  topics: string[]; entities: string[]; unit: string
  /** Added manually by the user (in note-<id>-manual; not deleted on sync) */
  manual: boolean
}
export type NoteKb = {
  note_id: string; ingested_at: string; updated_at: string
  /** The body changed after ingest: the knowledge base still has the old version */
  stale: boolean
  facts: NoteKbFact[]
  manual_session: string
}
export const noteKb = (noteId: string) =>
  fetch(`/api/notes/${noteId}/kb`, { headers: headers() }).then(json<NoteKb>)
export const syncNoteToKb = (noteId: string) =>
  fetch(`/api/ingest/note/${noteId}/sync`, { method: 'POST', headers: headers() })
    .then(json<{ job_id: string; status: string }>)
export const updateFact = (factId: string, text: string) =>
  fetch(`/api/kb/fact/${encodeURIComponent(factId)}`, {
    method: 'PATCH', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify({ text }),
  }).then(json<NoteKbFact>)
export const deleteFact = (factId: string) =>
  fetch(`/api/kb/fact/${encodeURIComponent(factId)}`, { method: 'DELETE', headers: headers() })
    .then(json<{ ok: boolean; removed: number }>)
export const addFact = (noteId: string, text: string, when = '') =>
  fetch('/api/kb/fact', {
    method: 'POST', headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ note_id: noteId, text, when }),
  }).then(json<NoteKbFact>)

export const ingestAudio = (file: Blob, filename = 'recording.webm', title = '', signal?: AbortSignal) => {
  const fd = new FormData()
  fd.append('file', file, filename)
  fd.append('title', title)
  fd.append('language', 'auto')
  return fetch('/api/ingest/audio', { method: 'POST', headers: headers(), body: fd, signal })
    .then(json<{ job_id: string; status: string; detail: string }>)
}

export const transcribeOnly = (file: Blob, filename = 'recording.webm', signal?: AbortSignal) => {
  const fd = new FormData()
  fd.append('file', file, filename)
  fd.append('language', 'auto')
  return fetch('/api/ingest/transcribe', { method: 'POST', headers: headers(), body: fd, signal })
    .then(json<{ text: string }>)
}

export type IngestItem = {
  id: string
  idx: number
  filename: string
  kind: string

  note_id?: string
  status: 'queued' | 'extracting' | 'transcribing' | 'chunking' | 'remembering'
    | 'done' | 'failed' | 'cancelled'
  facts: number
  detail: string
  chunks_total?: number
  chunks_done?: number
}

export type JobOut = {
  job_id: string
  // cancelling: cancellation received but the background has not fully stopped (maybe stuck in an LLM call or KITE's write lock);
  // during this time it must truthfully show "Stopping...", not still say "Processing" -- otherwise it is as if nothing was clicked.
  // interrupted: a service restart interrupted it, but the cleaned content was written to disk and can "Resume".
  status: 'queued' | 'running' | 'cancelling' | 'done' | 'error' | 'cancelled' | 'interrupted'
  facts: number
  detail: string
  items: IngestItem[]
  /** Progress by chunk (a 40-chunk meeting record and a 2-chunk jotting weigh differently), estimated time left,
   *  time elapsed, estimated tokens spent, which file is being worked on, and whether it can resume */
  chunks_total?: number
  chunks_done?: number
  eta_s?: number
  elapsed_s?: number
  tokens_est?: number
  current?: string
  resumable?: boolean
  /** Estimate before starting (given by import APIs): total chunks, roughly how long, how many tokens */
  estimate?: { chunks: number; seconds: number; tokens: number }
}

export const jobStatus = (jobId: string) =>
  fetch(`/api/ingest/jobs/${jobId}`, { headers: headers() }).then(json<JobOut>)

export const listJobs = (limit = 20) =>
  fetch(`/api/ingest/jobs?limit=${limit}`, { headers: headers() }).then(json<JobOut[]>)
/** Resume from the breakpoint: only run items not yet in a final state (imports interrupted by a service restart) */
export const resumeImportJob = (jobId: string) =>
  fetch(`/api/import/jobs/${jobId}/resume`, { method: 'POST', headers: headers() }).then(json<JobOut>)
export const cancelJob = (jobId: string) =>
  fetch(`/api/ingest/jobs/${jobId}/cancel`, { method: 'POST', headers: headers() }).then(json)

/** Batch ingest: PDF / DOCX / TXT / MD / audio mixed together, each file processed independently. */
export const ingestBatch = (files: File[]) => {
  const fd = new FormData()
  for (const f of files) fd.append('files', f, f.name)
  fd.append('language', 'auto')
  return fetch('/api/ingest/batch', { method: 'POST', headers: headers(), body: fd })
    .then(json<JobOut>)
}

/** Subscribe to a batch job's progress stream. onProgress receives a full snapshot on every state change; when the job reaches
 * a final state (done/error/cancelled) onEnd is called once and the connection closes automatically. */
export function watchJob(
  jobId: string,
  onProgress: (j: JobOut) => void,
  onEnd: () => void,
  signal?: AbortSignal,
) {
  ;(async () => {
    const res = await fetch(`/api/ingest/jobs/${jobId}/events`, { headers: headers(), signal })
    if (!res.ok || !res.body) throw new Error(`events failed: ${res.status}`)
    for await (const { event, payload } of sseFrames(res)) {
      if (event === 'progress') onProgress(payload as JobOut)
      else if (event === 'end') {
        window.dispatchEvent(new CustomEvent('notes-changed'))
        onEnd()
      }
    }
  })().catch((err) => {
    if (signal?.aborted) return
    throw err
  })
}

export const health = () => fetch('/api/health').then(json<any>)

/** Report frontend errors to the backend log (the packaged build has no DevTools; on a white screen this is the only clue). */
export const clientLog = (level: 'error' | 'warn' | 'info', message: string, stack = '', where = '') =>
  fetch('/api/client-log', {
    method: 'POST', headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ level, message, stack, where }),
  }).catch(() => {})

// ---------------------------------------------------------------- skill system
//
// The writing prompt system turned into "skills": each skill is an extra instruction stacked after the base system prompt
// of some generation call site; skills can be toggled and reordered. On a new user's first fetch
// the backend automatically seeds a few default skills rewritten from high-scoring Claude Skills.

export type SkillScope = { value: string; label: string }

/** A skill is a standard `SKILL.md` directory on disk, not a database row.
 *  `id` is the directory name (slug) -- the frontend has always addressed by id; the meaning changed, the usage did not.
 *  `source` distinguishes built-in / written by you / third-party installed; installed ones are off by default. */
export type Skill = {
  id: string; slug: string; name: string; description: string
  scopes: string[]; content: string; enabled: boolean
  idx: number; builtin: boolean
  source: 'builtin' | 'user' | 'imported'; sandbox: 'none' | 'compute' | 'files'
}

export type SkillIn = {
  name: string; slug?: string; description: string
  scopes: string[]; content: string; enabled: boolean
}

export const listSkillScopes = () =>
  fetch('/api/skills/scopes', { headers: headers() }).then(json<SkillScope[]>)

export const listSkills = () =>
  fetch('/api/skills', { headers: headers() }).then(json<Skill[]>)

export const createSkill = (body: SkillIn) =>
  fetch('/api/skills', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  }).then(json<Skill>)

export const updateSkill = (id: string, body: SkillIn) =>
  fetch(`/api/skills/${id}`, {
    method: 'PUT',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  }).then(json<Skill>)

export const toggleSkill = (id: string) =>
  fetch(`/api/skills/${id}/toggle`, { method: 'POST', headers: headers() }).then(json<Skill>)

export const deleteSkill = (id: string) =>
  fetch(`/api/skills/${id}`, { method: 'DELETE', headers: headers() }).then(json)

export const reorderSkills = (orderedIds: string[]) =>
  fetch('/api/skills/reorder', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ ordered_ids: orderedIds }),
  }).then(json)

/** Returns a draft (SkillIn shape), not persisted directly -- the caller shows it in the edit form,
 * and only after the user has reviewed, edited and picked scopes does calling createSkill really save it. */
export const generateSkill = (goal: string, scopeHint = '') =>
  fetch('/api/skills/generate', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ goal, scope_hint: scopeHint }),
  }).then(json<SkillIn>)

// ---------------------------------------------------------------- single-note harness (Smart Continue)
//
// The same "harness" spirit as endless writing (folder level), scoped to one note: automatic
// revisions (without waiting for a manual accept) + automatic continuation alternate, until the content is complete
// relative to the structural beats; not a round cap.

export type NoteHarnessRevision = {
  op: string; anchor: string; anchor_end?: string
  text: string; reason: string; sources: string[]
}

export type NoteHarnessDimensionScore = { level: number; note: string }

export type NoteHarnessToolCall = { tool: string; args: Record<string, unknown>; result: string }

export type NoteHarnessHandlers = {
  /** `notes` is the outline's deterministic check result (backend `harness/checks/skeleton.py`, plan 4.3).
   * **Judged but not blocking the run** -- the same tier as `slides`; the result is shown alongside the product,
   * and whether to regenerate is the user's call. */
  onSkeleton?: (spine: string, beats: string[], notes?: string[]) => void

  onRoundStart?: (d: { round: number; max_rounds: number; revisions_applied: number; skipped_continue?: boolean; facts?: number; sources?: string[]; kb_empty?: boolean; steer?: string; steer_dim?: string; steer_material?: boolean; steer_in_plan?: boolean | null; checks_total?: number; depth_dropped?: number; depth_dropped_all?: boolean; facts_irrelevant?: number; irrelevant_dropped?: boolean; irrelevant_sample?: string[]; cite_located?: number; cite_marked?: number; cite_matched?: number }) => void
  onRevision?: (r: NoteHarnessRevision) => void
  onDelta?: (text: string) => void
  /** This round's continuation stream ended (TEXT_MESSAGE_END): the client does the same normalization the server does at wrap-up (fixBoldPunct) */
  onTextEnd?: () => void
  /** Targeted continue: this round's deltas go at the end of section `section` (the backend's `pos` is only a fallback;
   *  the frontend recomputes the position from its own body); arrives before the first delta; without it, append to the end. */
  onInsertAt?: (d: { section: string; pos: number }) => void
  onRoundEnd?: (round: number, content?: string) => void

  onEvaluate?: (d: { scores: Record<string, NoteHarnessDimensionScore>; status: string; weakest: string | null; judge_hallucinated?: { dimension: string; quotes: string[]; note: string }[] }) => void
  /** When `reason` is awaiting_review it carries `runId`: this round stopped to wait for you to handle each change;
   *  once handled, send the remaining body back with resumeHarness(runId, content) to continue. */
  onDone?: (reason: string, blockedReason?: string, runId?: string, content?: string) => void
  onError?: (detail: string) => void
  /** The current phase (retrieval/edit/write/evaluate) and its human label */
  onPhase?: (d: { round: number; phase: string; label: string }) => void
  /** Live output within a phase. kind=thinking is the model's thinking process, output is what it writes. */
  onPhaseDelta?: (d: { round: number; phase: string; kind: string; text: string }) => void
  /** Which tools the agent decided to call by itself */
  onToolCalls?: (d: { round: number; iters: number; truncated: boolean; calls: NoteHarnessToolCall[] }) => void
  /** The policy controller adjusted how the next round runs based on the previous round's feedback */
  onPolicy?: (d: { round: number; policy: Partial<{ tool_iters: number; continue_temperature: number; max_revisions: number; require_verification: boolean }>; reasons: string[] }) => void
  /** A revision was dropped by the guards. **Not an error** -- synonymous rewrites, ambiguous anchors, cuts producing broken characters,
   * touching the user's own headings: all four are the guards working normally, and one round can drop several.
   * Rendering them with onError would turn the UI into a sheet of red. */
  onDropped?: (detail: string) => void
  /** Whole sentences the server deleted from the body within the round (meta-talk / citation sentences without grounding): the client must delete the same sentence from its local body, or by round end the two differ by a whole sentence */
  onScrub?: (v: { sentence: string; why: string }) => void
  /** The server stripped some passage / line the stream had given us (duplicate paragraphs, headings the model wrote itself): delete the same passage locally */
  onDedup?: (v: { paragraph: string }) => void
  /** A code criterion judged this round failed on the spot. On a hit the model scoring is skipped, and the score is the one this criterion gives.
   *
   * `check` is **the criterion's own name** (`no_placeholder` / `citations_exist`...).
   * `dimension` alone cannot answer "which criterion hit": five criteria all land on
   * the `factual_grounding` dimension, and a user seeing "Grounding 0 points" cannot tell who judged it.
   * `ran` is which check this round reached; the denominator `checks_total` is in round_summary.
   * **Several may arrive in one round** (the released stuck ones + the final short-circuit), so the caller must accumulate
   * them into a list, not keep only the last one. */
  /** The one with `stopped` true is not "hit this round" but a stop notice: the same criterion fired for `stuck_rounds` rounds,
   *  the backend stopped and shipped the best round (reason=check_stuck). The stop sentence uses it to say "which one, how many rounds". */
  onCheckHit?: (d: { round?: number; check?: string; ran?: number; dimension: string; note: string; stuck_rounds?: number; stopped?: boolean; advisory?: boolean; judge_floor?: number }) => void
  /** Some middleware threw. The loop keeps running (that is the isolation benefit of capability packaging),
   * but **it must not be silent** -- this round lacked that capability, and the user must know. */
  onWarning?: (d: { middleware: string; hook: string; error: string }) => void
  /** Which skills this run carries (sent at the start of the first round): those brought in automatically by scope, and those left for the model to load on demand */
  onSkills?: (d: { round: number; scope: string; injected: string[]; menu: string[] }) => void
  /** The skeleton was replanned. The goal was changed, and the user must be able to see what it changed to -- after this the backend
   * resends a skeleton event so the skeleton panel updates along. */
  onReplan?: (d: { round: number; why: string; changes: string[]; beats: string[] }) => void
  /** This run hit the single-run cost cap and stopped at this round (backend plan 12.3). **Not a silent truncation**:
   * after it a RUN_FINISHED with reason='cost_cap' still arrives, shipping the best round. */
  onCost?: (d: { round: number; tokens: number; cap: number; calls: number; detail: string }) => void
  /** This run finished **worse than the previous run** (backend plan 9.3). Report only, no rollback -- the previous body is in
   * "Revisions", and whether to go back is the user's call. */
  onCrossRun?: (d: { met: number; last_met: number; mean: number; last_mean: number; dimensions: string[]; detail: string }) => void
}

export async function runNoteHarness(
  noteId: string,
  content: string,
  spine: string,
  beats: string[],
  handlers: NoteHarnessHandlers,
  signal?: AbortSignal,
  /** write = revise while continuing; polish = **revise only, no writing**, dedicated to smoothing existing content.
   * In polish mode the backend also removes the beat_coverage / material_use dimensions -- those two measure
   * "how much was written", and polish is explicitly forbidden to write, so scoring with them would never let the loop converge. */
  mode: 'write' | 'polish' = 'write',
  /** Stop after each round and wait for you to accept/reject each change. When off, it is the old behavior: run through in one go
   *  and handle afterwards -- which means your handling in the editor would be overwritten by the next round. */
  reviewEachRound = false,

  intent = '',
) {
  const res = await fetch('/api/note-harness/run', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    // The round count is not passed: the mode decides it (`modes.NOTE.max_rounds` = 8). This used to hard-code 20, overriding

    body: JSON.stringify({
      note_id: noteId, content, spine, beats, mode, scope: memoryScope(),
      review_each_round: reviewEachRound, intent,
    }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`note-harness run failed: ${res.status}`)
  return consumeHarnessStream(res, handlers)
}

/** Continue after handling. `content` is the editor's body after accepting/rejecting each change -- the user's decisions
 *  happen in the editor; having the backend merge again from a list of hunk ids would be the same merge implemented twice. */
export async function resumeHarness(
  runId: string,
  content: string,
  handlers: NoteHarnessHandlers,
  signal?: AbortSignal,
) {
  const res = await fetch(`/api/harness/${runId}/resume`, {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ content }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`resume failed: ${res.status}`)
  return consumeHarnessStream(res, handlers)
}

/** The user decided after reading not to write further: save and wrap up, discard the snapshot. */
export const stopHarness = (runId: string, content: string) =>
  fetch(`/api/harness/${runId}/resume`, {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ content, stop: true }),
  }).then(json<{ stopped: string; rounds: number }>)

export type PausedRun = {
  id: string; note_id: string; mode: string; round: number; created_at: string
}

/** Runs paused halfway waiting for my handling. Once the SSE stream drops, this is the only place to find them again. */
export const listPausedRuns = () =>
  fetch('/api/harness/paused', { headers: headers() }).then(json<PausedRun[]>)

/** Exported only for testing. It is all of the parsing logic of the harness's frontend half --
 * events silently dropped, frames broken at chunk boundaries all happen here, and the symptom is
 * "something is missing from the panel", which nobody reports as a bug. */
export async function consumeHarnessStream(res: Response, handlers: NoteHarnessHandlers) {
  // AG-UI standard events. Domain-specific things go through CUSTOM's name field, so this is
  // "nine standard branches + one CUSTOM branch"; adding a harness needs no change here.
  //
  // The backend once used a different set of custom event names, with a translation layer in between -- a transition layer while the three routers
  // migrated one by one. Once all three switched, the frontend renamed and the backend deleted the function, one commit's
  // work.


  // round_summary.
  let round = 0
  for await (const { event, payload } of sseFrames(res)) {
    if (event === 'TEXT_MESSAGE_CONTENT') handlers.onDelta?.(payload.delta)
    else if (event === 'TEXT_MESSAGE_END') handlers.onTextEnd?.()
    else if (event === 'STEP_STARTED') { round = payload.step; handlers.onPhase?.({ round: payload.step, phase: '', label: payload.label }) }
    else if (event === 'STEP_FINISHED') handlers.onRoundEnd?.(payload.step, payload.content)
    else if (event === 'ACTIVITY_SNAPSHOT') handlers.onPhase?.({ round, phase: '', label: payload.content })
    else if (event === 'TOOL_CALL_RESULT') {
      handlers.onToolCalls?.({ round, iters: 1, truncated: false,
        calls: [{ tool: payload.toolName, args: payload.args, result: payload.content }] })
    } else if (event === 'RUN_FINISHED') {
      handlers.onDone?.(payload.reason, payload.blocked_reason, payload.run_id, payload.content)
    // **RUN_ERROR must not throw**: every scenario where the backend sends it is a recoverable degradation (some tool found
    // nothing, some call timed out), and the stream continues. Throwing would cut the whole SSE connection, and the user
    // would see "it vanished halfway". Hand it to onError for display, and let the harness keep running.
    } else if (event === 'RUN_ERROR') handlers.onError?.(payload.message)
    else if (event === 'CUSTOM') {
      const v = payload.value ?? {}
      if (payload.name === 'skeleton') handlers.onSkeleton?.(v.spine, v.beats, v.notes ?? [])
      else if (payload.name === 'round_summary') { if (typeof v.round === 'number') round = v.round; handlers.onRoundStart?.(v) }
      else if (payload.name === 'revision') handlers.onRevision?.(v)
      else if (payload.name === 'evaluate') handlers.onEvaluate?.(v)
      else if (payload.name === 'phase_delta') handlers.onPhaseDelta?.(v)
      else if (payload.name === 'policy') handlers.onPolicy?.(v)
      else if (payload.name === 'dropped') handlers.onDropped?.(v.detail)
      else if (payload.name === 'scrub') handlers.onScrub?.(v)
      else if (payload.name === 'dedup') handlers.onDedup?.(v)
      else if (payload.name === 'check_hit') handlers.onCheckHit?.(v)
      else if (payload.name === 'warning') handlers.onWarning?.(v)
      else if (payload.name === 'skills') handlers.onSkills?.(v)
      else if (payload.name === 'replan') handlers.onReplan?.(v)
      else if (payload.name === 'insert_at') handlers.onInsertAt?.(v)
      else if (payload.name === 'cost') handlers.onCost?.(v)
      else if (payload.name === 'cross_run') handlers.onCrossRun?.(v)
    }
  }
}

// ---------------------------------------------------------------- LLM provider settings
//
// Global, not per user: which provider (OpenAI / Anthropic / ... / Ollama / custom) is selected. After a
// switch the writing trio / continue / knowledge-base extraction / entity merging all use the new provider,
// no backend restart. The preset registry is the backend's `util/providers.py`; each provider keeps its own
// key / model / address, so switching never loses one.

/** One entry of the settings dropdown: the preset plus what is saved for it. **Never the key itself**, only
 *  "set" and the last four characters. */
export type ProviderPreset = {
  id: string
  label: string
  /** factory default address (the `local` entry: .env / factory default); shown as placeholder */
  base_url: string
  /** suggested model names (<datalist>), not an exhaustive list */
  models: string[]
  needs_key: boolean
  /** request-body shape: openai | compatible | local (the backend picks the token-limit field by it) */
  family: 'openai' | 'compatible' | 'local'
  group: 'hosted' | 'local' | 'custom'
  docs: string
  key_set: boolean
  key_preview: string
  /** saved model / address for this entry (empty = not set / default) */
  model: string
  base_url_saved: string
}

export type AsrProvider = 'whisper' | 'assemblyai' | 'speechmatics'

export type ProviderConfig = {
  /** the selected entry (preset id; old databases hold 'local' | 'gpt') */
  provider: string
  providers: ProviderPreset[]
  /** the entry actually in effect (a key-requiring entry without a key falls back to 'local') + its request-body shape */
  active_provider: string
  active_family: string
  gpt_model: string
  gpt_base_url: string
  gpt_api_key_set: boolean
  gpt_api_key_preview: string

  asr_base_url: string
  asr_default_url: string
  /** Active speech-to-text provider and the hosted providers' key-set flags / regions (keys are never returned). */
  asr_provider: AsrProvider
  assemblyai_api_key_set: boolean
  assemblyai_api_key_preview: string
  assemblyai_region: string
  speechmatics_api_key_set: boolean
  speechmatics_api_key_preview: string
  speechmatics_region: string

  vision_base_url: string
  vision_model: string
  vision_api_key_set: boolean
  vision_follows_llm: boolean
  vision_active_url: string
  vision_active_model: string

  local_base_url: string
  local_model: string
  local_api_key_set: boolean

  local_default_url: string
  local_default_model: string

  configured: boolean
  /** id of the configured entry ('gpt' / 'local' / 'openai' / ...) or 'env' / 'default' */
  configured_source: string

  active_url: string
  active_model: string

  auto_sync_notes: boolean
}

export const getProviderConfig = () =>
  fetch('/api/settings/provider', { headers: headers() }).then(json<ProviderConfig>)

export const setProviderConfig = (body: {
  /** preset id */
  provider: string
  /** the three fields **of the `provider` entry itself**: omitted = keep; api_key '' = clear; base_url '' = preset default */
  api_key?: string
  model?: string
  base_url?: string
  gpt_api_key?: string
  gpt_model?: string
  gpt_base_url?: string
  asr_base_url?: string
  /** Omitted = keep. Blank keys are never sent (that would clear them). */
  asr_provider?: AsrProvider
  assemblyai_api_key?: string
  assemblyai_region?: string
  speechmatics_api_key?: string
  speechmatics_region?: string
  auto_sync_notes?: boolean
  local_base_url?: string
  local_model?: string
  local_api_key?: string
  vision_base_url?: string
  vision_model?: string
  vision_api_key?: string
}) =>
  fetch('/api/settings/provider', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  }).then(json<ProviderConfig>)


export type ProviderTest = {
  ok: boolean
  message: string
  models: string[]
  model_found: boolean | null
  elapsed_ms: number
}

export const testProvider = (body: {
  kind: 'llm' | 'vision' | 'asr'
  base_url: string
  model?: string
  api_key?: string
  /** with an empty key field, use the key saved for this entry (preset id or 'vision') */
  saved_key_of?: string

  provider?: string
  /** kind 'asr' only: which speech provider to test (default whisper) and its region. */
  asr_provider?: AsrProvider
  region?: string
}) =>
  fetch('/api/settings/provider/test', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  }).then(json<ProviderTest>)


// ---------------------------------------------------------------- import from other note apps
//
// Separate from ingestBatch because that path cannot get original dates and does not know each app's private syntax --
// a whole vault going through it would be flattened onto one day, with wiki links and dataview blocks entering the knowledge base raw.
// See docs/import-from-other-note-apps.md.

/** When picking a whole vault the browser puts the relative path in webkitRelativePath, which must be sent explicitly as the file name;
 * the server uses it to rebuild the folder structure and generate stable ids (rerunning is an incremental sync). */
export const importFiles = (
  files: File[],
  source: 'obsidian' | 'evernote',
  to: 'both' | 'kb' | 'notes' = 'both',
) => {
  const fd = new FormData()
  for (const f of files) {
    fd.append('files', f, (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name)
  }
  fd.append('source', source)
  fd.append('to', to)
  return fetch('/api/import/files', { method: 'POST', headers: headers(), body: fd })
    .then(json<JobOut>)
}

export const importNotion = (token: string, to: 'both' | 'kb' | 'notes' = 'both') => {
  const fd = new FormData()
  fd.append('token', token)
  fd.append('to', to)
  return fetch('/api/import/notion', { method: 'POST', headers: headers(), body: fd })
    .then(json<JobOut>)
}

/** Feishu docs / wiki: the custom app's app_id / app_secret (not stored, filled every time), scope = wiki (knowledge base)
 *  or drive (cloud space). Documents must add the app as a collaborator. */
/** With `docs` filled, **only these documents are imported** (one link or token per line), skipping the "list" path.
 *  Feishu authorizes per document, while listing requires the app to be a **member** of the wiki space -- shared only as a single-doc collaborator,
 *  the document can be read but not listed (measured on a real account). */
export const importFeishu = (appId: string, appSecret: string, scope: 'wiki' | 'drive', to: 'both' | 'kb' | 'notes' = 'both', docs = '') => {
  const fd = new FormData()
  fd.append('app_id', appId)
  fd.append('app_secret', appSecret)
  fd.append('scope', scope)
  fd.append('to', to)
  if (docs.trim()) fd.append('docs', docs.trim())
  return fetch('/api/import/feishu', { method: 'POST', headers: headers(), body: fd })
    .then(json<JobOut>)
}

// ---- Export back (docs/import-sync-plan.md §2): this side is the truth; remote copies are overwritten by memoket_id ----

export type ExportBackOut = { created?: number; updated?: number; written?: number; skipped?: number; conflicts?: string[]; failed?: string[]; files?: string[]; missing?: string[]; untried?: number; url?: string; urls?: { note_id: string; title: string; url: string }[] }

export type NoteRemote = { platform: string; remote_id: string; remote_path: string; exported_at: string; remote_rev?: string }

export type MermaidBlocks = Record<string, string>
/** The response of `POST /api/export/renders`: how many were accepted, which keys were rejected as not PNG */
export type RendersOut = { stored: number; rejected: string[] }
export const exportObsidian = (vaultDir: string, noteIds: string[] = [], force = false) =>
  fetch('/api/export/obsidian', { method: 'POST', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify({ vault_dir: vaultDir, note_ids: noteIds, force }) })
    .then(json<ExportBackOut>)
export const exportNotion = (token: string, parentPageId: string, noteIds: string[] = [], force = false) =>
  fetch('/api/export/notion', { method: 'POST', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify({ token, parent_page_id: parentPageId, note_ids: noteIds, force }) })
    .then(json<ExportBackOut>)
export const exportFeishu = (appId: string, appSecret: string, folderToken: string, noteIds: string[] = [], force = false) =>
  fetch('/api/export/feishu', { method: 'POST', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify({ app_id: appId, app_secret: appSecret, folder_token: folderToken, note_ids: noteIds, force }) })
    .then(json<ExportBackOut>)
export const noteRemotes = (noteId: string) =>
  fetch(`/api/export/remotes/${noteId}`, { headers: headers() }).then(json<NoteRemote[]>)

export type ConnectionAvailability = { available: boolean; reason: string }
export const appleAvailable = (signal?: AbortSignal) =>
  fetch('/api/import/apple/available', { headers: headers(), signal })
    .then(json<ConnectionAvailability>)

export const importApple = (to: 'both' | 'kb' | 'notes' = 'both') => {
  const fd = new FormData()
  fd.append('to', to)
  return fetch('/api/import/apple', { method: 'POST', headers: headers(), body: fd })
    .then(json<JobOut>)
}

// ---------------------------------------------------------------- writing skeleton

/** The skeleton is stored with the note. It used to live only in frontend memory, cleared as soon as `open()` entered a note -- switching notes,
 * refreshing the page, even endless writing's "follow" auto-switching to the next section, and the skeleton was gone. */
export const saveSkeleton = (noteId: string, spine: string, beats: string[]) =>
  fetch(`/api/notes/${noteId}/skeleton`, {
    method: 'PUT',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ spine, beats }),
  }).then(json<Note>)

// ---------------------------------------------------------------- block generation invoked by `/`

/** The same loop as the writing harness: plan (call tools) -> generate -> score -> if below the bar, run another round with the diagnosis.
 * Numbers are computed by the data tool group, chart syntax assembled by the chart tool group -- the model only decides what to compute
 * and what to draw. custom is the context menu's "Custom prompt", scoped to the selected passage. */

export const BLOCK_MODES = ['prompt', 'chart', 'table', 'eda', 'analysis', 'custom'] as const
export type BlockMode = typeof BLOCK_MODES[number]

export async function composeBlock(
  body: { note_id: string; title: string; content: string; cursor: number;
          mode: BlockMode; prompt: string; selection?: string

          from_tray?: boolean },
  on: {
    onPhase?: (label: string) => void
    onTools?: (calls: NoteHarnessToolCall[]) => void
    onDelta?: (text: string) => void
    onEvaluate?: (status: string, scores: Record<string, NoteHarnessDimensionScore>) => void
    onError?: (detail: string) => void
    onSkills?: (d: { injected: string[]; menu: string[]; scope: string }) => void
  },
  signal?: AbortSignal,
): Promise<string> {
  const res = await fetch('/api/compose/block', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ ...body, scope: memoryScope() }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(await res.text().catch(() => res.statusText))
  let block = ''
  for await (const { event, payload } of sseFrames(res)) {
    const p = payload as Record<string, unknown>
    if (event === 'ACTIVITY_SNAPSHOT') on.onPhase?.(String(p.content ?? ''))
    else if (event === 'STEP_STARTED') on.onPhase?.(String(p.label ?? ''))
    else if (event === 'TOOL_CALL_RESULT') {
      on.onTools?.([{ tool: String(p.toolName ?? ''), args: p.args as Record<string, unknown>,
                      result: String(p.content ?? '') }] as NoteHarnessToolCall[])
    } else if (event === 'TEXT_MESSAGE_CONTENT') on.onDelta?.(String(p.delta ?? ''))
    else if (event === 'CUSTOM' && p.name === 'evaluate') {
      const v = (p.value ?? {}) as Record<string, unknown>
      on.onEvaluate?.(String(v.status ?? ''),
        v.scores as Record<string, NoteHarnessDimensionScore>)
    } else if (event === 'CUSTOM' && p.name === 'skills') {
      on.onSkills?.(p.value as { injected: string[]; menu: string[]; scope: string })
    } else if (event === 'RUN_ERROR') on.onError?.(String(p.message ?? ''))
    else if (event === 'RUN_FINISHED') {
      block = String(p.content ?? block)
      // The gate judged "cannot do it now" (no data near the cursor): not a word written, the reason is in blocked_reason
      if (p.reason === 'blocked' && p.blocked_reason) on.onError?.(String(p.blocked_reason))
    }
  }
  return block
}

/** Smart format: judge which lines should be headings and which should be lists -- semantic judgments rules cannot compute.
 *
 * **The model only outputs "which line becomes what structure", not a single character of the original text**; the original is moved
 * line by line by the backend (see app/restructure.py). So "formatting edited the content in passing" is structurally impossible,
 * not reliant on a prompt saying "do not change the content". */
export const restructureNote = (noteId: string, title: string, content: string, intent = '', signal?: AbortSignal) =>
  fetch('/api/compose/restructure', {
    method: 'POST',
    headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ note_id: noteId, title, content, intent }),
    signal,
  }).then(json<{ changed: boolean; content: string; ops: number
                 skipped: string[]; detail: string }>)

// ---------------------------------------------------------------- attachments

/** Images and audio are stored as files, with only a short link in the body. **Not inlined as data URIs**: note bodies are stored
 * in sqlite, and a phone photo is two or three MB after base64, carried along with every autosave and every
 * harness round's context. */
export const uploadAsset = (file: File) => {
  const fd = new FormData()
  fd.append('file', file, file.name)
  return fetch('/api/assets', { method: 'POST', headers: headers(), body: fd })
    .then(json<{ url: string; name: string; kind: 'image' | 'audio'; bytes: number }>)
}

/** An image -> a markdown table. Image reading goes to the **local** vision-capable model; images never leave the intranet.
 * When no table can be recognized detected=false, and the frontend truthfully says "no table detected" -- far better than stuffing
 * an empty table into the user's note. */
export const tableFromImage = (file: File, signal?: AbortSignal) => {
  const fd = new FormData()
  fd.append('file', file, file.name)
  return fetch('/api/compose/table-from-image', { method: 'POST', headers: headers(), body: fd, signal })
    .then(json<{ detected: boolean; table: string; raw: string }>)
}

// ---- Screen activity (Daily Journey, docs/daily-journey-plan.md) ----
//
// Segments land on the shell side (`<userData>/journey/<date>/`); these APIs only "turn segments into
// knowledge-base records" and "read a given day". Daily reports and cross-period reports do not start from scratch here --
// `compose/digest` is already that.

export type JourneySegment = {
  /** This segment's index in that day's file -- **deleting a segment goes by it** (deleted positions are kept, never renumbered). */
  i: number
  start: string; end: string; app: string; title: string
  desc: string; n: number; has_frame: boolean; has_thumb: boolean
  /** Why this segment will **never** get a description (empty string = not its turn yet). Old backends lack this field. */
  skip?: string
}
export type JourneyDay = {
  date: string; segments: JourneySegment[]; minutes: number
  /** Daily reports already written, along with **how many segments each was written from** -- a daily report is a snapshot, and the day is still growing. */
  report: string; report_segments: number; report_at: string
  /** The daily report's deterministic check result (backend `harness/checks/journey.py`, plan 8.2).
   *  **Judged but not blocking**: written to disk with the report, still there after a refresh. */
  report_notes?: string[]
}
export type JourneyReport = { date: string; report: string; segments: number; report_at: string; notes?: string[]; took_ms: number }
export type JourneyRun = {
  date: string; described: number; ingested: number
  skipped: number; left: number; removed_facts: number
}

export type JourneyDeny = {
  apps: string[]; words: string[]
  /** The built-in list **cannot be removed**, read-only */
  builtin_apps: string[]; builtin_words: string[]
}

/** The user's own blacklist. The built-in list is the floor; it can only be added to. */
export const journeyDeny = () =>
  fetch('/api/journey/deny', { headers: headers() }).then(json<JourneyDeny>)

export const journeySetDeny = (apps: string[], words: string[]) =>
  fetch('/api/journey/deny', { method: 'PUT', headers: { ...headers(), 'Content-Type': 'application/json' },
                               body: JSON.stringify({ apps, words }) }).then(json<JourneyDeny>)

// ---------------------------------------------------------------- entity merges
//
// The shape was decided by the user: **one-shot full post-processing, no incremental updates**. Candidates are recomputed each time (pure code, zero calls);
// only human judgments are persisted. Merges only take effect in the display / query layer; the knowledge base is untouched and can be undone anytime.

export type EntityMergeCandidate = {
  a: string; b: string
  /** Which signal pointed it out: initials / translit / spelling / substring */
  why: string
  score: number
  name_a: string; name_b: string
  facts_a: number; facts_b: number; facts_total: number
  sample_a: string[]; sample_b: string[]
  /** Sentences that mention both names. **Easiest to judge when present** -- but it is not the criterion: in the real library
   *  a sentence like "Elisa plans to…, and the CJK spelling of Elisa will explain a few words…" uses two spellings of the same person in one sentence. */
  both: string[]
}

export type EntityMergeDecision = 'same' | 'different' | 'unsure' | 'drop_a' | 'drop_b'

export const entityMergeCandidates = (limit = 200) =>
  fetch(`/api/kb/entity-merges?limit=${limit}`, { headers: headers() })
    .then(json<{ candidates: EntityMergeCandidate[]; total: number; decided: number }>)

export const decideEntityMerge = (a: string, b: string, decision: EntityMergeDecision, why = '') =>
  fetch('/api/kb/entity-merges', {
    method: 'POST', headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ a, b, decision, why }),
  }).then(json<{ ok: boolean }>)

export const undoEntityMerge = (a: string, b: string) =>
  fetch(`/api/kb/entity-merges?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
        { method: 'DELETE', headers: headers() }).then(json<{ ok: boolean }>)

/** Which days have records, newest first. Flipping days skips empty ones, also used to tell "has this ever been used". */
export const journeyDays = () =>
  fetch('/api/journey/days', { headers: headers() }).then(json<string[]>)

export const journeyDay = (date = '') =>
  fetch(`/api/journey/day${date ? `?date=${date}` : ''}`, { headers: headers() }).then(json<JourneyDay>)

/** Describe only `limit` segments at a time: a segment takes a dozen seconds, a day has dozens, doing them all takes over ten minutes --
 *  the UI must show progress, not "click and wait ten minutes". */
export const journeyCatchUp = (date = '', limit = 10) =>
  fetch(`/api/journey/catch-up?limit=${limit}${date ? `&date=${date}` : ''}`,
        { method: 'POST', headers: headers() }).then(json<JourneyRun>)


export const journeyReport = (date = '', signal?: AbortSignal) =>
  fetch(`/api/journey/report${date ? `?date=${date}` : ''}`,
        { method: 'POST', headers: headers(), signal }).then(json<JourneyReport>)

export type JourneySpan = {
  date_from: string; date_to: string; days: number
  missing: string[]; note_id: string; title: string; took_ms: number
}

/** A review of a period: **what goes to the model is daily reports, not raw records**; the product lands as a note. */
export const journeySpan = (days: number, signal?: AbortSignal) =>
  fetch(`/api/journey/span?days=${days}`, { method: 'POST', headers: headers(), signal }).then(json<JourneySpan>)

/** Save this day's review as a note -- **hung under that day's journal page**, overwriting one with the same name. */
export const journeySaveReport = (date = '') =>
  fetch(`/api/journey/report/save${date ? `?date=${date}` : ''}`,
        { method: 'POST', headers: headers() }).then(json<JourneySpan>)

/** A segment's thumbnail (256px). Local only. */
export const journeyThumb = (date: string, i: number) => `/api/journey/thumb?date=${date}&i=${i}`

/** Delete a segment: the image, its place on the timeline, **and the fact extracted from it**.
 *  A blacklist cannot block everything -- only being able to delete precisely makes it safe to keep this on. */
export const journeyDeleteSegment = (date: string, i: number) =>
  fetch(`/api/journey/segment?date=${date}&i=${i}`, { method: 'DELETE', headers: headers() }).then(json<JourneyRun>)


export const journeyDeleteDay = (date: string) =>
  fetch(`/api/journey/day?date=${date}`, { method: 'DELETE', headers: headers() }).then(json<JourneyRun>)


//

// thumbnails were never deleted. So the informed-consent screen lacked "how long it is kept" (plan §8.3 lists
// five items) -- **without the feature, that sentence could not be written**.

export type JourneyRetention = {
  /** Days; `0` = keep forever (an option, not the default) */
  segment_days: number; thumb_days: number
  /** How many days full-size images are kept (read-only, `FRAME_KEEP_DAYS`) */
  frame_days: number
  segment_choices: number[]; thumb_choices: number[]
  /** How much is on disk now -- **before "delete", it must be able to say what is being deleted** */
  days: number; segments: number; described: number
  thumbs: number; reports: number; bytes: number; oldest: string
  /** What the last cleanup **could not delete**, shown as is (not silent) */
  failures?: string[]
  /** What this cleanup just removed */
  swept?: { days_removed?: string[]; thumbs_removed?: number; frames_removed?: number
            facts_removed?: number; failures?: string[] }
}

export const journeyRetention = () =>
  fetch('/api/journey/retention', { headers: headers() }).then(json<JourneyRetention>)

/** Change the retention period. **The backend cleans up on the spot after the change** -- if shrinking it did not take effect immediately, the user could not tell
 *  whether the switch does anything. */
export const journeySetRetention = (segment_days: number, thumb_days: number) =>
  fetch('/api/journey/retention', { method: 'PUT', headers: { ...headers(), 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ segment_days, thumb_days }) }).then(json<JourneyRetention>)

/** **Delete everything**: all days' segments, descriptions, thumbnails, full-size images, daily reports + the memories they extracted into the knowledge base.
 *  The switch / blacklist / retention period stay -- those are settings, not records. */
export const journeyWipeAll = () =>
  fetch('/api/journey/all', { method: 'DELETE', headers: headers() }).then(json<JourneyRetention>)


export const memoketStatus = () => fetch('/api/connectors/memoket/status', { headers: headers() })
  .then(json<{ available: boolean; message: string; version?: string }>)
export const memoketAvailable = (signal?: AbortSignal) =>
  fetch('/api/connectors/memoket/available', { headers: headers(), signal }).then(json<ConnectionAvailability>)
export const memoketRead = (tool: string, args: Record<string, unknown>) =>
  fetch('/api/connectors/memoket/read', { method: 'POST', headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ tool, arguments: args }) }).then(json<Record<string, unknown>>)
export const memoketImport = (conversationId: string, title: string, to: 'notes' | 'both' | 'kb') =>
  fetch('/api/connectors/memoket/import', { method: 'POST', headers: headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ conversation_id: conversationId, title, to }) }).then(json<JobOut>)
