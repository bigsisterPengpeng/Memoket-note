/** What scoring dimensions are called in the UI.
 *
 * This table used to live only in `components/AgentActivity.tsx`, while the block-generation path
 * (`App.runBlock`'s onEvaluate) printed dimension names raw into the log -- two places each saying their own thing.
 * After batch 17 it had to be unified: the `prompt` / `custom` modes **generate** a few dimensions on the spot before running
 * (`checklist_1…`, backend `harness/checklist.py`); they are in no
 * hard-coded table, and wherever they land unhandled, the user sees something like `checklist_1`.
 */
import { t } from '../i18n'
const FIXED: Record<string, string> = {
  spine_fidelity: 'On topic',
  topic_fidelity: 'On topic',
  beat_coverage: 'Beat coverage',
  non_repetition: 'No repetition',
  coherence: 'Coherence',
  factual_grounding: 'Grounding',
  material_use: 'Uses your materials',
  style_fit: 'Style fit',
  prose_quality: 'Prose quality',
  workflow_fidelity: 'Workflow quality',
  follows_prompt: 'Follows your instruction',
  fits_context: 'Fits the context',
  no_fabrication: 'No fabrication',
  replaces_cleanly: 'Replaces the selection cleanly',
  // **Not a scoring dimension, the criteria's fallback bucket** (backend `harness/checks/pick.MECHANICS`,
  // plan 4.4). The scorer never scores it; its appearance only means a code criterion caught
  // a mechanical defect this round (hand-written mermaid, audit voice, flattened outline...), with the details in the note.
  // Before this, these criteria fell back to `coherence`, so the UI showed "Coherence
  // 0 points" -- while nobody had looked at whether the body was coherent.
  mechanics: 'Mechanical defect',
}

/** The ones generated on the spot: `checklist_1` -> "Your requirement 1". */
const CHECKLIST = /^checklist_(\d+)$/

export function dimLabel(dim: string): string {
  const m = CHECKLIST.exec(dim)
  if (m) return t('Your requirement {n}', { n: m[1] })
  return t(FIXED[dim] ?? dim)
}

/** What **criteria** are called in the UI (plan 12.1).
 *
 * A different thing from the table above, and they cannot be merged: which dimension a criterion picks is decided at runtime
 * (backend `checks/pick.pick_dimension`), and **five criteria all land on
 * `factual_grounding`** -- a user seeing "Grounding 0 points" cannot tell whether it was
 * `no_placeholder` or `citations_exist` that judged it. The criterion name is its own identity.
 *
 * The list is reconciled entry by entry with backend `Mode.checks`: `backend/tests/test_event_contract.py`
 * has a gate requiring every criterion the backend registers to have a display name here, otherwise the UI shows
 * raw text like `no_same_sources_twice`.
 */
const CHECKS: Record<string, string> = {
  no_placeholder: 'Placeholder instead of content',
  no_audit_voice: 'Audit voice',
  outline_intact: 'Outline flattened',
  citations_hold: 'Citation does not match the material',
  citations_exist: 'Cited fact does not exist',
  material_thin: 'Too little material',
  citations_present: 'No citation in the whole passage',
  material_used: 'Retrieved material not used',
  no_echoed_text: 'Same text written twice',
  no_repeated_lists: 'Repeated list',
  no_restated_paragraph: 'Paragraph restated',
  no_same_sources_twice: 'Same source used twice',
  no_fake_charts: 'Text pretending to be a chart',
  charts_from_tools: 'Chart not drawn by a tool',
  unsupported_specifics: 'Specific numbers without a source',

  done_criteria: 'Your done criteria',
  workflow_quality: 'Template sections and categories',

  chart_restates_list: 'Chart merely redraws the list',
  language_consistent: 'Language switched',
  no_foreign_script: 'Garbled characters mixed in',
  no_junk_tail: 'Junk sentence at the end',

  output_not_json: 'Whole passage answered as JSON',
  section_budget: 'Section not written enough',
  chart_numbers_grounded: 'Chart numbers ungrounded',
  chart_readable: 'Chart unreadable',
  heading_fits: 'Heading level does not fit',
  tail_clashes: 'Ending clashes with what follows',
  table_present: 'Expected a table, none found',
  table_columns_match: 'Table column count mismatch',
  numbers_from_tools: 'Numbers not computed by a tool',
  instruction_constraints: 'Hard requirements in your instruction',
}

export function checkLabel(check?: string): string {
  if (!check) return t('Code check')
  return t(CHECKS[check] ?? check)
}


const STUCK_TAIL: Record<string, string> = {
  output_not_json:
    '. Every round the model answered with raw JSON, not content that can go into the note — nothing is wrong with what you wrote. Switch models or run again',
}

/** The second half of the stop sentence (empty string if none). */
export function stuckTail(check?: string): string {
  return t((check && STUCK_TAIL[check]) || '')
}
