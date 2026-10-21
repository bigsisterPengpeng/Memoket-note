import { useState } from 'react'
import type { NoteHarnessToolCall } from '../api'
import Icon from './Icon'
import { t } from '../i18n'
import { dimLabel, checkLabel } from '../editor/dimLabel'
import { fmtDateTime } from '../util/time'
import { checkHitKind, type CheckHit } from '../editor/agentRound'

/** What the agent did in one round. Aggregated per round rather than flat per event — the user cares about
 * the causal chain "what it looked up this round, what it changed, what it scored, then how it decided to run the next round";
 * a raw event log makes no sense of it. */
export type AgentRound = {
  round: number
  /** Rounds that skip continuation and only clean up repetition. Such rounds have no continuation increments;
   * marked so users don't think it's stuck. */
  cleanupOnly: boolean
  revisions: number
  toolCalls: NoteHarnessToolCall[]
  toolTruncated: boolean
  scores: Record<string, { level: number; note: string }>
  status: string
  weakest: string | null
  /** Adjustments the policy controller made after this round. Empty array = no adjustment (all normal). */
  policyReasons: string[]

  policy: Partial<{ tool_iters: number; continue_temperature: number;
                    max_revisions: number; require_verification: boolean }> | null
  errors: string[]
  /** Revisions dropped by the guard, with reasons. Separate from errors: this is the guard working normally;
   * mixed into errors it would turn the UI into a sea of red. */
  dropped: string[]

  warnings?: RoundWarning[]
  /** A code criterion (not the model) failed this round on the spot. When hit, this round **won't** spend another
   * model call on scoring — so it must be marked, otherwise users see a 0 score without knowing who judged it.
   *
   * **One round can hit several** (the ones stuck and let through in a row + the final short-circuit one);
   * this used to be singular, the later one overwriting the earlier: the criterion really fired, yet the UI didn't show it —
   * the same shape as "building a criterion isn't using it". */
  checkHits?: CheckHit[]
  /** How many code criteria this mode has in total. Without the denominator, "all passed this round" and
   * "criteria didn't run at all" look identical in the UI. */
  checksTotal?: number
  /** What the last round diagnosed, and where it went this round (backend plan 12.1). */
  steer?: string
  steerDim?: string
  steerMaterial?: boolean
  /** `undefined` = this round had no retrieval-planning step (polish / cleanup only). */
  steerInPlan?: boolean | null

  depthDropped?: number
  depthDroppedAll?: boolean

  factsIrrelevant?: number

  irrelevantDropped?: boolean
  irrelevantSample?: string[]

  citeLocated?: number
  citeMarked?: number
  citeMatched?: number

  judgeHallucinated?: { dimension: string; quotes: string[]; note: string }[]
  /** Current phase (retrieval/edit/write/evaluate) and its human-readable label */
  phase?: string
  phaseLabel?: string
  /** Live output of each phase, stored per phase. thinking is the model's thinking process. */
  phaseText?: Record<string, { thinking: string; output: string }>
  /** Body text streamed out this round. After going two-phase the editor sits completely still for tens of seconds (retrieval planning
   * isn't streaming); showing the written text live in the panel is more useful than a single waiting status line. */
  streamed?: string

  skills?: { scope: string; injected: string[]; menu: string[] }

  restored?: RestoredMark
}


export type RoundWarning = {
  /** Which step (the backend event's `middleware`, e.g. "skeleton"). */
  middleware: string
  /** Which hook of that step (`before_run` / `skeleton` …). **Shown as-is**:
   *  two hooks of the same middleware each throwing are two different things. */
  hook: string
  /** What happened, in the backend's own words. */
  error: string
}


export type RestoredMark = {
  /** When this run happened (the library row's `created_at`). */
  at: string
  /** **What the library doesn't have**, item by item (given by the backend's `store.ROUND_SKELETON_MISSING`). */
  missing: string[]
  /** The numbers the library **does have** for this round, as one human-readable line (`restoredFactsLine`). */
  facts: string
  /** Which criteria fired this round (the library's `fired_checks`; empty if it can't be parsed). */
  firedChecks: string[]
}


export function warningLine(w: RoundWarning): string {
  return t('Step “{step}” failed; this round ran without that capability: {err}', { step: w.middleware, err: w.error })
}

