// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const calls = vi.hoisted(() => ({ save: vi.fn(), download: vi.fn(), toast: vi.fn(), action: vi.fn() }))
vi.mock('../../util/markdownExport', () => ({ downloadLibrary: calls.download, downloadMarkdown: vi.fn() }))
vi.mock('../../api', async () => ({
  ...await vi.importActual<Record<string, unknown>>('../../api'),
  saveNote: calls.save,
}))
vi.mock('../../toast', () => ({ toast: calls.toast, toastAction: calls.action }))
vi.mock('../Toaster', () => ({ default: () => null }))
vi.mock('../RightPane', () => ({ default: () => null }))
vi.mock('../MarkdownEditor', () => ({ default: ({ content, onChange }: { content: string; onChange: (text: string) => void }) =>
  <textarea aria-label="Note body" value={content} onChange={e => onChange(e.target.value)} /> }))

import App from '../../App'
import type { Note } from '../../api'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const note: Note = { id: 'fictional-maple', user_id: 'export-test', title: 'Maple report', content: 'Earlier draft.', pinned: false, spine: '', beats: [], created_at: '2026-11-09T10:00:00Z', updated_at: '2026-11-09T10:00:00Z' }
const splitNote: Note = { ...note, id: 'fictional-cedar', title: 'Cedar report' }
let host: HTMLDivElement
let root: Root
beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('memoket-note-user', 'export-test')
  calls.save.mockReset().mockImplementation(async (id: string, title: string, content: string) => ({ ...note, id, title, content }))
  calls.download.mockReset(); calls.toast.mockReset(); calls.action.mockReset()
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  HTMLElement.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('fetch', vi.fn(async (input: string) => {
    const path = String(input).split('?')[0]
    const body = path === '/api/notes' ? [note, splitNote] : path === '/api/health' ? { llm: { ok: true }, asr: { ok: false } }
      : path.endsWith('/writing-feedback') ? null : []
    return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  }))
})
afterEach(async () => {
  await act(async () => { root?.unmount() })
  host?.remove(); vi.unstubAllGlobals(); vi.useRealTimers()
})
async function mount() {
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => { root.render(<App />) })
}
async function edit(text: string, split = false) {
  const input = host.querySelector<HTMLTextAreaElement>(split ? '.split-body textarea' : '[aria-label="Note body"]')!
  expect(input).not.toBeNull()
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(input, text)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
async function exportAll() {
  await act(async () => { window.dispatchEvent(new CustomEvent('export-all')) })
}

it('saves the latest editor body before exporting within the autosave delay', async () => {
  await mount(); await edit('The fictional Maple launch is ready.')
  await exportAll()
  expect(calls.save).toHaveBeenCalledWith(note.id, note.title, 'The fictional Maple launch is ready.')
  expect(calls.download).toHaveBeenCalledWith('export-test')
})

it('waits for saving and ignores duplicate export requests', async () => {
  await mount(); await edit('Ready for the amber launch.')
  let release!: (value: Note) => void
  calls.save.mockReturnValueOnce(new Promise<Note>(resolve => { release = resolve }))
  await exportAll(); await exportAll()
  expect(calls.download).not.toHaveBeenCalled()
  expect(calls.save).toHaveBeenCalledTimes(1)
  expect(host.querySelector('[role="status"]')?.textContent).toBe('Saving open notes before export…')
  await act(async () => { release({ ...note, content: 'Ready for the amber launch.' }) })
  expect(calls.download).toHaveBeenCalledTimes(1)
  expect(host.querySelector('[role="status"]')).toBeNull()
})

it('cancels on save failure and retries with the current draft', async () => {
  await mount(); await edit('First export attempt.')
  calls.save.mockRejectedValueOnce(new Error('Fictional disk is full'))
  await exportAll()
  expect(calls.download).not.toHaveBeenCalled()
  expect(calls.action).toHaveBeenCalledWith(expect.stringContaining('Export cancelled:'), 'Retry export', expect.any(Function), 15000, 'error')
  await edit('Updated after the failed save.')
  await act(async () => { calls.action.mock.calls[0][2]() })
  expect(calls.save).toHaveBeenLastCalledWith(note.id, note.title, 'Updated after the failed save.')
  expect(calls.download).toHaveBeenCalledTimes(1)
})

it('queues the export save after an older in-flight save', async () => {
  await mount(); await edit('An earlier edit is being saved.')
  let release!: (value: Note) => void
  calls.save.mockReturnValueOnce(new Promise<Note>(resolve => { release = resolve }))
  await act(async () => { window.dispatchEvent(new KeyboardEvent('keydown', { key: 's', ctrlKey: true })) })
  await edit('A newer edit belongs in the archive.')
  await exportAll()
  expect(calls.save).toHaveBeenCalledTimes(1)
  expect(calls.download).not.toHaveBeenCalled()
  await act(async () => { release({ ...note, content: 'An earlier edit is being saved.' }) })
  expect(calls.save).toHaveBeenLastCalledWith(note.id, note.title, 'A newer edit belongs in the archive.')
  expect(calls.download).toHaveBeenCalledTimes(1)
})

it('preserves an intentional return to the initial text while saving', async () => {
  await mount(); await edit('A change that will be undone.')
  let release!: (value: Note) => void
  calls.save.mockReturnValueOnce(new Promise<Note>(resolve => { release = resolve }))
  await act(async () => { window.dispatchEvent(new KeyboardEvent('keydown', { key: 's', ctrlKey: true })) })
  await edit(note.content); await exportAll()
  await act(async () => { release({ ...note, content: 'A change that will be undone.' }) })
  expect(calls.save).toHaveBeenLastCalledWith(note.id, note.title, note.content)
  expect(calls.download).toHaveBeenCalledTimes(1)
})

it('exports an already saved library without writing the note again', async () => {
  await mount(); await exportAll()
  expect(calls.save).not.toHaveBeenCalled()
  expect(calls.download).toHaveBeenCalledTimes(1)
})

it('flushes a split-pane draft and stops when it cannot be saved', async () => {
  localStorage.setItem('memoket-note-split:export-test', JSON.stringify({ id: splitNote.id, w: 420 }))
  await mount(); await edit('Cedar uses violet labels.', true)
  calls.save.mockRejectedValueOnce(new Error('Fictional split save failure'))
  await exportAll()
  expect(calls.save).toHaveBeenCalledWith(splitNote.id, splitNote.title, 'Cedar uses violet labels.')
  expect(calls.download).not.toHaveBeenCalled()
  expect(calls.action).toHaveBeenCalledWith(expect.stringContaining('Export cancelled:'), 'Retry export', expect.any(Function), 15000, 'error')
  await exportAll()
  expect(calls.download).toHaveBeenCalledTimes(1)
})

it('includes a newly typed title and waits for the split save too', async () => {
  localStorage.setItem('memoket-note-split:export-test', JSON.stringify({ id: splitNote.id, w: 420 }))
  await mount()
  const title = host.querySelector<HTMLInputElement>('[aria-label="Note title"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(title, 'Maple launch review')
    title.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await edit('Cedar uses silver labels.', true)
  let release!: (value: Note) => void
  calls.save.mockResolvedValueOnce({ ...note, title: 'Maple launch review' })
    .mockReturnValueOnce(new Promise<Note>(resolve => { release = resolve }))
  await exportAll()
  expect(calls.save).toHaveBeenNthCalledWith(1, note.id, 'Maple launch review', note.content)
  expect(calls.save).toHaveBeenNthCalledWith(2, splitNote.id, splitNote.title, 'Cedar uses silver labels.')
  expect(calls.download).not.toHaveBeenCalled()
  await act(async () => { release({ ...splitNote, content: 'Cedar uses silver labels.' }) })
  expect(calls.download).toHaveBeenCalledTimes(1)
})

it('does not start a download when the workspace unmounts during a save', async () => {
  await mount(); await edit('A pending Maple draft.')
  let release!: (value: Note) => void
  calls.save.mockReturnValueOnce(new Promise<Note>(resolve => { release = resolve }))
  await exportAll()
  await act(async () => { root.unmount() })
  await act(async () => { release({ ...note, content: 'A pending Maple draft.' }) })
  expect(calls.download).not.toHaveBeenCalled()
})

it.each([false, true])('waits for a saving note after its last tab closes (failure: %s)', async (fail) => {
  await mount(); await edit('The closing Maple draft.')
  let release!: (value: Note) => void
  let reject!: (error: Error) => void
  calls.save.mockReturnValueOnce(new Promise<Note>((resolve, failure) => { release = resolve; reject = failure }))
  await act(async () => { window.dispatchEvent(new KeyboardEvent('keydown', { key: 's', ctrlKey: true })) })
  await act(async () => { window.dispatchEvent(new CustomEvent('tab-action', { detail: 'close' })) })
  await exportAll()
  expect(calls.download).not.toHaveBeenCalled()
  await act(async () => {
    if (fail) reject(new Error('Fictional closing-note save failure'))
    else release({ ...note, content: 'The closing Maple draft.' })
  })
  expect(calls.download).toHaveBeenCalledTimes(fail ? 0 : 1)
  if (fail) {
    expect(calls.action).toHaveBeenCalledWith(expect.stringContaining('Export cancelled:'), 'Retry export', expect.any(Function), 15000, 'error')
    await act(async () => { calls.action.mock.calls[0][2]() })
    expect(calls.save).toHaveBeenLastCalledWith(note.id, note.title, 'The closing Maple draft.')
    expect(calls.download).toHaveBeenCalledTimes(1)
  }
})
