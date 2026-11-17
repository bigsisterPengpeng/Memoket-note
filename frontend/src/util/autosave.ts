
export type Autosave = {
  change(content: string): void
  flush(): Promise<void>
  dispose(): void
  /** Whether there are changes not yet persisted */
  dirty(): boolean
}

export function createAutosave(opts: {
  delay: number
  save: (content: string) => Promise<void>
  onError?: (e: unknown) => void
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (t: unknown) => void
}): Autosave {
  const setT = opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = opts.clearTimer ?? ((t) => clearTimeout(t as ReturnType<typeof setTimeout>))
  let pending: string | null = null
  let timer: unknown = null
  let inflight: Promise<void> | null = null
  let disposed = false
  let lastError: unknown

  async function run(): Promise<void> {
    if (inflight) return inflight
    inflight = (async () => {
      while (pending !== null && !disposed) {
        const c = pending
        pending = null
        try { await opts.save(c); lastError = undefined }
        catch (e) {
          // Put the failed edit back for next time; with no newer change, do not auto-retry (avoids hammering on a bad network)
          if (pending === null) pending = c
          lastError = e
          opts.onError?.(e)
          break
        }
      }
    })().finally(() => { inflight = null })
    return inflight
  }

  return {
    change(content) {
      if (disposed) return
      pending = content
      if (timer !== null) clearT(timer)
      timer = setT(() => { timer = null; void run() }, opts.delay)
    },
    async flush() {
      if (timer !== null) { clearT(timer); timer = null }
      if (pending === null && !inflight) return
      await run()
      if (!disposed && pending !== null) throw lastError ?? new Error('Changes have not been saved')
    },
    dispose() {
      disposed = true
      if (timer !== null) { clearT(timer); timer = null }
      pending = null
    },
    dirty() { return pending !== null || inflight !== null },
  }
}