/** That cell's header. **The number is really counted**: one round can have several (one per throw of each hook
 *  of each middleware); hardcoding "lacked one capability" would hide the second. */
export function warningsHead(ws: RoundWarning[]): string {
  const steps = [...new Set(ws.map((w) => w.middleware))]
  return t('This round ran without {n} capabilities ({steps}), so it finished without that evidence', { n: ws.length, steps: steps.join(t(', ')) })
}

/** Wording of the "Skills" line. Extracted as a pure function so a gate can reach it: it's the user's only basis for judging "did the Skill actually load". */
export function skillsLine(s: { injected: string[]; menu: string[] }): string {
  const a = s.injected.length ? t('{n} loaded automatically by scope: {list}', { n: s.injected.length, list: s.injected.join(t(', ')) }) : t('No skills configured for this scope; none loaded')
  const b = s.menu.length ? t('; {n} more without a scope, left for the model to load on demand', { n: s.menu.length }) : ''
  return t('Skills: {a}{b}', { a, b })
}


export function citeCoverLine(located: number, marked: number, matched: number): string {
  if (located <= 0) return t('Nothing written this run has a verbatim source in the materials, so there were no citation ids to attach')
  const wrong = marked - matched
  const tail = marked === 0 ? t(', none were attached')
    : wrong > 0 ? t(', of which {matched} have matching ids and {wrong} do not', { matched, wrong })
      : ''
  return t('{marked} of the {located} citable sentences were cited{tail}', { located, marked, tail })
}

type Props = {
  rounds: AgentRound[]
  status: string
  running: boolean
}

const LEVEL_COLOR: Record<number, string> = { 0: 'var(--del)', 1: 'var(--warn)', 2: 'var(--ins)' }
// The three tables below are data (module-level constants), wrapped in t() at display; each row marked i18n-ignore
const LEVEL_LABEL: Record<number, string> = { 0: 'Insufficient', 1: 'Partial', 2: 'Meets the bar' }

/** Display names of dimensions. The backend uses English keys because writer_harness is a standalone package meant to be open-sourced,
 * carrying no Chinese domain vocabulary; localized names appear only in the presentation layer. */

const PHASE_LABEL: Record<string, string> = {
  retrieval: '① Decide whether to search the knowledge base',
  edit: '② Read through and find problems',
  write: '③ Write',
  evaluate: '④ Score',
}

const TOOL_LABEL: Record<string, string> = {
  search_memory: 'Keyword search',
  list_topics: 'List knowledge base topics',
  list_entities: 'List people / products',
  filter_facts: 'Fetch by topic',
  facts_in_range: 'Fetch by date range',
  fact_sources: 'Trace back to the original conversation',
  search_session_context: 'Follow up in the original conversation',
}

/** The diagnosis text has the shape `dim: note` (backend `loop._steer`); the dimension name is already shown
 * once separately, so strip the prefix here so the same word doesn't appear twice in a line. */
export function stripDim(steer: string): string {
  const at = steer.indexOf(': ')
  return at > 0 ? steer.slice(at + 2) : steer
}


//

// then the whole "⚑ Code check … failed factual grounding. …" passage, and the next card started with "Last round's diagnosis: …"
// as a whole passage again — that passage alone is one or two hundred chars, three times over it filled the right pane, and what
// people really wanted to see, "what this round wrote", was pushed to the very bottom.
//
// **Where each of the three comes from (read from what the backend pins down, not guessed)**:
//   A "Weakest is X: …"         = `st.ev.scores[weakest].note`, via the `evaluate` event.
//   B "⚑ Code check …"          = `check_hit.note` = `Verdict.message`, via the `check_hit` event.
//   C "Last round's diagnosis: …" = `State.steer` = `bag[focus] + ": " + bag[focus_note]`,
//      via **the next round's** `round_start` event; and the two lines at `loop.py:157-158` write exactly
//      **this round's** `st.ev` `weakest` and `_weak_note(st)` — verbatim A.
//
// So the two equalities are **structural**, not statistical:
//   · `C(round N+1) ≡ A(round N)` — those two lines in `loop.py` write unconditionally;
//   · `A ≡ B` (criterion short-circuit rounds) — the short-circuit branch of `middleware/checks.py` fabricates
//     `Evaluation(scores={verdict.dimension: DimensionScore(level=0, note=verdict.message)})`;
//     the scorer never ran, so "the weakest dimension's diagnosis" is the criterion's sentence.
//

