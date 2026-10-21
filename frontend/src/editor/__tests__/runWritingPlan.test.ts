// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { runWritingPlan } from '../../api'

function fakeFetch(frames: string) {
  const enc = new TextEncoder()
  const body = new ReadableStream({ start(c) { c.enqueue(enc.encode(frames)); c.close() } })
  ;(globalThis as any).fetch = async () => new Response(body, { status: 200 })
}

const sse = (event: string, data: object) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`

describe('runWritingPlan recognizes AG-UI events', () => {
  it('TEXT_MESSAGE_CONTENT / STEP_FINISHED inside a section reach the handler with the current note_id', async () => {
    fakeFetch(
      sse('section-start', { section_id: 's1', title: 'A', note_id: 'n1', is_new_note: true, facts: 0 })
      + sse('TEXT_MESSAGE_START', { messageId: 'r1' })
      + sse('TEXT_MESSAGE_CONTENT', { messageId: 'r1', delta: 'Hello ' })
      + sse('TEXT_MESSAGE_CONTENT', { messageId: 'r1', delta: 'world' })
      + sse('STEP_FINISHED', { step: 1, content: 'Hello world.' })
      + sse('RUN_FINISHED', { reason: 'complete', content: 'Hello world.' })
      + sse('section-done', { section_id: 's1', summary: '', forced: false, blocked: false, blocked_reason: null })
      + sse('done', {}),
    )
    const deltas: [string, string][] = []
    const synced: [string, string][] = []
    await runWritingPlan('p', {
      onDelta: (id, t) => deltas.push([id, t]),
      onNoteContent: (id, c) => synced.push([id, c]),
    })
    expect(deltas).toEqual([['n1', 'Hello '], ['n1', 'world']])
    expect(synced).toEqual([['n1', 'Hello world.'], ['n1', 'Hello world.']])
  })
})
