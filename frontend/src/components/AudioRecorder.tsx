import { useRef, useState } from 'react'
import { ingestAudio, transcribeOnly } from '../api'
import { toast } from '../toast'
import { t } from '../i18n'
import { friendlyError } from '../util/friendlyError'
import { micError } from '../util/micError'
import { requestTrayAdd } from '../util/tray'
import { recordingTitle, trayByDefault } from '../util/trayDefaults'
import ContextMenu, { type MenuAt, type MenuItem } from './ContextMenu'
import Icon from './Icon'

type Props = {
  /** Insert the transcription at the editor cursor */
  onTranscript: (text: string) => void
  /** After the recording is ingested, returns a job id for the caller to poll */
  onIngested: (jobId: string) => void
  /** Address of the voice service when unreachable (empty string = online). When offline the record button shows an "offline" state: clicking explains first,
   *  rather than letting users record a whole passage only to fail at transcription. */
  offline?: string

  noteId?: string
}

export type RecordTarget = 'insert' | 'memory' | 'tray'

/** Order of the recording menu's three destinations: switch on and a note open → "To tray" first (the default destination); otherwise it goes last / not offered without a note */
export function recordMenuOrder(noteId: string | undefined, byDefault: boolean): RecordTarget[] {
  if (!noteId) return ['insert', 'memory']
  return byDefault ? ['tray', 'insert', 'memory'] : ['insert', 'memory', 'tray']
}

/**
 * Recording -> Whisper. Three destinations:
 *   to tray — after transcription, laid out on the desk as one material (not in the body; the default destination, can be turned off in the tray cell)
 *   insert into body — transcription only, used as voice input
 *   save to knowledge base — after transcription, extracted into facts in the background
 */
export default function AudioRecorder({ onTranscript, onIngested, offline = '', noteId }: Props) {
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState('')
  const [menuAt, setMenuAt] = useState<MenuAt | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const target = useRef<RecordTarget>('insert')

  const abortRef = useRef<AbortController | null>(null)

  async function start(to: RecordTarget) {
    target.current = to
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      chunks.current = []
      const mr = new MediaRecorder(stream)
      mr.ondataavailable = (e) => e.data.size && chunks.current.push(e.data)
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunks.current, { type: 'audio/webm' })
        const ctrl = new AbortController()
        abortRef.current = ctrl
        try {
          if (target.current === 'insert' || target.current === 'tray') {
            setBusy(t('Transcribing'))
            const { text } = await transcribeOnly(blob, 'recording.webm', ctrl.signal)
            // With silence / nothing transcribed there used to be no reaction at all — the user finished recording, clicked stop,
            // nothing happened, and couldn't tell whether it didn't record or something broke.
            if (!text) toast(t('No transcript produced; the recording may be silent — check the microphone'), 'error')

            else if (target.current === 'tray') requestTrayAdd({ kind: 'import', title: recordingTitle(), excerpt: text, noteId })
            else onTranscript(text)
          } else {
            setBusy(t('Transcribing and saving'))
            const { job_id, detail } = await ingestAudio(blob, 'recording.webm', '', ctrl.signal)
            // When transcription is empty the backend returns job_id="" + detail="Transcription result is empty……"
            // (on the success path the detail field carries a preview of the transcribed text, not an error message;
            // the two meanings differ, and it should only be shown as an error on the failure path without a job_id).
            // Before, either case just did onTranscript('') inserting an empty string
            // (i.e. nothing), and detail itself was never shown — users who finished recording likewise
            // saw no reaction at all.
            if (job_id) onIngested(job_id)
            else toast(detail || t('Recording failed'), 'error')
          }
        } catch (err) {
          if ((err as Error).name === 'AbortError') toast(t('Stopped; this recording was not transcribed'))
          else toast(t('Voice processing failed: {err}', { err: friendlyError(err) }), 'error')
        } finally {
          abortRef.current = null
          setBusy('')
        }
      }
      mr.start()
      recorder.current = mr
      setRecording(true)
    } catch (e) {
      toast(micError(e), 'error')
    }
  }

  function stop() {
    recorder.current?.stop()
    setRecording(false)
  }

  // One microphone button, two destinations in the menu (the floating-button spot at the body's top right).
  if (busy) return <button className="fb-btn" title={t('Cancel this transcription and discard the recording')} onClick={() => abortRef.current?.abort()}><span className="spinner" /> {busy}… {t('Stop')}</button>
  if (recording) {
    return <button className="fb-btn rec" onClick={stop} title={t('Stop recording')}><Icon n="bx-stop-circle" /> {t('Stop recording')}</button>
  }
  if (offline) {
    return (
      <button className="fb-btn" title={t('Voice service unreachable ({offline}): recording transcription is unavailable. Check the voice service address in Settings', { offline })}
              onClick={() => toast(t('Voice service unreachable ({offline}); recording transcription is unavailable, everything else works', { offline }), 'error')}>
        <Icon n="bx-microphone-off" style={{ opacity: .6 }} />
      </button>
    )
  }
  const order = recordMenuOrder(noteId, trayByDefault())
  const MENU: Record<RecordTarget, MenuItem> = {
    tray: { label: t('Record → materials'), icon: 'bx-layer-plus', hint: order[0] === 'tray' ? t('Default: transcript becomes reference material for AI writing') : t('Transcript becomes reference material for AI writing'), onSelect: () => void start('tray') },
    insert: { label: t('Record → insert into text'), icon: 'bx-text', hint: t('Transcribe only'), onSelect: () => void start('insert') },
    memory: { label: t('Record → save to knowledge base'), icon: 'bx-brain', hint: t('Transcribe, then extract facts'), onSelect: () => void start('memory') },
  }
  return (
    <>
      <button className="fb-btn" title={order[0] === 'tray' ? t('Record: transcript goes to materials (default), or insert into the text or save to the knowledge base') : t('Record: transcript is inserted into the text, or saved to the knowledge base')}
              onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setMenuAt({ x: r.left, y: r.bottom + 4 }) }}>
        <Icon n="bx-microphone" /><Icon n="bx-chevron-down" className="fb-caret" />
      </button>
      {menuAt && (
        <ContextMenu at={menuAt} onClose={() => setMenuAt(null)} items={order.map((k) => MENU[k])} />
      )}
    </>
  )
}
