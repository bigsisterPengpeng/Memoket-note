// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import { appleAvailable, memoketAvailable, memoketImport, memoketRead } from '../../api'
import { setLang } from '../../i18n'
import AppleNotesImport from '../AppleNotesImport'
import MemoketImport from '../MemoketImport'

vi.mock('../../api', () => ({
  appleAvailable: vi.fn(), memoketAvailable: vi.fn(), memoketRead: vi.fn(), memoketImport: vi.fn(),
}))

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
let root: Root | null = null
let element: HTMLDivElement | null = null

afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  element?.remove(); element = null; root = null
  vi.resetAllMocks(); vi.useRealTimers(); setLang('en')
})

async function mount(content: React.ReactNode) {
  element = document.createElement('div'); document.body.append(element)
  root = createRoot(element)
  await act(async () => { root!.render(content) })
  return element
}

function button(label: string) {
  return [...element!.querySelectorAll('button')].find((candidate) => candidate.textContent === label)!
}

async function fill(label: string, value: string) {
  const input = element!.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

it('shows an unavailable Apple Notes reason and prevents import', async () => {
  vi.mocked(appleAvailable).mockResolvedValue({ available: false, reason: 'Apple Notes requires macOS.' })
  const onImport = vi.fn()
  const el = await mount(<AppleNotesImport disabled={false} onImport={onImport} />)
  expect(el.querySelector('[role="status"]')?.textContent).toBe('Apple Notes requires macOS.')
  expect(button('Import all notes').disabled).toBe(true)
  await act(async () => { button('Import all notes').click() })
  expect(onImport).not.toHaveBeenCalled()
})

it('turns a failed check into an explicit error and retries without reloading', async () => {
  vi.mocked(appleAvailable).mockRejectedValueOnce(new Error('503 offline'))
    .mockResolvedValueOnce({ available: true, reason: '' })
  const onImport = vi.fn()
  const el = await mount(<AppleNotesImport disabled={false} onImport={onImport} />)
  expect(el.textContent).toContain('Could not check Apple Notes.')
  expect(el.textContent).not.toContain('Checking')
  expect(button('Import all notes').disabled).toBe(true)
  await act(async () => { button('Check again').click() })
  expect(button('Import all notes').disabled).toBe(false)
  expect(el.textContent).toContain('macOS shows an "allow to control Notes" permission prompt')
  await act(async () => { button('Import all notes').click() })
  expect(onImport).toHaveBeenCalledOnce()
})

it('times out a hanging check, aborts it and ignores its late response', async () => {
  vi.useFakeTimers()
  let resolve!: (value: { available: boolean; reason: string }) => void
  vi.mocked(memoketAvailable).mockReturnValueOnce(new Promise((done) => { resolve = done }))
    .mockResolvedValueOnce({ available: true, reason: '' })
  const el = await mount(<MemoketImport to="notes" disabled={false} onImported={() => {}} />)
  expect(el.textContent).toContain('Checking Memoket CLI availability')
  expect(el.querySelector('fieldset')?.disabled).toBe(true)
  await act(async () => { vi.advanceTimersByTime(8000) })
  expect(el.textContent).toContain('Could not check Memoket CLI.')
  expect(vi.mocked(memoketAvailable).mock.calls[0][0]?.aborted).toBe(true)
  await act(async () => { button('Check again').click() })
  expect(el.querySelector('fieldset')?.disabled).toBe(false)
  await act(async () => { resolve({ available: false, reason: 'An obsolete response' }) })
  expect(el.querySelector('fieldset')?.disabled).toBe(false)
  expect(el.textContent).not.toContain('An obsolete response')
})

it('keeps Memoket actions disabled while the CLI is missing', async () => {
  vi.mocked(memoketAvailable).mockResolvedValue({ available: false, reason: 'Install the official CLI.' })
  const el = await mount(<MemoketImport to="notes" disabled={false} onImported={() => {}} />)
  expect(el.textContent).toContain('Install the official CLI.')
  expect(el.textContent).toContain('A Docker workspace cannot use your host Memoket login.')
  expect(button('Search recordings').matches(':disabled')).toBe(true)
  expect(button('Import selected brief').matches(':disabled')).toBe(true)
  await act(async () => { button('Search recordings').click(); button('Import selected brief').click() })
  expect(memoketRead).not.toHaveBeenCalled()
  expect(memoketImport).not.toHaveBeenCalled()
})

it('clears a previous recording selection when starting a new search', async () => {
  vi.mocked(memoketAvailable).mockResolvedValue({ available: true, reason: '' })
  vi.mocked(memoketRead).mockResolvedValue({ items: [{ conversation_id: 'maple-1', title: 'Maple rehearsal' }] })
  const el = await mount(<MemoketImport to="notes" disabled={false} onImported={() => {}} />)
  await fill('Search Memoket recordings', 'Maple')
  await act(async () => { button('Search recordings').click() })
  await act(async () => { el.querySelector<HTMLButtonElement>('.memoket-matches button')!.click() })
  expect(button('Import selected brief').disabled).toBe(false)
  await fill('Search Memoket recordings', 'Amber')
  await act(async () => { button('Search recordings').click() })
  expect(el.querySelector<HTMLInputElement>('input[aria-label="Memoket conversation ID"]')?.value).toBe('')
  expect(button('Import selected brief').disabled).toBe(true)
})

it('aborts availability checks on unmount', async () => {
  vi.mocked(appleAvailable).mockReturnValue(new Promise(() => {}))
  await mount(<AppleNotesImport disabled={false} onImport={() => {}} />)
  const signal = vi.mocked(appleAvailable).mock.calls[0][0]!
  await act(async () => { root!.unmount(); root = null })
  expect(signal.aborted).toBe(true)
})

it('announces connection errors in the selected UI language', async () => {
  setLang('zh')
  vi.mocked(appleAvailable).mockRejectedValue(new Error('503 offline'))
  const el = await mount(<AppleNotesImport disabled={false} onImport={() => {}} />)
  expect(el.querySelector('[role="status"]')?.textContent).toContain('\u65e0\u6cd5\u68c0\u67e5')
})
