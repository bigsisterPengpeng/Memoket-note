// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { watchJob } from '../../api'

afterEach(() => vi.unstubAllGlobals())

it('notifies the note tree when an import stream finishes', async () => {
  const progress = { job_id: 'synthetic-import', status: 'done', facts: 0, items: [] }
  vi.stubGlobal('fetch', vi.fn(async () => new Response(
    `event: progress\ndata: ${JSON.stringify(progress)}\n\nevent: end\ndata: {}\n\n`,
    { headers: { 'Content-Type': 'text/event-stream' } },
  )))
  const changed = vi.fn()
  const onProgress = vi.fn()
  const onEnd = vi.fn()
  window.addEventListener('notes-changed', changed)
  try {
    watchJob('synthetic-import', onProgress, onEnd)
    await vi.waitFor(() => expect(onEnd).toHaveBeenCalledOnce())
    expect(onProgress).toHaveBeenCalledWith(progress)
    expect(changed).toHaveBeenCalledOnce()
  } finally {
    window.removeEventListener('notes-changed', changed)
  }
})