//   · rounds with A: **429**, of which criterion short-circuit rounds (A ≡ B) **261 = 60.8%**;
//   · cards that would show C: **311**, C ≡ the previous card's A **311 = 100.0%**;
//   · all three the same sentence (previous round a short-circuit round) **191 = 61.4%**.
//
// **Merge rule**: verbatim identical ⇒ show once and say where the other one is ("this round acted on it" /
// "the verdict is the criterion below"); **only different ones are listed separately**, not a single char folded.
// The folded original goes into `title`, not deleted.
// The comparison **only normalizes whitespace**, no fuzzy matching — §21: criteria should be narrow;
// the cost of folding wrongly is "users think two places say the same thing when they don't", much worse than reading it twice.

function normDiag(s: string | undefined): string {
  return (s ?? '').replace(/\s+/g, ' ').trim()
}

/** Whether two diagnoses are verbatim the same sentence (after whitespace normalization). Empty strings always count as "different". */
export function sameDiag(a: string | undefined, b: string | undefined): boolean {
  const x = normDiag(a)
  return x !== '' && x === normDiag(b)
}

/** This round's "Weakest is X: …" is exactly the verdict of the ⚑ criterion on the same card (= a criterion short-circuit round). */
export function weakestEchoedByCheck(r: AgentRound): boolean {
  const note = r.weakest ? r.scores?.[r.weakest]?.note : ''
  return (r.checkHits ?? []).some((h) => h.dimension === r.weakest && sameDiag(h.note, note))
}

/** This card's "Last round's diagnosis" is exactly the previous card's "Weakest is" passage.
 *
 * **`steerDim` must match too**: `State.steer`'s dimension name is copied from the same field as `weakest`;
 * a mismatch means another round happened in between (or the diagnosis changed carrier), and "it's the sentence above" would be false. */
export function steerEchoedByPrev(r: AgentRound, prev?: AgentRound): boolean {
  if (!r.steer || !prev) return false
  const prevNote = prev.weakest ? prev.scores?.[prev.weakest]?.note : ''
  return !!r.steerDim && r.steerDim === prev.weakest && sameDiag(stripDim(r.steer), prevNote)
}


//

// in a three-round Smart Continue, among 3396 chars in the right pane,
// "Code check: your done criteria failed factual grounding (check 14 of 19); no model call was spent on scoring this round."

// taking 225 chars ≈ 6.6%, while only the second half actually differed.
//
// **Merge only adjacent ones with verbatim-identical headers** (same criterion + same dimension + same "check N",
// and neither is a special case like "stuck, let through" / "wrap-up") —
// no cross-position grabbing, no fuzzy matching: §21 criteria should be narrow; merging wrongly tells users
// "these two were judged by the same criterion", which may be false.

export type CheckHitGroup = { head: CheckHit; notes: string[] }

function hitKey(h: CheckHit): string | null {
  if (h.stuck_rounds || h.stopped) return null     // these two each appear only once and don't take part in merging

  // Identical at runtime (`\u0000` is that byte); only the source file's encoding changes:
  // a real NUL makes `file(1)` classify the whole `.tsx` as `data`, so `grep` **silently skips it** —


  // grep just couldn't see them. The gate is `frontend/scripts/check-greppable.mts`.
  // A byte that makes search fail silently costs far more than the little it saves.
  return `${h.check ?? ''}\u0000${h.dimension ?? ''}\u0000${h.ran ?? ''}`
}

/** Merge adjacent ⚑ with the same header into one: the header said once, verdicts listed one by one. */
export function groupCheckHits(hits: CheckHit[]): CheckHitGroup[] {
  const out: CheckHitGroup[] = []
  for (const h of hits) {
    const k = hitKey(h)
    const last = out[out.length - 1]
    if (k !== null && last && hitKey(last.head) === k) { last.notes.push(h.note); continue }
    out.push({ head: h, notes: [h.note] })
  }
  return out
}


export function dimParen(dim: string | undefined): string {
  const s = dimLabel(dim || '')
  return s ? t(' ({title})', { title: s }) : ''
}

