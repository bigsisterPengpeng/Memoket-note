
const dayOf = (iso: string) => iso.slice(5, 10)                  // MM-DD
const minuteOf = (iso: string) => iso.slice(5, 16).replace('T', ' ')

type Row = { key: string; title: string; at: string }

export function dupSuffixes(rows: Row[]): Map<string, string> {
  const byTitle = new Map<string, Row[]>()
  for (const r of rows) {
    const t = r.title.trim()
    if (!t) continue          // a column of "Untitled" should not all get dates
    const list = byTitle.get(t)
    if (list) list.push(r)
    else byTitle.set(t, [r])
  }

  const out = new Map<string, string>()
  for (const list of byTitle.values()) {
    if (list.length < 2) continue
    const dated = list.filter((r) => r.at)
    if (dated.length < 2) continue
    const days = new Set(dated.map((r) => dayOf(r.at)))
    const label = days.size === dated.length ? dayOf : minuteOf
    const labels = dated.map((r) => label(r.at))
    if (new Set(labels).size < 2) continue     // minutes still cannot separate them: marking would not help
    dated.forEach((r, i) => out.set(r.key, labels[i]))
  }
  return out
}
