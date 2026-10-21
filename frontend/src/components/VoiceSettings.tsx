import { useState } from 'react'
import * as api from '../api'
import type { AsrProvider, ProviderConfig } from '../api'
import { t } from '../i18n'
import { friendlyError } from '../util/friendlyError'
import Icon from './Icon'



export type VoiceDraft = {
  asr_provider: AsrProvider
  asr_base_url: string
  assemblyai_api_key: string
  assemblyai_region: string
  speechmatics_api_key: string
  speechmatics_region: string
}

export const EMPTY_VOICE_DRAFT: VoiceDraft = {
  asr_provider: 'whisper', asr_base_url: '',
  assemblyai_api_key: '', assemblyai_region: 'us',
  speechmatics_api_key: '', speechmatics_region: 'eu',
}

/** Draft from the saved config. Key fields always start empty (keys are never sent back). */
export function voiceDraftFrom(c: ProviderConfig): VoiceDraft {
  return {
    asr_provider: c.asr_provider ?? 'whisper',
    asr_base_url: c.asr_base_url ?? '',
    assemblyai_api_key: '',
    assemblyai_region: c.assemblyai_region || 'us',
    speechmatics_api_key: '',
    speechmatics_region: c.speechmatics_region || 'eu',
  }
}

/** The voice part of the save body. Blank keys are left out: sending '' would mean "clear the key". */
export function voiceBody(d: VoiceDraft): Partial<Parameters<typeof api.setProviderConfig>[0]> {
  const body: Partial<Parameters<typeof api.setProviderConfig>[0]> = {
    asr_provider: d.asr_provider,
    // Empty string is valid here: clear the address and fall back to the .env default.
    asr_base_url: d.asr_base_url.trim(),
    assemblyai_region: d.assemblyai_region,
    speechmatics_region: d.speechmatics_region,
  }
  if (d.assemblyai_api_key.trim()) body.assemblyai_api_key = d.assemblyai_api_key.trim()
  if (d.speechmatics_api_key.trim()) body.speechmatics_api_key = d.speechmatics_api_key.trim()
  return body
}

/** Region ids per hosted provider; the first one is the provider's default. */
const REGIONS: Record<'assemblyai' | 'speechmatics', string[]> = {
  assemblyai: ['us', 'eu'],
  speechmatics: ['eu', 'us'],
}

/** Display label for a region id; called at render time so the language switch applies. */
function regionLabel(id: string): string {
  return id === 'eu' ? t('EU') : t('US')
}

