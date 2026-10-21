// @vitest-environment jsdom
/**
 * Settings > "Writing model": provider dropdown (cloud / local / custom groups) + one set of three fields per
 * provider.
 *
 *  - **every preset** is in the dropdown, grouped by `group`;
 *  - switching providers swaps the address placeholder / model suggestion list to that provider's;
 *  - key field: key-requiring providers show the `sk-...` placeholder and a red notice while no key is saved;
 *    providers with a saved key show the last four chars + "Clear saved key"; local servers keep the field
 *    but say it is optional;
 *  - **switching away and back keeps what was typed** (drafts are kept per provider);
 *  - save posts the selected provider's `provider / base_url / model`, **without** `api_key` when the field is
 *    blank (sending it would clear the saved key).
 *
 * The backend half (registry, per-provider credentials, family -> request body) is `backend/tests/test_providers.py`.
 */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProviderConfig, ProviderPreset } from '../../api'

const preset = (over: Partial<ProviderPreset> & Pick<ProviderPreset, 'id' | 'label' | 'base_url' | 'group'>): ProviderPreset => ({
  models: [], needs_key: true, family: 'compatible', docs: '', key_set: false, key_preview: '', model: '', base_url_saved: '', ...over,
})

const PRESETS: ProviderPreset[] = [
  preset({ id: 'openai', label: 'OpenAI', base_url: 'https://api.openai.com/v1', group: 'hosted', family: 'openai', models: ['gpt-6-luna', 'gpt-6.1-sol'] }),
  preset({ id: 'deepseek', label: 'DeepSeek', base_url: 'https://api.deepseek.com', group: 'hosted', models: ['deepseek-flash', 'deepseek-v4-pro'],
           key_set: true, key_preview: '...1234', model: 'deepseek-flash' }),
  preset({ id: 'ollama', label: 'Ollama', base_url: 'http://127.0.0.1:11434/v1', group: 'local', family: 'local', needs_key: false, models: ['qwen3:8b'] }),
  preset({ id: 'local', label: 'Local / self-hosted (custom address)', base_url: 'http://127.0.0.1:11434/v1', group: 'local', family: 'local', needs_key: false }),
  preset({ id: 'gpt', label: 'Custom OpenAI-compatible endpoint', base_url: 'https://api.openai.com/v1', group: 'custom', family: 'openai', model: 'gpt-4.1-mini', base_url_saved: 'https://api.openai.com/v1' }),
]

const CFG: ProviderConfig = {
  provider: 'ollama', providers: PRESETS, active_provider: 'local', active_family: 'local',
  gpt_model: 'gpt-4.1-mini', gpt_base_url: 'https://api.openai.com/v1', gpt_api_key_set: false, gpt_api_key_preview: '',
  asr_provider: 'whisper', assemblyai_api_key_set: false, assemblyai_api_key_preview: '', assemblyai_region: 'us',
  speechmatics_api_key_set: false, speechmatics_api_key_preview: '', speechmatics_region: 'eu',
  asr_base_url: '', asr_default_url: 'http://127.0.0.1:8081',
  vision_base_url: '', vision_model: '', vision_api_key_set: false, vision_follows_llm: true, vision_active_url: '', vision_active_model: '',
  local_base_url: '', local_model: '', local_api_key_set: false, local_default_url: 'http://127.0.0.1:11434/v1', local_default_model: '',
  configured: false, configured_source: 'default', active_url: 'http://127.0.0.1:11434/v1', active_model: '', auto_sync_notes: false,
}

const posted: Record<string, unknown>[] = []

vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api')
  return {
    ...actual,
    getProviderConfig: () => Promise.resolve(CFG),
    setProviderConfig: (body: Record<string, unknown>) => {
      posted.push(body)
      return Promise.resolve({ ...CFG, provider: body.provider as string, active_provider: body.provider as string, configured: true })
    },
    testProvider: () => Promise.resolve({ ok: true, message: 'ok', models: [], model_found: null, elapsed_ms: 1 }),
  }
})

const { default: SettingsPanel } = await import('../SettingsPanel')

async function mount() {
  const el = document.createElement('div')
  document.body.append(el)
  const root = createRoot(el)
  await act(async () => { root.render(<SettingsPanel onClose={() => {}} />) })
  await act(async () => { await new Promise((r) => setTimeout(r, 20)) })
  return el
}

/** Controlled inputs: go through the native value setter and dispatch `input` so React treats it as typing. */
function type(input: HTMLInputElement, value: string) {
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  set.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}
function choose(select: HTMLSelectElement, value: string) {
  const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!
  set.call(select, value)
  select.dispatchEvent(new Event('change', { bubbles: true }))
}

const q = <T extends Element>(el: Element, sel: string) => el.querySelector(sel) as T

afterEach(() => { document.body.innerHTML = ''; posted.length = 0 })

