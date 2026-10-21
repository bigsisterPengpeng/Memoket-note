
export interface Draft { title: string; content: string; at: number }

const key = (noteId: string) => 'memoket-note-draft:' + noteId

export function readDraft(noteId: string): Draft | null {
  try {
    const raw = localStorage.getItem(key(noteId))
    return raw ? (JSON.parse(raw) as Draft) : null
  } catch { return null }
}
export function writeDraft(noteId: string, title: string, content: string) {
  try { localStorage.setItem(key(noteId), JSON.stringify({ title, content, at: Date.now() })) } catch { /* does not matter */ }
}
export function clearDraft(noteId: string) {
  try { localStorage.removeItem(key(noteId)) } catch { /* does not matter */ }
}


export function resolveDraft(note: { title: string; content: string; updated_at: string }, draft: Draft | null, isProbe: boolean):
  { title: string; content: string; restored: boolean; clear: boolean } {
  if (draft && draft.content !== note.content && draft.at > Date.parse(note.updated_at)) {
    return { title: draft.title || note.title, content: draft.content, restored: true, clear: isProbe }
  }
  return { title: note.title, content: note.content, restored: false, clear: !!draft }
}
