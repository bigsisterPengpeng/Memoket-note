
import type { TrayItem, TrayItemIn, TrayKind } from '../api'
import { t } from '../i18n'

export const TRAY_KIND_LABEL: Record<TrayKind, string> = { note: 'Notes', fact: 'Fact', import: 'Import', selection: 'Excerpt' }
export const TRAY_KIND_ICON: Record<TrayKind, string> = { note: 'bx-note', fact: 'bx-link', import: 'bx-import', selection: 'bx-text' }
/** How long a tray item's excerpt is: the same number as backend `store.TRAY_EXCERPT_MAX` */
export const TRAY_EXCERPT_MAX = 600
/** How many characters a collapsed item shows in the panel */
export const TRAY_PREVIEW_CHARS = 120


export type TrayAddDetail = Partial<TrayItemIn> & { noteId?: string; items?: TrayItemIn[] }

/** Put an item into the tray from elsewhere. The panel (`TrayPanel`) listens; with no note open it says "open a note first". */
export function requestTrayAdd(item: TrayAddDetail): void {
  window.dispatchEvent(new CustomEvent<TrayAddDetail>('tray-add', { detail: item }))
}


export function trayAddNotice(items: Pick<TrayItemIn, 'kind' | 'excerpt'>[]): string {
  const long = items.filter((it) => (it.kind === 'import' || it.kind === 'selection') && (it.excerpt ?? '').length > TRAY_EXCERPT_MAX)
  if (!long.length) return ''
  const n = Math.max(...long.map((it) => (it.excerpt ?? '').length))
  return t('; only the first {max} chars are kept here (full text {n} chars). For long recordings or documents, save to the knowledge base first and pick the facts you need as materials', { max: TRAY_EXCERPT_MAX, n })
}

/** Append a batch at the end (pure function): each through `withItem`, existing ones skipped, capped at 24 */
export function withItems(items: TrayItem[], add: TrayItemIn[]): TrayItemIn[] {
  let cur: TrayItemIn[] = items.map(({ id, kind, ref_id, title, excerpt }) => ({ id, kind, ref_id, title, excerpt }))
  for (const it of add) {
    if (cur.length >= TRAY_MAX_ITEMS) break
    if (alreadyInTray(cur, it)) continue
    cur = [...cur, { ...it, excerpt: (it.excerpt ?? '').slice(0, TRAY_EXCERPT_MAX) }]
  }
  return cur
}
/** Tray cap: the same number as backend `store.TRAY_MAX_ITEMS` */
export const TRAY_MAX_ITEMS = 24


const pendingAdds = new Map<string, Promise<{ items: TrayItem[]; added: number }>>()

export async function appendTrayItems(noteId: string, add: TrayItemIn[]): Promise<{ items: TrayItem[]; added: number }> {
  const previous = pendingAdds.get(noteId) ?? Promise.resolve()
  const operation = previous.catch(() => {}).then(async () => {
    const { listTray, putTray } = await import('../api')
    const current = await listTray(noteId)
    const next = withItems(current, add)
    const added = next.length - current.length
    const items = added ? await putTray(noteId, next) : current
    setTrayCache(noteId, items)
    return { items, added }
  })
  pendingAdds.set(noteId, operation)
  try { return await operation }
  finally { if (pendingAdds.get(noteId) === operation) pendingAdds.delete(noteId) }
}

export async function landNotesInTray(trayNoteId: string, notes: { id: string; title: string; content: string }[]): Promise<number> {
  const add: TrayItemIn[] = notes.filter((n) => n.id !== trayNoteId)
    .map((n) => ({ kind: 'note', ref_id: n.id, title: n.title, excerpt: noteExcerpt(n.content) }))
  if (!add.length) return 0
  return (await appendTrayItems(trayNoteId, add)).added
}

/** The first few hundred characters of a note -> tray excerpt: drop heading hashes, fold in-note links back into titles, fold blank lines into single newlines */
export function noteExcerpt(content: string, max = TRAY_EXCERPT_MAX): string {
  const plain = (content || '')
    .replace(/\[([^\]\n]+)\]\(note:\/\/[0-9a-f]{12}\)/g, '$1')
    .replace(/^#+\s*/gm, '')
    .replace(/\n{2,}/g, '\n')
    .trim()
  return plain.length > max ? plain.slice(0, max) + '…' : plain
}

/** Putting the same item in twice counts once: note / fact by ref_id, import / selection by content */
export function trayKey(i: Pick<TrayItemIn, 'kind' | 'ref_id' | 'excerpt'>): string {
  return i.kind === 'note' || i.kind === 'fact' ? `${i.kind}:${i.ref_id ?? ''}` : `${i.kind}:${(i.excerpt ?? '').trim()}`
}

export function alreadyInTray(items: Pick<TrayItemIn, 'kind' | 'ref_id' | 'excerpt'>[], item: TrayItemIn): boolean {
  const k = trayKey(item)
  return items.some((i) => trayKey(i) === k)
}

/** Append an item at the end (returned unchanged if already in the tray) -- pure function; the array PUT as a whole is its return value */
export function withItem(items: TrayItem[], item: TrayItemIn): TrayItemIn[] {
  const base: TrayItemIn[] = items.map(({ id, kind, ref_id, title, excerpt }) => ({ id, kind, ref_id, title, excerpt }))
  if (alreadyInTray(base, item)) return base
  return [...base, { ...item, excerpt: (item.excerpt ?? '').slice(0, TRAY_EXCERPT_MAX) }]
}

/** Drag reorder / move up / down: move from to to (pure function) */
export function moveItem<T>(items: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return items
  const next = items.slice()
  const [it] = next.splice(from, 1)
  next.splice(to, 0, it)
  return next
}

// ---- In-process cache: used by `runBlock`'s "Write from tray" to check for empty before running; the panel writes it on every persist
const cache = new Map<string, TrayItem[]>()
export function setTrayCache(noteId: string, items: TrayItem[]): void {
  cache.set(noteId, items)
  window.dispatchEvent(new CustomEvent('tray-changed', { detail: { noteId, count: items.length } }))
}
export function trayCount(noteId: string): number { return cache.get(noteId)?.length ?? 0 }

/** The gate before "Write from tray" runs: with an empty tray, say so and send no request (the backend blocks too, `compose_block` 400). Empty string = allowed */
export function trayPrecondition(noteId: string): string {
  return trayCount(noteId) === 0 ? t('No materials yet — add the notes or facts you need from the Memory tab, then click “Write from materials”.') : ''
}
