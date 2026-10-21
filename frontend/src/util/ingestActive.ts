import { useEffect, useState } from 'react'

/** "Is an ingest job running right now" -- the knowledge-base pages only need to poll every 3 seconds then
 *  (facts land chunk by chunk and show up as they are extracted); otherwise the library does not change by itself and polling just wastes backend calls.
 *  App sets it once when a job starts / ends; pages read it via a hook. */
let active = false
const listeners = new Set<(v: boolean) => void>()

export function setIngestActive(v: boolean) {
  if (active === v) return
  active = v
  for (const l of listeners) l(v)
}

export function useIngestActive(): boolean {
  const [v, setV] = useState(active)
  useEffect(() => { listeners.add(setV); return () => { listeners.delete(setV) } }, [])
  return v
}
