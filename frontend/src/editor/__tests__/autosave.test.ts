import { describe, expect, it, vi } from 'vitest'
import { createAutosave } from '../../util/autosave'

describe('createAutosave', () => {
  it('after typing stops only the last version is saved', async () => {
    vi.useFakeTimers()
    const save = vi.fn(async () => {})
    const a = createAutosave({ delay: 500, save })
    a.change('a'); a.change('ab'); a.change('abc')
    expect(a.dirty()).toBe(true)
    await vi.advanceTimersByTimeAsync(499)
    expect(save).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(save).toHaveBeenCalledTimes(1)
    expect(save).toHaveBeenCalledWith('abc')
    expect(a.dirty()).toBe(false)
    vi.useRealTimers()
  })

  it('changed again while saving: save again right after, never concurrently', async () => {
    vi.useFakeTimers()
    let release: () => void = () => {}
    const calls: string[] = []
    const save = vi.fn((c: string) => { calls.push(c); return new Promise<void>((r) => { release = r }) })
    const a = createAutosave({ delay: 100, save })
    a.change('v1')
    await vi.advanceTimersByTimeAsync(100)
    expect(calls).toEqual(['v1'])
    a.change('v2')
    await vi.advanceTimersByTimeAsync(100)
    expect(calls).toEqual(['v1'])          // v1 has not come back yet, v2 is queued
    release()
    await vi.advanceTimersByTimeAsync(0)
    expect(calls).toEqual(['v1', 'v2'])
    release()
    await vi.advanceTimersByTimeAsync(0)
    expect(a.dirty()).toBe(false)
    vi.useRealTimers()
  })

  it('flush saves immediately; dispose drops what is unsaved', async () => {
    vi.useFakeTimers()
    const save = vi.fn(async () => {})
    const a = createAutosave({ delay: 10_000, save })
    a.change('x')
    await a.flush()
    expect(save).toHaveBeenCalledWith('x')
    const b = createAutosave({ delay: 10_000, save })
    b.change('y'); b.dispose()
    await vi.advanceTimersByTimeAsync(20_000)
    expect(save).toHaveBeenCalledTimes(1)
    expect(b.dirty()).toBe(false)
    vi.useRealTimers()
  })

  it('save fails: report it, keep the content, retry on the next change', async () => {
    vi.useFakeTimers()
    let fail = true
    const save = vi.fn(async () => { if (fail) throw new Error('boom') })
    const onError = vi.fn()
    const a = createAutosave({ delay: 100, save, onError })
    a.change('z')
    await vi.advanceTimersByTimeAsync(100)
    expect(onError).toHaveBeenCalledTimes(1)
    expect(a.dirty()).toBe(true)
    await vi.advanceTimersByTimeAsync(5_000)
    expect(save).toHaveBeenCalledTimes(1)     // no automatic retry
    fail = false
    a.change('z2')
    await vi.advanceTimersByTimeAsync(100)
    expect(save).toHaveBeenLastCalledWith('z2')
    expect(a.dirty()).toBe(false)
    vi.useRealTimers()
  })

  it('explicit flush rejects a failed save and keeps it available for retry', async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error('Fictional write failure')).mockResolvedValue(undefined)
    const a = createAutosave({ delay: 10_000, save })
    a.change('The Cedar draft.')
    await expect(a.flush()).rejects.toThrow('Fictional write failure')
    expect(a.dirty()).toBe(true)
    await a.flush()
    expect(save).toHaveBeenLastCalledWith('The Cedar draft.')
    expect(a.dirty()).toBe(false)
    a.dispose()
  })

  it('flush joins an in-flight autosave and reports its failure', async () => {
    vi.useFakeTimers()
    let reject!: (error: Error) => void
    const a = createAutosave({ delay: 100, save: () => new Promise<void>((_resolve, fail) => { reject = fail }) })
    a.change('In-flight Cedar draft.')
    await vi.advanceTimersByTimeAsync(100)
    const flushed = expect(a.flush()).rejects.toThrow('Fictional delayed failure')
    reject(new Error('Fictional delayed failure'))
    await flushed
    expect(a.dirty()).toBe(true)
    a.dispose(); vi.useRealTimers()
  })
})