describe('provider dropdown', () => {
  it('lists every preset, grouped cloud / local / custom, with the saved provider selected', async () => {
    const el = await mount()
    const select = q<HTMLSelectElement>(el, '#provider-select')
    expect(select).toBeTruthy()
    expect([...select.options].map((o) => o.value)).toEqual(PRESETS.map((p) => p.id))
    expect([...select.querySelectorAll('optgroup')].map((g) => g.label)).toEqual(['Cloud services', 'Local / self-hosted', 'Custom'])
    expect(select.value).toBe('ollama')
    // a provider with a saved key gets a check mark on its option
    expect([...select.options].find((o) => o.value === 'deepseek')!.textContent).toContain('✓')
  })

  it('switching providers swaps the address placeholder and the model suggestions', async () => {
    const el = await mount()
    expect(q<HTMLInputElement>(el, '#provider-base-url').placeholder).toContain('http://127.0.0.1:11434/v1')
    expect([...el.querySelectorAll('#provider-model-suggestions option')].map((o) => (o as HTMLOptionElement).value)).toEqual(['qwen3:8b'])
    await act(async () => { choose(q(el, '#provider-select'), 'openai') })
    expect(q<HTMLInputElement>(el, '#provider-base-url').placeholder).toContain('https://api.openai.com/v1')
    expect([...el.querySelectorAll('#provider-model-suggestions option')].map((o) => (o as HTMLOptionElement).value)).toEqual(['gpt-6-luna', 'gpt-6.1-sol'])
    expect(q<HTMLInputElement>(el, '#provider-model').placeholder).toContain('gpt-6-luna')
  })

  it('key field: notice when a required key is missing; saved key shows its tail + clear button; local says optional', async () => {
    const el = await mount()
    // Ollama: the field exists, but the label says it is usually not needed; no red notice
    expect(el.textContent).toContain('API key (usually not needed locally)')
    expect(el.textContent).not.toContain('No API key set')
    await act(async () => { choose(q(el, '#provider-select'), 'openai') })
    expect(q<HTMLInputElement>(el, '#provider-api-key').placeholder).toBe('sk-...')
    expect(el.textContent).toContain('No API key set')
    expect(el.textContent).not.toContain('Clear saved key')
    await act(async () => { choose(q(el, '#provider-select'), 'deepseek') })
    expect(q<HTMLInputElement>(el, '#provider-api-key').placeholder).toContain('...1234')
    expect(el.textContent).toContain('Clear saved key')
    expect(el.textContent).not.toContain('No API key set')
    // the saved model / address of this provider are filled in
    expect(q<HTMLInputElement>(el, '#provider-model').value).toBe('deepseek-flash')
  })

  it('switching away and back keeps what was typed', async () => {
    const el = await mount()
    await act(async () => { choose(q(el, '#provider-select'), 'openai') })
    await act(async () => { type(q(el, '#provider-model'), 'gpt-6.1-sol') })
    await act(async () => { type(q(el, '#provider-base-url'), 'https://gw.example/v1') })
    await act(async () => { choose(q(el, '#provider-select'), 'deepseek') })
    expect(q<HTMLInputElement>(el, '#provider-model').value).toBe('deepseek-flash')
    await act(async () => { choose(q(el, '#provider-select'), 'openai') })
    expect(q<HTMLInputElement>(el, '#provider-model').value).toBe('gpt-6.1-sol')
    expect(q<HTMLInputElement>(el, '#provider-base-url').value).toBe('https://gw.example/v1')
  })

  it('save posts the selected provider / base_url / model; no api_key when the field is blank (it would clear the key)', async () => {
    const el = await mount()
    await act(async () => { choose(q(el, '#provider-select'), 'openai') })
    await act(async () => { type(q(el, '#provider-model'), 'gpt-6-luna') })
    const save = [...el.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Save')!
    await act(async () => { save.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 20)) })
    expect(posted).toHaveLength(1)
    expect(posted[0]).toMatchObject({ provider: 'openai', model: 'gpt-6-luna', base_url: '', vision_base_url: '', vision_model: '' })
    expect(posted[0]).not.toHaveProperty('api_key')
    // the key is sent only when typed
    await act(async () => { type(q(el, '#provider-api-key'), 'sk-new') })
    await act(async () => { save.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 20)) })
    expect(posted[1]).toMatchObject({ provider: 'openai', api_key: 'sk-new' })
  })

  it('a provider edited but not selected is stored too (the API takes one provider per call)', async () => {
    const el = await mount()
    await act(async () => { choose(q(el, '#provider-select'), 'openai') })
    await act(async () => { type(q(el, '#provider-model'), 'gpt-6-luna') })
    await act(async () => { choose(q(el, '#provider-select'), 'ollama') })
    const save = [...el.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Save')!
    await act(async () => { save.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 20)) })
    expect(posted.map((p) => p.provider)).toEqual(['openai', 'ollama'])
    expect(posted[0]).toMatchObject({ provider: 'openai', model: 'gpt-6-luna' })
    expect(posted[0]).not.toHaveProperty('asr_base_url')      // other providers store the three fields only; voice / vision ride with the last call
  })
})
