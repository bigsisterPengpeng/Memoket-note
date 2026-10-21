
import { t } from '../i18n'

export type NoteAction = 'skeleton' | 'tap' | 'harness' | 'polish' | 'restructure' | 'slides' | 'ingest'

/** Action -> the sentence shown to the user when the body is empty. **Say what it was going to do**, not just "empty". */
export const EMPTY_NOTE: Record<NoteAction, string> = {
  skeleton: 'Write some content (or a title) before generating an outline',
  tap: 'Write some content (or a title) before continuing',
  harness: 'Write a title or a few sentences so Smart Continue has something to build on',
  polish: 'The note is empty — nothing to polish',
  restructure: 'The note is empty — nothing to restructure',
  slides: 'This note has no body yet — nothing to turn into slides',
  ingest: 'The note is empty — write something before saving it to the knowledge base',
}

/** These only look at the body, not the title: a one-line title cannot be formatted, made into slides, or have facts extracted. */
const BODY_ONLY = new Set<NoteAction>(['polish', 'restructure', 'slides', 'ingest'])

/** Returns the sentence shown to the user; empty string = allowed. Pure function, the backend has the same one. */
export function notePrecondition(action: NoteAction, content: string, title = ''): string {
  const hasBody = !!content.trim()
  const hasTitle = !!title.trim() && !BODY_ONLY.has(action)
  // `?? ''`: unknown actions are allowed (same as the backend copy). The frontend has a type gate, but the signature says
  // `string`, and without this it returns `undefined` -- the "unknown action" case in `shared/precondition-cases.json`

  return hasBody || hasTitle ? '' : t(EMPTY_NOTE[action] ?? '')
}


export const NOT_CONFIGURED = 'No model configured'
/** The start of the "configured but unreachable" tier (followed by the address). */
export const LLM_UNREACHABLE = 'LLM unreachable'
export const NOT_CONFIGURED_HINT =
  'No model configured — open Settings: choose “Local model” and enter the address and model name (local Ollama is http://127.0.0.1:11434/v1), or choose “OpenAI compatible” and enter a key'

/** The red status bar line. With `configured=false` (factory default, nobody configured anything) **no address is reported**, it says "no model configured";
 *  only when configured and unreachable is the address reported, which the user can change. */
export function healthMessage(h: { ok?: boolean; configured?: boolean; base_url?: string }): string {
  if (h.ok) return ''
  if (h.configured === false) return t(NOT_CONFIGURED)
  return t(LLM_UNREACHABLE) + ' (' + (h.base_url ?? '') + ')'
}


export function llmGateMessage(healthMsg: string): string {
  if (healthMsg === NOT_CONFIGURED || healthMsg === t(NOT_CONFIGURED)) return t(NOT_CONFIGURED_HINT)
  if (!healthMsg.startsWith(LLM_UNREACHABLE) && !healthMsg.startsWith(t(LLM_UNREACHABLE))) return ''
  return healthMsg + t(' — fix the model address / key in Settings first, then try again')
}
