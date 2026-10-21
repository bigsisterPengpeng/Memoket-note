/** Editable body for the second split pane (in Trilium every split pane is writable; ours used to be read-only).
 *
 *  Shares no state with the main editor: holds its own body, debounces its own autosave (`util/autosave`),
 *  and once saved hands the server's returned note to App to replace that entry in the list in place. No harness / continue /
 *  proposal layer / citation highlights -- those all live on the main editor; the split pane is for "glance at another note and make a few edits".
 *  When the same note is also open in the main pane App does not use this component (that side renders read-only), so the two never overwrite each other. */
import { useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react'
import * as api from '../api'
import type { Note } from '../api'
import MarkdownEditor from './MarkdownEditor'
import { createAutosave } from '../util/autosave'
import { friendlyError } from '../util/friendlyError'
import { toast } from '../toast'
import { t } from '../i18n'

const SAVE_DELAY_MS = 800

/** Must be mounted with `key={note.id}`. */
export default function SplitEditor({ note, onSaved, flushRef }: {
  note: Note
  onSaved: (n: Note) => void
  /** App flushes this before moving the note to the main pane: otherwise the last 0.8 s of edits in the split pane would be overwritten by the main pane's autosave holding the old body */
  flushRef?: MutableRefObject<(() => Promise<void>) | null>
}) {
  const [content, setContent] = useState(note.content)
  const [status, setStatus] = useState<'' | 'saving' | 'saved' | 'error'>('')
  const live = useRef({ note, onSaved })
  live.current = { note, onSaved }

  const probing = useMemo(() => !!new URLSearchParams(location.search).get('probe'), [])

  const saverRef = useRef<ReturnType<typeof createAutosave> | null>(null)
  const saver = useMemo(() => createAutosave({
    delay: SAVE_DELAY_MS,
    save: async (c) => {
      if (probing) { setStatus('saved'); return }
      setStatus('saving')
      const n = await api.saveNote(live.current.note.id, live.current.note.title, c)
      live.current.onSaved(n)
      setStatus('saved')
    },
    onError: (e) => {
      // 404 = this note was already deleted (removed in the tree, or permanently deleted elsewhere): nothing to save to, drop it silently rather than scaring with "not saved"
      if (/^404\b/.test(e instanceof Error ? e.message : String(e))) { saverRef.current?.dispose(); setStatus(''); return }
      setStatus('error'); toast(t('The split-view note was not saved: {err}', { err: friendlyError(e) }), 'error')
    },
  }), [probing])
  saverRef.current = saver

  // App mounts this component with key={note.id}: a different note = remount, the body comes from useState's initial value.
  // On unmount (closing the split / switching notes) flush anything unsaved before dropping it.
  useEffect(() => () => { void saver.flush(); saver.dispose() }, [saver])
  useEffect(() => {
    if (!flushRef) return
    flushRef.current = () => saver.flush()
    return () => { flushRef.current = null }
  }, [flushRef, saver])

  // This note changed elsewhere (import / undo / revision restore) and there are no unsaved edits here: refresh along with it
  useEffect(() => {
    if (!saver.dirty()) setContent(note.content)
  }, [note.content, saver])

  const onChange = (c: string) => { setContent(c); saver.change(c) }

  return (
    <>
      <MarkdownEditor content={content} onChange={onChange} placeholder={t('Write here…')} />
      {status && (
        <div className="split-save-status muted" aria-live="polite">
          {status === 'saving' ? t('Saving…') : status === 'saved' ? t('Saved') : t('Not saved; your changes stay here and the next edit retries')}
        </div>
      )}
    </>
  )
}
