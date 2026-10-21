
import type { NoteRevision } from '../api'
import { t } from '../i18n'

export type RunRound = {
  round_no: number
  before: NoteRevision
  after: NoteRevision | null

  later: NoteRevision[]
}
export type RunHistory = {
  run_id: string
  /** When the first round started */
  at: string
  rounds: RunRound[]
  /** Whether the wrap-up row has arrived (finished / paused): for runs without it the last round only has "before" and cannot be undone */
  finished: boolean
}

/** Grouped by run, newest run first; rounds within a run in ascending order. Runs without round rows (only a harness delivery row) do not count. */
export function groupRuns(revs: NoteRevision[]): RunHistory[] {
  const byRun = new Map<string, NoteRevision[]>()
  // The list is newest first; within a run we need chronological order, so walk it backwards (same-second rows are already ordered by rowid in the list)
  for (let i = revs.length - 1; i >= 0; i--) {
    const r = revs[i]
    if (!r.run_id) continue
    const list = byRun.get(r.run_id) ?? []
    list.push(r)
    byRun.set(r.run_id, list)
  }
  const out: RunHistory[] = []
  for (const [run_id, list] of byRun) {
    const rounds: RunRound[] = []
    list.forEach((r, i) => {
      if (r.reason !== 'round') return
      rounds.push({ round_no: r.round_no, before: r, after: list[i + 1] ?? null, later: list.slice(i + 2) })
    })
    if (!rounds.length) continue
    out.push({ run_id, at: rounds[0].before.created_at, rounds,
               finished: list.some((r) => r.reason === 'run_end' || r.reason === 'harness') })
  }
  out.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0))
  return out
}

export type HistoryItem =
  | { kind: 'rev'; rev: NoteRevision }
  | { kind: 'run'; run_id: string; revs: NoteRevision[] }

/** For the history panel: rows of the same run fold into one group (placed where its newest row is); other rows as before; still newest first. */
export function historyGroups(revs: NoteRevision[]): HistoryItem[] {
  const out: HistoryItem[] = []
  const seen = new Set<string>()
  for (const r of revs) {
    if (!r.run_id) { out.push({ kind: 'rev', rev: r }); continue }
    if (seen.has(r.run_id)) continue
    seen.add(r.run_id)
    out.push({ kind: 'run', run_id: r.run_id, revs: revs.filter((x) => x.run_id === r.run_id) })
  }
  return out
}

/** Why a history row kept this revision, for people to read. */
export function revisionLabel(r: Pick<NoteRevision, 'reason' | 'round_no'>): string {
  switch (r.reason) {
    case 'auto': return t('Auto')
    case 'manual': return t('Manual')
    case 'before_restore': return t('Before restore')
    case 'harness': return t('AI delivery')
    case 'round': return t('Before round {n}', { n: r.round_no })
    case 'run_end': return t('Finished (after round {n})', { n: r.round_no })
    default: return r.reason
  }
}

/** A run's title: how many rounds, and how many characters the last round reached. */
export function runTitle(run: RunHistory): string {
  const n = run.rounds.length
  const end = run.rounds[n - 1].after?.chars
  const delta = end != null ? end - run.rounds[0].before.chars : null
  const tail = delta == null ? '' : ' · ' + t('{n} chars', { n: `${delta >= 0 ? '+' : ''}${delta}` })
  return t('Smart Continue · {n} rounds', { n }) + tail + (run.finished ? '' : ' · ' + t('not finished'))
}
