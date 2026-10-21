import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it } from 'vitest'
import type { ProviderConfig } from '../../api'
import { setLang } from '../../i18n'
import VoiceSettings, { EMPTY_VOICE_DRAFT, voiceBody, voiceDraftFrom } from '../VoiceSettings'
import { friendlyError } from '../../util/friendlyError'

const cfg = {
  asr_base_url: '', asr_default_url: 'http://127.0.0.1:8081',
  asr_provider: 'speechmatics',
  assemblyai_api_key_set: false, assemblyai_api_key_preview: '', assemblyai_region: 'eu',
  speechmatics_api_key_set: true, speechmatics_api_key_preview: '...abcd', speechmatics_region: 'us',
} as unknown as ProviderConfig

const render = (draft = voiceDraftFrom(cfg), c: ProviderConfig | null = cfg) =>
  renderToStaticMarkup(createElement(VoiceSettings, { cfg: c, value: draft, onChange: () => {} }))

afterEach(() => setLang('en'))

describe('VoiceSettings', () => {
  it('draft comes from the saved config, key fields start empty', () => {
    const d = voiceDraftFrom(cfg)
    expect(d).toEqual({ ...EMPTY_VOICE_DRAFT, asr_provider: 'speechmatics', assemblyai_region: 'eu', speechmatics_region: 'us' })
  })

  it('save body never sends a blank key (that would clear the saved one)', () => {
    const body = voiceBody({ ...voiceDraftFrom(cfg), speechmatics_api_key: '   ' })
    expect(body).not.toHaveProperty('speechmatics_api_key')
    expect(body).not.toHaveProperty('assemblyai_api_key')
    expect(body).toMatchObject({ asr_provider: 'speechmatics', asr_base_url: '', speechmatics_region: 'us' })
    expect(voiceBody({ ...EMPTY_VOICE_DRAFT, assemblyai_api_key: ' k1 ' }).assemblyai_api_key).toBe('k1')
  })

  it('hosted provider shows key-set indicator, region and test button; no whisper address', () => {
    const html = render()
    expect(html).toContain('Speechmatics API key')
    expect(html).toContain('Set ...abcd; leave empty to keep it')
    expect(html).toContain('An API key is saved.')
    expect(html).toContain('Speechmatics region')
    expect(html).not.toContain('Voice service address')
    expect(html).not.toContain('abcd-full-key')
  })

  it('missing key: warns and disables the test button', () => {
    const html = render({ ...voiceDraftFrom(cfg), asr_provider: 'assemblyai' })
    expect(html).toContain('No API key yet')
    expect(html).toMatch(/<button[^>]*disabled[^>]*title="Paste an API key first"/)
  })

  it('whisper shows the address with the .env default as placeholder', () => {
    const html = render({ ...EMPTY_VOICE_DRAFT })
    expect(html).toContain('aria-label="Voice service address"')
    expect(html).toContain('Default http://127.0.0.1:8081')
  })

  it('Chinese UI comes from the voice shard', () => {
    setLang('zh')
    const html = render({ ...EMPTY_VOICE_DRAFT })
    expect(html).toContain('aria-label="\u8bed\u97f3\u670d\u52a1\u5730\u5740"')   // "voice service address"
  })

  it('backend voice sentences pass through friendlyError unchanged', () => {
    for (const m of [
      'AssemblyAI rejected the API key (401) - check the key in Settings',
      'The voice service at http://h timed out - transcription did not finish, try again later',
      'Speechmatics is rate-limiting requests (429) - try again in a minute',
    ]) expect(friendlyError(new Error('502 ' + m))).toBe(m)
  })
})