/** 0/1/2 drawn as three signal bars — easier than bare numbers for scanning a row of dimensions to see which collapsed. */
function LevelBars({ level }: { level: number }) {
  return (
    <span style={{ display: 'inline-flex', gap: 2, alignItems: 'flex-end', height: 11 }}>
      {[1, 2, 3].map((i) => (
        <i
          key={i}
          style={{
            display: 'block',
            width: 3,
            height: `${i * 33}%`,
            background: i <= level + 1 ? LEVEL_COLOR[level] : 'var(--line)',
          }}
        />
      ))}
    </span>
  )
}

function ToolCallRow({ call }: { call: NoteHarnessToolCall }) {
  const [open, setOpen] = useState(false)
  // The search terms are the model's own; they're the key information for judging "did it search in the right direction",
  // so they're visible even when collapsed, while the raw results hide behind expansion.
  const query = Object.entries(call.args)
    .filter(([k]) => k !== 'limit')
    .map(([, v]) => String(v))
    .join(' / ')
  const empty = /^[(\uff08]/.test(call.result)   // empty results come back wrapped in parentheses (ASCII or fullwidth)
  return (
    <li style={{ marginBottom: 4, fontSize: 'var(--t-sm)', lineHeight: 1.5 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        title={open ? t('Collapse results') : t('Show the retrieved text')}
        style={{
          all: 'unset', cursor: 'pointer', display: 'flex', gap: 6,
          alignItems: 'baseline', width: '100%',
        }}
      >
        <span className="muted" style={{ width: 10, flexShrink: 0 }}>{open ? '▾' : '▸'}</span>
        <span style={{ color: 'var(--accent)', flexShrink: 0 }}>
          {t(TOOL_LABEL[call.tool] ?? call.tool)}
        </span>
        <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {query || t('(no arguments)')}
        </span>
        {empty && <span className="muted" style={{ flexShrink: 0 }}>{t('Nothing found')}</span>}
      </button>
      {open && (
        <pre
          style={{
            margin: '4px 0 6px 16px', padding: '6px 8px', fontSize: 'var(--t-xs)', lineHeight: 1.6,
            whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 200, overflowY: 'auto',
            background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 'var(--r-xs)',
          }}
        >
          {call.result}
        </pre>
      )}
    </li>
  )
}


export default function AgentActivity({ rounds, status, running }: Props) {
  if (!rounds.length && !status) return null
  const sorted = [...rounds].sort((a, b) => a.round - b.round)
  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h2 style={{ margin: 0 }}>{t('Agent run')}</h2>
        {running && <span className="spinner" />}
      </div>

      {status && (
        <p className="muted" style={{ margin: '6px 0 10px', fontSize: 'var(--t-sm)' }}>{status}</p>
      )}

      {}
      {sorted.map((r, i) => (
        <div
          key={r.round}
          style={{
            marginBottom: 10, padding: '8px 10px', fontSize: 'var(--t-sm)',
            border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', background: 'var(--panel)',
          }}
        >
          <div className="row" style={{ gap: 8, alignItems: 'baseline', marginBottom: 6 }}>
            <strong>{r.round === 0 ? t('Before start') : t('Round {n}', { n: r.round })}</strong>
            {r.cleanupOnly && (
              <span className="muted" title={t('Last round’s score found problems in the existing text, so this round only cleans up without adding')}>
                {t('Cleanup only, no new text')}
              </span>
            )}
            {}
            {!r.restored && <span className="muted">{t('{n} revisions', { n: r.revisions })}</span>}
            {r.phaseLabel && (
              <span style={{ color: 'var(--accent)', marginLeft: 'auto' }}>
                {r.phaseLabel}
              </span>
            )}
          </div>

          {}
          {r.restored && (
            <div className="agent-restored">
              <div>
                <b>{t('This card is a skeleton read back from the database')}</b>
                {}
                {r.restored.at && t(' (that run: {at})', { at: fmtDateTime(r.restored.at) })}
                {t(' — the details of this round lived only in that run and were not stored.')}
              </div>
              {r.restored.facts && <div style={{ marginTop: 2 }}>{t('Stored: {facts}', { facts: r.restored.facts })}</div>}
              {r.restored.firedChecks.length > 0 && (
                <div style={{ marginTop: 2 }}>
                  {t('Code checks hit: {list}', { list: r.restored.firedChecks.map((c) => checkLabel(c)).join(t(', ')) })}
                </div>
              )}
              {r.restored.missing.length > 0 && (
                <div style={{ marginTop: 2 }}>
                  {t('The database has ')}<b>{t('no')}</b>{t(': ')}{r.restored.missing.join(t(', '))}
                </div>
              )}
            </div>
          )}

          {/* The first item of "why this round runs this way": what the last round diagnosed, and **where that diagnosis
              went this round**. The panel used to show only the result of `adjust()`
              (retrieval budget / temperature), while what really decides what this round looks up is this sentence. */}
          {r.steer && (
            <p className="muted" style={{ margin: '0 0 6px', lineHeight: 1.55 }}
               title={steerEchoedByPrev(r, sorted[i - 1]) ? stripDim(r.steer) : undefined}>
              {t('Last round’s diagnosis: ')}{r.steerDim ? t('“{dim}”', { dim: dimLabel(r.steerDim) }) : ''}
              {steerEchoedByPrev(r, sorted[i - 1])
                ? t(' — the same line as on the round {n} card above; this round acted on it.', { n: sorted[i - 1].round })
                : stripDim(r.steer)}
              <br />
              {r.steerInPlan === true && t('→ This went into this round’s retrieval plan.')}
              {r.steerInPlan === false && (r.steerMaterial
                ? t('→ Not in this round’s retrieval plan (the policy controller produced no direction for it).')
                : t('→ Not a retrieval item: ten more facts won’t fix this dimension; it goes through revision instead.'))}
              {r.steerInPlan == null && t('→ This round had no retrieval planning step (cleanup / polish only).')}
            </p>
          )}

          {}
          {!!r.depthDropped && (
            <div className="muted" style={{ marginBottom: 3 }}>
              {t('{n} searches were dropped by the “deep-dive only from round 2” rule', { n: r.depthDropped })}
              {r.depthDroppedAll && t(' (the whole batch was dropped; this round’s tool loop ended there)')}
            </div>
          )}

          {}
          {!!r.factsIrrelevant && (
            <div className="muted" style={{ marginBottom: 3 }}
                 title={(r.irrelevantSample ?? []).join('\n')}>
              {t('{verb} {n} materials unrelated to this note (sampled from topics with thousands of facts, zero overlap with the text{tail})', { verb: r.irrelevantDropped ? t('Filtered out') : t('Flagged'), n: r.factsIrrelevant, tail: r.irrelevantDropped ? '' : t('; not removed, still in the materials') })}
              {(r.irrelevantSample ?? []).length > 0 && `${t(': ')}${(r.irrelevantSample ?? [])[0]}…`}
            </div>
          )}

          {}
          {r.citeLocated !== undefined && (
            <div className="muted" style={{ marginBottom: 3 }}>
              {citeCoverLine(r.citeLocated, r.citeMarked ?? 0, r.citeMatched ?? 0)}
            </div>
          )}

          {r.skills && (
            <div className="muted agent-skills" style={{ marginBottom: 3 }} title={t('Scope: {scope}', { scope: r.skills.scope })}>{skillsLine(r.skills)}</div>
          )}

          {(r.toolCalls ?? []).length > 0 && (
            <>
              <div className="muted" style={{ marginBottom: 3 }}>
                {t('The agent chose to search {n} times', { n: (r.toolCalls ?? []).length })}
                {r.toolTruncated && t(' (hit the limit, wanted to keep searching)')}
              </div>
              <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 6px' }}>
                {(r.toolCalls ?? []).map((c, i) => <ToolCallRow key={i} call={c} />)}
              </ul>
            </>
          )}

          {Object.keys(r.scores ?? {}).length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px', margin: '4px 0 6px' }}>
              {Object.entries(r.scores).map(([dim, sc]) => (
                <span
                  key={dim}
                  title={`${t(String(LEVEL_LABEL[sc.level] ?? sc.level))}${t(': ')}${sc.note}`}
                  style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}
                >
                  <LevelBars level={sc.level} />
                  <span style={{ color: sc.level < 2 ? LEVEL_COLOR[sc.level] : 'inherit' }}>
                    {dimLabel(dim)}
                  </span>
                </span>
              ))}
            </div>
          )}

          {}
          {r.weakest && r.scores[r.weakest]?.note && (
            <p className="muted" style={{ margin: '0 0 6px', lineHeight: 1.55 }}
               title={weakestEchoedByCheck(r) ? r.scores[r.weakest].note : undefined}>
              {weakestEchoedByCheck(r)
                ? t('Weakest: “{dim}” — this round was not scored; the verdict is the ⚑ code check below.', { dim: dimLabel(r.weakest) })
                : t('Weakest: “{dim}”: {note}', { dim: dimLabel(r.weakest), note: r.scores[r.weakest].note })}
            </p>
          )}

          {}
          {(r.judgeHallucinated ?? []).map((h) => (
            <p key={h.dimension} className="muted" style={{ margin: '0 0 6px', lineHeight: 1.55 }}
               title={h.note}>
              {t('“{dim}” was not scored: the judge claimed the text contains “{quotes}”, which it does not', { dim: dimLabel(h.dimension), quotes: h.quotes.join(t('”, “')) })}
            </p>
          ))}

          {(r.policyReasons ?? []).length > 0 && (
            <div
              style={{
                marginTop: 6, paddingTop: 6, borderTop: '1px dashed var(--line)',
              }}
            >
              <div className="muted" style={{ marginBottom: 3 }}>
                {t('Adjusted the next round accordingly')}
                {r.policy && (
                  <span>
                    {' · '}{t('retrieval budget')} {r.policy.tool_iters}
                    {' · '}{t('continue temperature')} {r.policy.continue_temperature}
                    {' · '}{t('revision quota')} {r.policy.max_revisions}
                    {r.policy.require_verification && ` · ${t('source verification required')}`}
                  </span>
                )}
              </div>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {(r.policyReasons ?? []).map((reason, i) => (
                  <li key={i} style={{ display: 'flex', gap: 5, lineHeight: 1.55 }}>
                    <span style={{ color: 'var(--accent)', flexShrink: 0 }}>↻</span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {r.phaseText && Object.entries(r.phaseText).map(([ph, txt]) => (
            <details key={ph} style={{ marginTop: 4 }}>
              <summary style={{ cursor: 'pointer', color: 'var(--muted)' }}>
                {t(PHASE_LABEL[ph] ?? ph)}
                {r.phase === ph && <span style={{ color: 'var(--accent)' }}> · {t('in progress')}</span>}
                <span className="muted">
                  {t(' (thinking {thinking} chars · output {output} chars)', { thinking: (txt.thinking ?? '').length, output: (txt.output ?? '').length })}
                </span>
              </summary>
              {txt.thinking && (
                <pre style={{
                  margin: '4px 0 0', padding: '6px 8px', fontSize: 'var(--t-xs)', lineHeight: 1.6,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 160,
                  overflowY: 'auto', background: 'var(--bg)', border: '1px dashed var(--line)',
                  borderRadius: 'var(--r-xs)', color: 'var(--muted)', fontStyle: 'italic',
                }}>{txt.thinking}</pre>
              )}
              {txt.output && (
                <pre style={{
                  margin: '4px 0 0', padding: '6px 8px', fontSize: 'var(--t-xs)', lineHeight: 1.6,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 200,
                  overflowY: 'auto', background: 'var(--bg)', border: '1px solid var(--line)',
                  borderRadius: 'var(--r-xs)',
                }}>{txt.output}</pre>
              )}
            </details>
          ))}

          {r.streamed && (
            <details open style={{ marginTop: 6 }}>
              <summary style={{ cursor: 'pointer', color: 'var(--muted)' }}>
                {t('Text written this round ({n} chars)', { n: (r.streamed ?? '').length })}
              </summary>
              <pre style={{
                margin: '4px 0 0', padding: '6px 8px', fontSize: 'var(--t-xs)', lineHeight: 1.7,
                whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 260,
                overflowY: 'auto', background: 'var(--bg)', border: '1px solid var(--line)',
                borderRadius: 'var(--r-xs)',
              }}>{r.streamed}</pre>
            </details>
          )}

          {/* The full picture of this round's code criteria: which ones hit (not just the last one),
              and the denominator — say something even when all pass, otherwise "criteria ran and all passed"
              looks exactly like "criteria weren't wired up at all" in the UI. */}
          {groupCheckHits(r.checkHits ?? []).map(({ head: h, notes }, i) => (
            <p key={i} className="muted" style={{ margin: '4px 0 0', lineHeight: 1.55,
                                                  display: 'flex', gap: 5 }}>
              <span style={{ flexShrink: 0 }}>⚑</span>
              <span>
                {checkHitKind(h) === 'stopped' || checkHitKind(h) === 'stuck' ? (
                  <>
                    {t('Check')} <b>{checkLabel(h.check)}</b>{dimParen(h.dimension)}{t(' has been stuck for')}
                    {' '}{t('{n} rounds unchanged — ', { n: h.stuck_rounds ?? '' })}
                    {}
                    {h.stopped ? t('Writing stops here.') : t('Not blocking this round; scoring as usual.')}{h.note}
                  </>
                ) : checkHitKind(h) === 'released' ? (
                  <>
                    {}
                    {t('Code check')} <b>{checkLabel(h.check)}</b> {t('raised a point on {dim}', { dim: dimLabel(h.dimension) })}
                    {h.ran && r.checksTotal ? t(' (check {i} of {total})', { total: r.checksTotal, i: h.ran }) : ''}
                    {t(', ')}{h.judge_floor
                      ? t('no real score for {n} rounds in a row, so this round is not blocked and is scored as usual.', { n: h.judge_floor })
                      : t('but did not block this round — scored as usual; treat this as a reminder.')}
                    {notes.length === 1 ? notes[0] : notes.map((n, j) => (
                      <span key={j} style={{ display: 'block', marginTop: 2 }}>· {n}</span>
                    ))}
                  </>
                ) : (
                  <>
                    {t('Code check')} <b>{checkLabel(h.check)}</b> {t('failed {dim}', { dim: dimLabel(h.dimension) })}
                    {h.ran && r.checksTotal ? t(' (check {i} of {total})', { total: r.checksTotal, i: h.ran }) : ''}
                    {t(', ')}{t('no model call was spent on scoring this round.')}
                    {}
                    {notes.length === 1 ? notes[0] : notes.map((n, j) => (
                      <span key={j} style={{ display: 'block', marginTop: 2 }}>· {n}</span>
                    ))}
                  </>
                )}
              </span>
            </p>
          ))}
          {!!r.checksTotal && !(r.checkHits ?? []).length
            && Object.keys(r.scores ?? {}).length > 0 && (
            <p className="muted" style={{ margin: '4px 0 0', lineHeight: 1.55 }}>
              {t('All {n} code checks passed; this round’s score came from the judge model.', { n: r.checksTotal })}
            </p>
          )}

          {(r.dropped ?? []).length > 0 && (
            <details style={{ marginTop: 4 }}>
              <summary style={{ cursor: 'pointer', color: 'var(--muted)' }}>
                {t('Dropped {n} revisions', { n: (r.dropped ?? []).length })}
                <span className="muted">{t(' (caught by the guardrails, not an error)')}</span>
              </summary>
              <ul style={{ listStyle: 'none', padding: 0, margin: '4px 0 0 6px' }}>
                {(r.dropped ?? []).map((d, i) => (
                  <li key={i} className="muted" style={{ display: 'flex', gap: 5, lineHeight: 1.55 }}>
                    <Icon n="bx-x" style={{ flexShrink: 0 }} />
                    <span>{d}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}

          {}
          {(r.warnings ?? []).length > 0 && (
            <div style={{ marginTop: 4 }}>
              <p className="muted" style={{ margin: 0, lineHeight: 1.55 }}>
                {warningsHead(r.warnings ?? [])}
              </p>
              <ul style={{ listStyle: 'none', padding: 0, margin: '2px 0 0 6px' }}>
                {(r.warnings ?? []).map((w, i) => (
                  <li key={i} className="muted" style={{ display: 'flex', gap: 5, lineHeight: 1.55 }}>
                    <Icon n="bx-error" style={{ flexShrink: 0 }} />
                    <span>{warningLine(w)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(r.errors ?? []).map((e, i) => (
            <p key={i} style={{ margin: '4px 0 0', color: 'var(--del)', lineHeight: 1.55 }}>
              {e}
            </p>
          ))}
        </div>
      ))}
    </div>
  )
}
