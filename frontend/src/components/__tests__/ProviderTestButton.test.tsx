// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'
import { testProvider, type ProviderTest, type ProviderTestRequest } from '../../api'
import { setLang } from '../../i18n'
import ProviderTestButton from '../ProviderTestButton'

vi.mock('../../api', () => ({ testProvider: vi.fn() }))
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const request: ProviderTestRequest = { kind: 'llm', provider: 'local', base_url: 'http://127.0.0.1:18001/v1', model: 'maple-writer' }
const result: ProviderTest = { ok: true, message: 'Fictional service connected', models: ['maple-writer'], model_found: true, elapsed_ms: 4 }
let root: Root | null = null
let element: HTMLDivElement | null = null

afterEach(async () => {
  if (root) await act(async () => { root!.unmount() })
  element?.remove(); element = null; root = null
  vi.resetAllMocks(); vi.useRealTimers(); setLang('en')
})

async function render(body = request, credentialRevision = '') {
  if (!element) {
    element = document.createElement('div'); document.body.append(element)
    root = createRoot(element)
  }
  await act(async () => {
    root!.render(<ProviderTestButton request={body} credentialRevision={credentialRevision} onPick={() => {}} />)
  })
  return element
}

async function test() {
  await act(async () => { element!.querySelector<HTMLButtonElement>('.chip-action')!.click() })
}

it.each([
  ['endpoint', { base_url: 'http://127.0.0.1:18002/v1' }],
  ['model', { model: 'amber-writer' }],
  ['provider', { provider: 'gpt' }],
  ['draft key', { api_key: 'fictional-key-b' }],
  ['saved credential slot', { saved_key_of: 'vision' }],
  ['voice region', { region: 'eu' }],
])('discards the result and model list after changing %s', async (_name, patch) => {
  vi.mocked(testProvider).mockResolvedValue(result)
  const el = await render()
  await test()
  expect(el.textContent).toContain(result.message)
  await render({ ...request, ...patch })
  expect(el.textContent).not.toContain(result.message)
  expect(el.querySelector('[aria-label="Available models"]')).toBeNull()
  expect(el.textContent).toContain('Settings changed. Test again')
})

it('keeps a result on unrelated rerenders, but invalidates changed saved credentials', async () => {
  vi.mocked(testProvider).mockResolvedValue(result)
  const el = await render(request, 'key-saved-a')
  await test()
  await render({ ...request }, 'key-saved-a')
  expect(el.textContent).toContain(result.message)
  await render({ ...request }, 'key-cleared')
  expect(el.textContent).not.toContain(result.message)
})

it('aborts an old test and ignores its late success while a newer test is running', async () => {
  let oldResolve!: (value: ProviderTest) => void
  let newResolve!: (value: ProviderTest) => void
  vi.mocked(testProvider).mockReturnValueOnce(new Promise((resolve) => { oldResolve = resolve }))
    .mockReturnValueOnce(new Promise((resolve) => { newResolve = resolve }))
  const el = await render()
  await test()
  const oldSignal = vi.mocked(testProvider).mock.calls[0][1]!
  await render({ ...request, base_url: 'http://127.0.0.1:18002/v1' })
  expect(oldSignal.aborted).toBe(true)
  expect(el.querySelector<HTMLButtonElement>('.chip-action')!.disabled).toBe(false)
  await test()
  await act(async () => { oldResolve(result) })
  expect(el.textContent).not.toContain(result.message)
  expect(el.querySelector<HTMLButtonElement>('.chip-action')!.disabled).toBe(true)
  await act(async () => { newResolve({ ...result, message: 'Current service connected' }) })
  expect(el.textContent).toContain('Current service connected')
})

it('bounds a hanging request, offers retry and ignores a response after timeout', async () => {
  vi.useFakeTimers()
  let resolve!: (value: ProviderTest) => void
  vi.mocked(testProvider).mockReturnValueOnce(new Promise((done) => { resolve = done }))
    .mockResolvedValueOnce({ ...result, message: 'Retry connected' })
  const el = await render()
  await test()
  await act(async () => { vi.advanceTimersByTime(45_000) })
  expect(el.textContent).toContain('Connection test timed out.')
  expect(vi.mocked(testProvider).mock.calls[0][1]!.aborted).toBe(true)
  await test()
  await act(async () => { resolve(result) })
  expect(el.textContent).toContain('Retry connected')
  expect(el.textContent).not.toContain(result.message)
})

it('aborts and clears waiting work on unmount', async () => {
  vi.useFakeTimers()
  vi.mocked(testProvider).mockReturnValue(new Promise(() => {}))
  await render()
  await test()
  const signal = vi.mocked(testProvider).mock.calls[0][1]!
  await act(async () => { root!.unmount(); root = null })
  expect(signal.aborted).toBe(true)
  expect(vi.getTimerCount()).toBe(0)
})

it('does not include a supplied key in markup or the model list', async () => {
  vi.mocked(testProvider).mockResolvedValue(result)
  const el = await render({ ...request, api_key: 'fictional-private-key-value' })
  await test()
  expect(el.outerHTML).not.toContain('fictional-private-key-value')
  expect(vi.mocked(testProvider).mock.calls[0][0].api_key).toBe('fictional-private-key-value')
  expect(el.querySelector('li button')?.getAttribute('aria-pressed')).toBe('true')
})

it('announces invalidated results in the selected UI language', async () => {
  setLang('zh')
  vi.mocked(testProvider).mockResolvedValue(result)
  const el = await render()
  await test()
  await render({ ...request, model: 'amber-writer' })
  expect(el.textContent).toContain('\u8bbe\u7f6e\u5df2\u66f4\u6539')
})
