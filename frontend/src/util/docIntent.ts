/**
 * Doc intent (docs/agent-native-editor.md section 3.1): every note knows what it is for.
 *
 * Three fields -- goal / audience / done criteria -- are managed by the editor's "writing mode"
 * and stored in `notes.intent`. **Every AI action on the note puts it first in the system
 * prompt** (skeleton / continue / rewrite / polish / expand / verify / layout): polish finally
 * knows who the note is for, verify checks against the done criteria.
 *
 * New notes never infer a task from the title. Once the user fills it in, source becomes `user`
 * and later title changes do not overwrite it. `prefill` only exists for old data; reading never
 * treats it as user intent.
 * Pure functions only; `as_text` in the backend `editor/intent.py` emits the same format as
 * `intentText`.
 */

export type DocIntent = {
  goal: string; reader: string; done: string; source: '' | 'prefill' | 'user'
  /** The writing workflow the user chose. Not shown as a fourth form field; it only carries the template's quality contract into the Harness. */
  workflow?: WritingWorkflowId | ''

  checked?: string[]
}

/** Workflow ids: the four original single-template workflows plus the 11 template categories of
 *  `editor/writingTemplates.ts` (templates in one category share one backend contract). Open as
 *  string so the catalogue can grow; the backend drops ids it does not know. */
export type WritingWorkflowId = string

/** id -> English display label (show it through `t()`). **Must match `WORKFLOW_LABEL` in the
 *  backend `editor/intent.py` verbatim.** The shared text itself carries the id
 *  (`Workflow: weekly`), so a label change never breaks the round trip. */
export const WORKFLOW_LABEL: Record<WritingWorkflowId, string> = {
  daily: 'Daily report', weekly: 'Weekly report', journal: 'Journal', meeting: 'Meeting notes',
  reports: 'Reports', meetings: 'Meetings', product: 'Product', research: 'Research',
  writing: 'Writing', personal: 'Personal', sales: 'Sales & marketing', engineering: 'Engineering',
  people: 'People', learning: 'Learning & teaching', ops: 'Operations & finance',
}

export const EMPTY_INTENT: DocIntent = { goal: '', reader: '', done: '', source: '', workflow: '', checked: [] }
/** Per-field cap, same as backend `FIELD_MAX` (English text needs about 1.5x the room of Chinese). */
export const INTENT_FIELD_MAX = 300
/** Field labels of the shared text (not UI strings: the backend parses them). */
export const INTENT_LABEL: Record<'goal' | 'reader' | 'done', string> = { goal: 'Goal', reader: 'Audience', done: 'Done' }
export const WORKFLOW_FIELD = 'Workflow'

export function isEmptyIntent(i: DocIntent | null | undefined): boolean {
  return !i || !(i.goal || i.reader || i.done)
}

/** "Workflow: weekly; Goal: ...; Audience: ...; Done: ..." -- only the filled fields. Sent with every AI action. */
export function intentText(i: DocIntent | null | undefined): string {
  // A prefill generated from the title by old versions is not a user choice. Even if hot reload
  // kept the old state, a requirement the UI has cleared must not keep reaching the backend.
  if (!i || i.source === 'prefill' || isEmptyIntent(i)) return ''
  const fields = (['goal', 'reader', 'done'] as const)
    .filter((k) => i[k].trim())
    .map((k) => `${INTENT_LABEL[k]}: ${i[k].trim()}`)
  const workflow = i.workflow && WORKFLOW_LABEL[i.workflow] ? [`${WORKFLOW_FIELD}: ${i.workflow}`] : []
  return [...workflow, ...fields].join('; ')
}

/** Opening a note: only restore a task the user wrote explicitly; old auto-prefills count as empty. */
export function resolveIntent(stored: DocIntent | null | undefined, _title: string): DocIntent {
  // Changed by the user (source=user), or of unknown origin but filled in (written directly
  // through the API): both count as the user's.
  if (stored && !isEmptyIntent(stored) && stored.source !== 'prefill') {
    return { ...stored, source: stored.source || 'user' }
  }
  return { ...EMPTY_INTENT }
}

/**
 * Smart Continue needs a goal the user gave explicitly.
 *
 * Body, skeleton and beats only say "what it has become", not "what the user wants it to be".
 * Spine / beats may themselves have been summarised from the body by the Agent; letting them
 * stand in for the goal would close a loop where the Agent sets the question, answers it and
 * grades itself. So this deliberately does not accept body or skeleton.
 */
export function needsHarnessGoal(intent: DocIntent | null | undefined): boolean {
  return !intent?.goal.trim() || intent.source !== 'user'
}
