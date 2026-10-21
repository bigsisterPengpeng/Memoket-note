import { describe, expect, it } from 'vitest'
import { consumeHarnessStream } from '../../api'
import { withCheckHit } from '../agentRound'

/** User screenshot: in the Agent run panel "Round 0" sat below "Round 1" -- activity snapshot / tool result events carry no round,
 * and used to be recorded as round 0 across the board. */
function sse(frames: { event: string; data: unknown }[]): Response {
  const text = frames.map((f) => `event: ${f.event}\ndata: ${JSON.stringify(f.data)}\n\n`).join('')
  return new Response(text, { headers: { 'Content-Type': 'text/event-stream' } })
}

describe('which round harness stream events belong to', () => {
  it('snapshots and tool results follow the round of the latest STEP_STARTED', async () => {
    const phases: number[] = []; const tools: number[] = []
    await consumeHarnessStream(sse([
      { event: 'ACTIVITY_SNAPSHOT', data: { content: 'before the run' } },
      { event: 'STEP_STARTED', data: { step: 1, label: 'Round one' } },
      { event: 'ACTIVITY_SNAPSHOT', data: { content: 'writing…' } },
      { event: 'TOOL_CALL_RESULT', data: { toolName: 'recall', args: {}, content: 'x' } },
      { event: 'STEP_STARTED', data: { step: 2, label: 'Round two' } },
      { event: 'ACTIVITY_SNAPSHOT', data: { content: 'scoring' } },
      { event: 'RUN_FINISHED', data: { reason: 'complete' } },
    ]), { onPhase: (d) => phases.push(d.round), onToolCalls: (d) => tools.push(d.round) })
    expect(phases).toEqual([0, 1, 1, 2, 2])
    expect(tools).toEqual([1])
  })
})

describe('the check_hit after a criterion has been stuck for its full count', () => {
  it('stuck_rounds travels all the way to the panel, not swallowed by the event layer', async () => {
    const hits: { dimension: string; note: string; stuck_rounds?: number }[] = []
    await consumeHarnessStream(sse([
      { event: 'STEP_STARTED', data: { step: 1, label: 'Round one' } },
      { event: 'CUSTOM', data: { name: 'check_hit', value: { dimension: 'factual_grounding', note: 'has placeholder sentences' } } },
      { event: 'STEP_STARTED', data: { step: 3, label: 'Round three' } },
      // after being stuck for the full count the backend no longer short-circuits; the event is still sent, with an extra stuck_rounds
      { event: 'CUSTOM', data: { name: 'check_hit', value: { dimension: 'factual_grounding', note: 'has placeholder sentences', stuck_rounds: 3 } } },
      { event: 'RUN_FINISHED', data: { reason: 'complete' } },
    ]), { onCheckHit: (d) => hits.push(d) })

    expect(hits.map((h) => h.stuck_rounds)).toEqual([undefined, 3])
    expect(hits[1].note).toBe('has placeholder sentences')
  })
})

describe('the two CUSTOM events added in batch 23', () => {
  it('cost cap: the numbers travel to the panel, and the done that follows has reason cost_cap', async () => {
    const costs: { tokens: number; cap: number; detail: string }[] = []
    let reason = ''
    await consumeHarnessStream(sse([
      { event: 'STEP_STARTED', data: { step: 2, label: 'Round two' } },
      { event: 'CUSTOM', data: { name: 'cost', value: { round: 2, tokens: 520000, cap: 500000, calls: 31, detail: 'hit the single-run cap' } } },
      { event: 'RUN_FINISHED', data: { reason: 'cost_cap', content: 'the best round' } },
    ]), { onCost: (d) => costs.push(d), onDone: (r) => { reason = r } })

    // **not a silent truncation**: the event says how much was spent, done's reason says it stopped because of that; both halves arrive.
    expect(costs).toHaveLength(1)
    expect(costs[0].tokens).toBe(520000)
    expect(reason).toBe('cost_cap')
  })

  it('worse than the previous run: report it, leave the body alone (report only, no rollback)', async () => {
    const worse: { met: number; last_met: number; detail: string }[] = []
    await consumeHarnessStream(sse([
      { event: 'CUSTOM', data: { name: 'cross_run', value: { met: 2, last_met: 3, mean: 1.6, last_mean: 2, dimensions: ['non_repetition'], detail: 'this run finished worse than the previous one' } } },
      { event: 'RUN_FINISHED', data: { reason: 'complete' } },
    ]), { onCrossRun: (d) => worse.push(d) })

    expect(worse).toHaveLength(1)
    expect([worse[0].last_met, worse[0].met]).toEqual([3, 2])
  })
})

