

/** How alike two sentences are. Bigram Dice -- **CJK has no word boundaries**; character bigrams work for CJK and
 *  for English identifiers in between, and need no dependency at all. */
export function similar(a: string, b: string): number {
  const grams = (s: string) => {
    const t = s.toLowerCase().replace(/\s+/g, '')
    const out = new Set<string>()
    for (let i = 0; i + 1 < t.length; i++) out.add(t.slice(i, i + 2))
    return out
  }
  const A = grams(a), B = grams(b)
  if (!A.size || !B.size) return 0
  let hit = 0
  for (const g of A) if (B.has(g)) hit++
  return (2 * hit) / (A.size + B.size)
}


export const RUN_SIM = 0.45

/** Do not merge across a gap this long: the blank stretch in between is information itself (lunch, a meeting),
 *  and merged, one block would span a whole afternoon with nothing recorded in the middle. Same number as the gap drawn with it. */
export const RUN_GAP_MIN = 15

export type RunSeg = { start: string; end: string; app: string; desc: string }

export type Run<S extends RunSeg> = {
  segs: S[]
  start: string
  end: string
  app: string
  /** Which sentence this block shows. **Take the longest one**: they say the same thing, so take the one with the most information
   *  (specific file names / errors often appear in only one of them). */
  desc: string
}

export function groupRuns<S extends RunSeg>(segs: S[]): Run<S>[] {
  const runs: Run<S>[] = []
  for (const s of segs) {
    const cur = runs[runs.length - 1]
    const gapMin = cur ? (Date.parse(s.start) - Date.parse(cur.end)) / 60_000 : Infinity
    const lead = cur?.segs[0]
    // Compare with the **block's first entry**, not the previous one: chaining one by one drifts -- a is like b, b is like c,
    // and a and c are already two different things.
    const fits = !!cur && !!lead && cur.app === s.app && gapMin < RUN_GAP_MIN
      && (lead.desc.trim() || s.desc.trim()
          ? similar(lead.desc, s.desc) >= RUN_SIM
          : true)                       // neither has a description yet = the two rows look identical, merge
    if (!fits) {
      runs.push({ segs: [s], start: s.start, end: s.end, app: s.app, desc: s.desc })
      continue
    }
    cur.segs.push(s)
    cur.end = s.end
    if (s.desc.trim().length > cur.desc.trim().length) cur.desc = s.desc
  }
  return runs
}
