import { useEffect, useRef } from 'react'


export function usePoll(fn: () => void, ms: number, on = true): void {
  // Keep the callback in a ref: callers almost always pass a closure recreated on every render,
  // and putting it in the dependency array would rebuild the timer on every render (the period would restart forever).
  const cb = useRef(fn)
  cb.current = fn

  useEffect(() => {
    if (!on) return
    let timer: number | null = null
    const tick = () => { if (!document.hidden) cb.current() }
    const start = () => { if (timer === null) timer = window.setInterval(tick, ms) }
    const stop = () => { if (timer !== null) { window.clearInterval(timer); timer = null } }
    const onVis = () => { if (document.hidden) stop(); else { cb.current(); start() } }
    start()
    document.addEventListener('visibilitychange', onVis)
    return () => { stop(); document.removeEventListener('visibilitychange', onVis) }
  }, [ms, on])
}