describe('batch 24: the two things behind "why this round runs this way" (plan 12.1)', () => {
  it('the steer in the round payload reaches the panel, and "no retrieval-planning step" must not degrade into false', async () => {
    const seen: { round: number; steer?: string; in_plan?: boolean | null }[] = []
    await consumeHarnessStream(sse([
      { event: 'CUSTOM', data: { name: 'round_summary', value: {
        round: 2, max_rounds: 8, revisions_applied: 0,
        steer: 'non_repetition: said the same thing twice', steer_dim: 'non_repetition',
        steer_material: false, steer_in_plan: false, checks_total: 14 } } },
      // a polish round has no retrieval-planning step at all: the backend gives null, not false
      { event: 'CUSTOM', data: { name: 'round_summary', value: {
        round: 3, max_rounds: 8, revisions_applied: 0,
        steer: 'coherence: heading levels are messed up', steer_dim: 'coherence',
        steer_material: false, steer_in_plan: null, checks_total: 14 } } },
      { event: 'RUN_FINISHED', data: { reason: 'complete' } },
    ]), { onRoundStart: (d) => seen.push({ round: d.round, steer: d.steer, in_plan: d.steer_in_plan }) })

    expect(seen.map((s) => s.round)).toEqual([2, 3])
    expect(seen[0].steer).toContain('said the same thing twice')
    // **`false` and `null` are not the same**: the former is "the step exists but the diagnosis did not enter",
    // the latter is "this round has no such step at all". Merged into one value, the panel could only guess.
    expect(seen[0].in_plan).toBe(false)
    expect(seen[1].in_plan).toBeNull()
  })

  it('when several criteria hit in one round, each one reaches the panel (the later one used to overwrite the earlier)', async () => {
    const hits: { check?: string; ran?: number; stuck_rounds?: number }[] = []
    await consumeHarnessStream(sse([
      { event: 'CUSTOM', data: { name: 'round_summary', value: { round: 4, max_rounds: 8, revisions_applied: 0, checks_total: 14 } } },
      // first comes the one "stuck for the full count, released this round", last the one that really short-circuits
      { event: 'CUSTOM', data: { name: 'check_hit', value: { round: 4, check: 'no_placeholder', ran: 1, dimension: 'factual_grounding', note: 'has placeholder sentences', stuck_rounds: 3 } } },
      { event: 'CUSTOM', data: { name: 'check_hit', value: { round: 4, check: 'citations_exist', ran: 5, dimension: 'factual_grounding', note: 'citations are made up' } } },
      { event: 'RUN_FINISHED', data: { reason: 'complete' } },
    ]), { onCheckHit: (d) => hits.push(d) })

    // two criteria land on **the same dimension** -- dimension alone cannot answer "which criterion hit"
    expect(hits.map((h) => h.check)).toEqual(['no_placeholder', 'citations_exist'])
    expect(hits.map((h) => h.ran)).toEqual([1, 5])
  })
})

describe('batch 24: criterion hits within a round must accumulate (plan 12.1)', () => {
  it('the later one must not overwrite the earlier', () => {
    const stuck = { check: 'no_placeholder', ran: 1, dimension: 'factual_grounding', note: 'has placeholder sentences', stuck_rounds: 3 }
    const short = { check: 'citations_exist', ran: 5, dimension: 'factual_grounding', note: 'citations are made up' }
    // the released stuck one arrives first, the real short-circuit later -- both must be kept
    const r1 = withCheckHit({} as { checkHits?: typeof stuck[] }, stuck)
    const r2 = withCheckHit(r1, short)
    expect(r2.checkHits?.map((h) => h.check)).toEqual(['no_placeholder', 'citations_exist'])
    // the original round object must not be mutated in place (setState wants a new object)
    expect(r1.checkHits).toHaveLength(1)
  })
})
