
export type Spot = { head: number; top: number }

const MAX = 60
const key = (user: string) => 'memoket-note-spots:' + user

export function loadSpots(user: string): Map<string, Spot> {
  try {
    const raw = localStorage.getItem(key(user))
    const obj = raw ? (JSON.parse(raw) as Record<string, Spot>) : {}
    return new Map(Object.entries(obj).filter(([, v]) => v && typeof v.head === 'number'))
  } catch { return new Map() }
}

export function saveSpots(user: string, spots: Map<string, Spot>) {
  // When over the limit, drop from the oldest (a Map's insertion order = order of last set; rememberSpot deletes before setting)
  while (spots.size > MAX) spots.delete(spots.keys().next().value as string)
  try { localStorage.setItem(key(user), JSON.stringify(Object.fromEntries(spots))) } catch { /* private mode cannot write; not worth an error */ }
}

/** Remember a note's position: delete then insert, so it moves to the end of the Map (LRU). */
export function putSpot(spots: Map<string, Spot>, id: string, spot: Spot) {
  spots.delete(id)
  spots.set(id, spot)
}
