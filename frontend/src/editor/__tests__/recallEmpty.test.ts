import { describe, expect, it, vi } from 'vitest'

/**
 * "The knowledge base is empty" and "nothing found this time" must be said as two things.
 *
 * Round 677 screenshot: a new user who had not imported anything typed `@prototype` in the body and saw
 * "No records related to 'prototype' found in the knowledge base" -- sounding like the word was wrong, so they would try other words
 * again, empty however many times. (The same trap in the writing loop was fixed in round 676.)
 */
const recall = vi.fn()
vi.mock('../../api', () => ({ recall: (q: string, n: number) => recall(q, n) }))

const { recallSource } = await import('../recallCompletion')

function ctx(text: string) {
  return {
    aborted: false,
    matchBefore: (re: RegExp) => {
      const m = re.exec(text)
      return m ? { from: text.length - m[0].length, to: text.length, text: m[0] } : null
    },
  } as never
}

describe('what @ citation says when nothing is found', () => {
  it('empty library: suggest importing, not rewording', async () => {
    recall.mockResolvedValue({ facts: [], took_ms: 1, terms: [], kb_empty: true })
    const r = await recallSource(ctx('Writing here @prototype'))
    expect(r!.options[0].label).toContain('The knowledge base is still empty')
    expect(r!.options[0].label).toContain('import')
    expect(r!.options[0].label).not.toContain('prototype')
  })

  it('the library has content, just no hit this time: say that word was not found, as before', async () => {
    recall.mockResolvedValue({ facts: [], took_ms: 1, terms: [], kb_empty: false })
    const r = await recallSource(ctx('Writing here @prototype'))
    expect(r!.options[0].label).toContain('prototype')
    expect(r!.options[0].label).not.toContain('empty')
  })

  it('when the backend does not give this field (old version), go with "not found", never wrongly claiming the library is empty', async () => {
    recall.mockResolvedValue({ facts: [], took_ms: 1, terms: [] })
    const r = await recallSource(ctx('Writing here @prototype'))
    expect(r!.options[0].label).toContain('prototype')
  })

  it('when something is found, give candidates as usual', async () => {
    recall.mockResolvedValue({
      facts: [{ id: 'f1', text: 'The prototype battery lasted 11 hours in testing.', when: '2026-03-04', sources: [] }],
      took_ms: 1, terms: [], kb_empty: false,
    })
    const r = await recallSource(ctx('Writing here @prototype'))
    expect(r!.options).toHaveLength(1)
    expect(r!.options[0].label).toContain('battery')
  })
})