export default function VoiceSettings({ cfg, value, onChange }: {
  cfg: ProviderConfig | null
  value: VoiceDraft
  onChange: (next: VoiceDraft) => void
}) {
  const set = (patch: Partial<VoiceDraft>) => onChange({ ...value, ...patch })
  const p = value.asr_provider
  const providers: { id: AsrProvider; label: string; hint: string }[] = [
    { id: 'whisper', label: t('Whisper server (self-hosted)'), hint: t('Free and local; needs a whisper.cpp server running on this machine or your network.') },
    { id: 'assemblyai', label: 'AssemblyAI', hint: t('Hosted service; recordings are uploaded to AssemblyAI. Needs your own API key.') },
    { id: 'speechmatics', label: 'Speechmatics', hint: t('Hosted service; recordings are uploaded to Speechmatics. Needs your own API key.') },
  ]
  const whisperUrlNow = value.asr_base_url.trim() || cfg?.asr_default_url || ''

  function hostedFields(id: 'assemblyai' | 'speechmatics') {
    const keySet = id === 'assemblyai' ? cfg?.assemblyai_api_key_set : cfg?.speechmatics_api_key_set
    const preview = id === 'assemblyai' ? cfg?.assemblyai_api_key_preview : cfg?.speechmatics_api_key_preview
    const key = id === 'assemblyai' ? value.assemblyai_api_key : value.speechmatics_api_key
    const region = id === 'assemblyai' ? value.assemblyai_region : value.speechmatics_region
    const label = id === 'assemblyai' ? 'AssemblyAI' : 'Speechmatics'
    return (
      <div className="stack" style={{ marginTop: 4, paddingLeft: 24 }}>
        <label className="muted" style={{ fontSize: 'var(--t-sm)' }}>API key</label>
        <input aria-label={t('{provider} API key', { provider: label })}
          type="password"
          placeholder={keySet ? t('Set {preview}; leave empty to keep it', { preview: preview ?? '' }) : t('Paste your {provider} API key', { provider: label })}
          value={key}
          onChange={(e) => set(id === 'assemblyai' ? { assemblyai_api_key: e.target.value } : { speechmatics_api_key: e.target.value })}
        />
        <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: 0 }}>
          {keySet
            ? <><Icon n="bx-check-circle" /> {t('An API key is saved.')}</>
            : <><Icon n="bx-error" /> {t('No API key yet: transcription will not work until you add one and save.')}</>}
        </p>
        <label className="muted" style={{ fontSize: 'var(--t-sm)', marginTop: 4 }}>{t('Region')}</label>
        <select aria-label={t('{provider} region', { provider: label })} value={region}
          onChange={(e) => set(id === 'assemblyai' ? { assemblyai_region: e.target.value } : { speechmatics_region: e.target.value })}>
          {REGIONS[id].map((r) => <option key={r} value={r}>{regionLabel(r)}</option>)}
        </select>
        <VoiceTestButton disabled={!(key.trim() || keySet)}
          disabledReason={t('Paste an API key first')}
          run={() => api.testProvider({ kind: 'asr', base_url: '', asr_provider: id, region, api_key: key.trim() || undefined, saved_key_of: id })} />
      </div>
    )
  }

  return (
    <>
      <p className="kb-section-title" style={{ marginTop: 18 }}>{t('Voice service')}</p>
      <p className="muted" style={{ fontSize: 'var(--t-sm)', marginTop: 0 }}>
        {t('Which service transcribes recordings. After saving, the "voice offline" status in the status bar is rechecked right away.')}
      </p>
      {providers.map((o) => (
        <div key={o.id}>
          <label className="row" style={{ gap: 8, cursor: 'pointer' }}>
            <input type="radio" name="asr-provider" checked={p === o.id} onChange={() => set({ asr_provider: o.id })} />
            <span>{o.label}</span>
          </label>
          {p === o.id && (
            <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '2px 0 0', paddingLeft: 24 }}>{o.hint}</p>
          )}
          {p === o.id && o.id === 'whisper' && (
            <div className="stack" style={{ marginTop: 4, paddingLeft: 24 }}>
              <label className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('Server address')}</label>
              <input aria-label={t('Voice service address')}
                placeholder={t('Default {url}', { url: cfg?.asr_default_url ?? '' })}
                value={value.asr_base_url}
                onChange={(e) => set({ asr_base_url: e.target.value })}
              />
              <VoiceTestButton disabled={!whisperUrlNow} disabledReason={t('Fill in the address first')}
                run={() => api.testProvider({ kind: 'asr', base_url: whisperUrlNow, asr_provider: 'whisper' })} />
            </div>
          )}
          {p === o.id && o.id !== 'whisper' && hostedFields(o.id)}
        </div>
      ))}
    </>
  )
}

/** "Test" button for the voice section: one real request, result shown underneath. */
function VoiceTestButton({ disabled, disabledReason, run }: {
  disabled?: boolean
  disabledReason: string
  run: () => Promise<api.ProviderTest>
}) {
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<api.ProviderTest | null>(null)
  return (
    <>
      <div className="row" style={{ gap: 8, marginTop: 6 }}>
        <button className="chip chip-action" disabled={busy || disabled}
                title={disabled ? disabledReason : t('Make one real request with these values; the result shows below')}
                onClick={async () => {
                  setBusy(true); setRes(null)
                  try { setRes(await run()) } catch (e) {
                    setRes({ ok: false, message: t('Could not test: {error}', { error: friendlyError(e) }), models: [], model_found: null, elapsed_ms: 0 })
                  } finally { setBusy(false) }
                }}>
          {busy ? <span className="spinner" /> : <Icon n="bx-link" />} {t('Test')}
        </button>
        {busy && <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('Connecting...')}</span>}
      </div>
      {res && (
        <p className={'probe-result' + (res.ok ? ' ok' : ' bad')}>
          <Icon n={res.ok ? 'bx-check-circle' : 'bx-error'} /> {res.message}
        </p>
      )}
    </>
  )
}
