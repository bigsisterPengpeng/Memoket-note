/**
 * SSE stream parsing.
 *
 * This logic originally had **five copies** in api.ts, already inconsistent: the block-generation copy
 * put the event name inside the frame loop (right), the other four outside -- so a data:-only frame
 * would inherit the previous frame's event name. The backend always sends them in pairs so it never blew up, but it was a dud bomb.
 * And only that copy skipped unparseable frames; the other four threw, cutting off the whole stream.
 *
 * Merged into one, this guards it: **splitting frames across chunk boundaries** is the classic way this kind of code breaks
 * -- a frame cut in half by the network, and when untested it silently drops random events.
 */
import { describe, expect, it } from 'vitest'

import { sseFrames } from '../../api'

/** Turn several pieces of text into a Response, each piece being the chunk one read() returns. */
function streamOf(chunks: string[]): Response {
  const enc = new TextEncoder()
  let i = 0
  return {
    body: {
      getReader: () => ({
        read: async () =>
          i < chunks.length
            ? { done: false, value: enc.encode(chunks[i++]) }
            : { done: true, value: undefined },
      }),
    },
  } as unknown as Response
}

async function collect(chunks: string[]) {
  const out: { event: string; payload: any }[] = []
  for await (const f of sseFrames(streamOf(chunks))) out.push(f)
  return out
}

const frame = (event: string, data: unknown) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`

describe('sseFrames', () => {
  it('several frames in one chunk come out in order', async () => {
    const got = await collect([frame('a', { n: 1 }) + frame('b', { n: 2 })])
    expect(got).toEqual([{ event: 'a', payload: { n: 1 } },
                         { event: 'b', payload: { n: 2 } }])
  })

  it('a frame cut between two chunks is put back together whole', async () => {
    // the norm on real networks. The cut point is inside the JSON -- the easiest place to break; multibyte CJK text makes it harder
    const whole = frame('delta', { text: '\u4e00\u6bb5\u4e2d\u6587\u6b63\u6587' })
    const cut = Math.floor(whole.length / 2)
    const got = await collect([whole.slice(0, cut), whole.slice(cut)])
    expect(got).toEqual([{ event: 'delta', payload: { text: '\u4e00\u6bb5\u4e2d\u6587\u6b63\u6587' } }])
  })

  it('no frame is lost when cut inside the blank line that separates frames', async () => {
    const two = frame('a', { n: 1 }) + frame('b', { n: 2 })
    const cut = two.indexOf('\n\n') + 1        // cut exactly between the two newlines
    const got = await collect([two.slice(0, cut), two.slice(cut)])
    expect(got.map((f) => f.event)).toEqual(['a', 'b'])
  })

  it('feeding one byte at a time still puts it back together', async () => {
    const whole = frame('x', { '\u4e2d\u6587': '\u503c', n: 42 })   // a CJK key and value: multibyte UTF-8 split byte by byte
    const got = await collect([...whole])
    expect(got).toEqual([{ event: 'x', payload: { '\u4e2d\u6587': '\u503c', n: 42 } }])
  })

  it('each frame\'s event name is independent', async () => {
    // in the old code the event name carried over across frames: a data:-only frame would be dispatched under the previous frame's
    // name
    const got = await collect([frame('a', { n: 1 }) + 'data: {"n":2}\n\n'])
    expect(got).toEqual([{ event: 'a', payload: { n: 1 } },
                         { event: '', payload: { n: 2 } }])
  })

  it('unparseable frames are skipped without cutting off the whole stream', async () => {
    // giving up a whole generation over one bad frame costs tens of seconds of work
    const got = await collect([
      ': keep-alive\n\n',
      'event: a\ndata: {this is not valid JSON\n\n',
      frame('b', { n: 2 }),
    ])
    expect(got).toEqual([{ event: 'b', payload: { n: 2 } }])
  })

  it('a response without a body errors out right away, rather than silently doing nothing', async () => {
    await expect(async () => {
      for await (const _ of sseFrames({} as Response)) { /* should never get here */ }
    }).rejects.toThrow('no stream')
  })

  it('when the last frame has no trailing blank line it is dropped, never emitting half a frame', async () => {
    const got = await collect([frame('a', { n: 1 }) + 'event: b\ndata: {"n":2'])
    expect(got).toEqual([{ event: 'a', payload: { n: 1 } }])
  })
})
