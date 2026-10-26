import { useEffect, useState } from 'react'
import { friendlyError } from '../util/friendlyError'
import * as api from '../api'
import type { ProviderConfig, ProviderPreset } from '../api'
import { toast } from '../toast'
import { applyTheme, canSwitchTheme, getTheme, type Theme } from '../theme'
import { t } from '../i18n'
import Icon from './Icon'
import ProviderTestButton from './ProviderTestButton'
import VoiceSettings, { EMPTY_VOICE_DRAFT, voiceBody, voiceDraftFrom, type VoiceDraft } from './VoiceSettings'

/** Feature name -> human label. **A function, not a constant**: `t()` is looked up at render time so a
 *  language switch is picked up. */
const FEATURE_LABEL = (): Record<string, string> => ({
  'magic-tap': t('Continue'), 'note-harness/run': t('Smart Continue'), 'note-harness/resume': t('Smart Continue'), 'writing-plan/run': t('Endless Continue'),
  'writing-plan/start': t('Endless Continue · plan sections'),
  'compose/block': t('/ block'), 'compose/restructure': t('Smart layout'), skeleton: t('Writing outline'), rewrite: t('Rewrite / polish'), expand: t('Expand'),
  verify: t('Check'), digest: t('Digest'), 'memory/trace': t('Trace'), 'memory/relations': t('Memory relations'), 'skills/generate': t('Skill generation'),
  'kb/quality/judged': t('Extraction quality'), 'ingest/text': t('Save to knowledge base'), 'kb/extract~': t('Knowledge base extraction (estimated)'),
})


const FEATURE_GROUP = (): Record<string, string> => ({
  'note-harness': t('Smart Continue'), 'writing-plan': t('Endless Continue'), compose: t('Insert block'),
  memory: t('Memory'), skills: 'Skill', kb: t('Knowledge base'), ingest: t('Save to knowledge base'),
})

export function featureLabel(key: string): string {
  const exact = FEATURE_LABEL()[key]
  if (exact) return exact
  const head = key.split('/')[0]
  const group = FEATURE_GROUP()[head]
  return group ? t('{group} · other', { group }) : key
}
const fmtTok = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n))

/** Model usage: 24 hours / 7 days / 30 days / all time, by feature (rolling windows, not calendar days — the
 *  server counts in UTC, so "today" would be off in the small hours of UTC+8). Users paying for an API need
 *  to know where the money goes. */
function UsageSection() {
  const [u, setU] = useState<api.UsageSummary | null>(null)
  useEffect(() => { api.usageSummary().then(setU).catch(() => setU(null)) }, [])
  if (!u) return null
  const cell = (b: api.UsageBucket) => t('{calls} calls · {tok} tokens', { calls: b.calls, tok: fmtTok(b.prompt_tokens + b.completion_tokens) })
  return (
    <>
      <p className="kb-section-title" style={{ marginTop: 18 }}>{t('Model usage')}</p>
      <div className="row" style={{ gap: 14, flexWrap: 'wrap', fontSize: 'var(--t-md)' }}>
        <span><span className="muted">{t('24 hours')}</span> {cell(u.today)}</span>
        <span><span className="muted">{t('7 days')}</span> {cell(u.week)}</span>
        <span><span className="muted">{t('30 days')}</span> {cell(u.month)}</span>
        <span><span className="muted">{t('All')}</span> {cell(u.all)}</span>
      </div>
      {u.by_feature.length > 0 && (
        <div className="chip-wrap" style={{ marginTop: 6 }}>
          {u.by_feature.map((f) => <span key={f.feature} className="badge" title={t('{feature} · {calls} calls', { feature: f.feature, calls: f.calls })}>{featureLabel(f.feature)} {fmtTok(f.tokens)}</span>)}
        </div>
      )}
      <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '4px 0 0' }}>
        {t('Token counts come from provider responses, sorted by feature over the last 30 days; "Knowledge base extraction (estimated)" goes through KITE\'s own calls, which report no usage, so it is estimated from character counts.')}{u.models.length ? ' ' + t('Models: {models}', { models: u.models.join(', ') }) : ''}
      </p>
    </>
  )
}

/** Appearance, three choices. Placed before the LLM section — Trilium's settings start with Appearance too. */
function AppearanceSection() {
  const [theme, setTheme] = useState<Theme>(getTheme())
  const options: { v: Theme; label: string; icon: string }[] = [
    { v: 'system', label: t('Follow system'), icon: 'bx-desktop' },
    { v: 'light', label: t('Light'), icon: 'bx-sun' },
    { v: 'dark', label: t('Dark'), icon: 'bx-moon' },
  ]
  return (
    <>
      <h3 className="kb-section-title">{t('Appearance')}</h3>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        {options.map((o) => (
          <button key={o.v} className={'chip' + (theme === o.v ? ' active' : '')}
                  disabled={!canSwitchTheme() && o.v !== 'system'} title={!canSwitchTheme() && o.v !== 'system' ? t('The web version follows the system; only the desktop app can pick manually') : undefined}
                  onClick={() => { setTheme(o.v); applyTheme(o.v) }}>
            <Icon n={o.icon} /> {o.label}
          </button>
        ))}
      </div>
      {!canSwitchTheme() && <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '4px 0 0' }}>{t('In a browser the theme follows the system; the desktop app can pin light / dark.')}</p>}
    </>
  )
}




/** Provenance line at the bottom of the settings page: AGPL §13 requires offering the source to users. */
export function AboutLine() {
  return (
    <div className="muted" style={{ fontSize: 'var(--t-xs)', marginTop: 28, overflowWrap: 'anywhere' }}>
      <p><strong>MEMOKET NOTE</strong> · {t('An agent-native writing workspace')}</p>
      <p>{t('A writing agent that remembers your work.')}</p>
      <p>{t('A personal project built on the Memoket KITE memory engine, powered by a writing agent harness.')}</p>
      <p>
        {t('AGPL-3.0 · Source')} <a href="https://github.com/huilongan/Memoket-note" target="_blank" rel="noreferrer">github.com/huilongan/Memoket-note</a> {t('· Reuses Trilium\'s design and theme (AGPL-3.0); dependency list in docs/third-party-notices.md')}
      </p>
    </div>
  )
}

/** One entry's three fields as they sit in the inputs. `api_key` always starts empty: the backend never sends
 *  the key back, and this side must not keep it either. */
type Draft = { base_url: string; model: string; api_key: string }
const EMPTY_DRAFT: Draft = { base_url: '', model: '', api_key: '' }

/** Dropdown groups: order and labels. */
const GROUPS = (): { id: ProviderPreset['group']; label: string }[] => [
  { id: 'hosted', label: t('Cloud services') },
  { id: 'local', label: t('Local / self-hosted') },
  { id: 'custom', label: t('Custom') },
]

/** Drafts for every entry from the backend config (address / model as saved, key always empty). */
function draftsFrom(c: ProviderConfig): Record<string, Draft> {
  const out: Record<string, Draft> = {}
  for (const p of c.providers) out[p.id] = { base_url: p.base_url_saved, model: p.model, api_key: '' }
  return out
}

export default function SettingsPanel({ onClose, embedded = false }: { onClose?: () => void; embedded?: boolean }) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [cfg, setCfg] = useState<ProviderConfig | null>(null)
  const [provider, setProvider] = useState<string>('local')
  // one draft per entry, keyed by preset id: switch away and back and what was typed is still there
  // (the backend stores them per entry as well)
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  // which entries were touched on this screen (save stores more than the selected one)
  const [dirty, setDirty] = useState<Record<string, true>>({})
  const [voice, setVoice] = useState<VoiceDraft>(EMPTY_VOICE_DRAFT)
  const [autoSync, setAutoSync] = useState(false)
  // vision: follows the writing model by default; untick to configure separately
  const [visionOwn, setVisionOwn] = useState(false)
  const [visionBaseUrl, setVisionBaseUrl] = useState('')
  const [visionModel, setVisionModel] = useState('')
  const [visionApiKey, setVisionApiKey] = useState('')

  useEffect(() => {
    api.getProviderConfig().then((c) => {
      setCfg(c)
      setProvider(c.provider)
      setDrafts(draftsFrom(c))
      setVoice(voiceDraftFrom(c))
      setAutoSync(!!c.auto_sync_notes)
      setVisionOwn(!c.vision_follows_llm)
      setVisionBaseUrl(c.vision_base_url)
      setVisionModel(c.vision_model)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const presets = cfg?.providers ?? []
  const cur: ProviderPreset | undefined = presets.find((p) => p.id === provider)
  const draft = drafts[provider] ?? EMPTY_DRAFT
  const setDraft = (patch: Partial<Draft>) => {
    setDrafts((d) => ({ ...d, [provider]: { ...(d[provider] ?? EMPTY_DRAFT), ...patch } }))
    setDirty((d) => ({ ...d, [provider]: true }))
  }
  const curLabel = cur ? t(cur.label) : provider

  // "Test" uses what is in the inputs right now, not the saved copy: the user wants to know whether it works
  // before saving. Empty address = this entry's default; "Local / self-hosted" with an empty model = .env /
  // factory default.
  const urlNow = draft.base_url.trim() || cur?.base_url || ''
  const modelNow = draft.model.trim() || (provider === 'local' ? (cfg?.local_default_model ?? '') : '')
  const visionUrlNow = visionOwn ? visionBaseUrl.trim() : urlNow
  const visionModelNow = visionOwn ? visionModel.trim() : modelNow
  // key field: required for key-requiring entries / the custom endpoint; local servers usually need none, but
  // some gateways do, so the field stays and the label says it is optional
  const keyRequired = !!cur && (cur.needs_key || cur.group === 'custom')

  async function clearKey() {
    if (!cur) return
    try {
      const updated = await api.setProviderConfig({ provider, api_key: '' })
      setCfg(updated)
      setDraft({ api_key: '' })
      toast(t('Cleared the API key for {name}', { name: curLabel }))
      window.dispatchEvent(new CustomEvent('provider-changed'))
    } catch (e) {
      toast(t('Could not clear: {why}', { why: friendlyError(e) }), 'error')
    }
  }

  async function save() {
    setSaving(true)
    try {
      // first store every **other** entry touched on this screen (the API takes one entry per call), then the
      // selected one last — it is the one that becomes active
      for (const pid of Object.keys(dirty)) {
        if (pid === provider || !drafts[pid]) continue
        const d = drafts[pid]
        const other: Parameters<typeof api.setProviderConfig>[0] = { provider: pid, base_url: d.base_url.trim(), model: d.model.trim() }
        if (d.api_key.trim()) other.api_key = d.api_key.trim()
        await api.setProviderConfig(other)
      }
      const body: Parameters<typeof api.setProviderConfig>[0] = {
        provider,
        // an empty address falls back to this entry's default; an empty model for "Local / self-hosted"
        // falls back to .env / factory default
        base_url: draft.base_url.trim(),
        model: draft.model.trim(),
        // an empty voice address means "clear, back to default" — unlike the key, empty is a valid value here
        ...voiceBody(voice),
        auto_sync_notes: autoSync,
        // "follow the writing model" = clear both vision fields; the backend falls back (`get_active_vision_config`)
        vision_base_url: visionOwn ? visionBaseUrl.trim() : '',
        vision_model: visionOwn ? visionModel.trim() : '',
      }
      // never send an empty key: the backend reads "omitted = keep, empty string = clear", and a user who
      // only switched providers without retyping the key must not lose the saved one
      if (draft.api_key.trim()) body.api_key = draft.api_key.trim()
      if (visionOwn && visionApiKey.trim()) body.vision_api_key = visionApiKey.trim()
      const updated = await api.setProviderConfig(body)
      setCfg(updated)
      setDrafts(draftsFrom(updated))
      setDirty({})
      setVisionApiKey('')
      const activeLabel = updated.providers.find((p) => p.id === updated.active_provider)?.label
      setVoice(voiceDraftFrom(updated))
      toast(updated.configured
        ? t('Switched to {name}: {model} @ {url}', { name: activeLabel ? t(activeLabel) : updated.active_provider, model: updated.active_model || t('(model not set)'), url: updated.active_url })
        : t('Saved, but the model is not fully set up — fill in the address and model name before AI features will work'))
      // let the shell re-check health so the status bar's "LLM unreachable" updates right away
      window.dispatchEvent(new CustomEvent('provider-changed'))
    } catch (e) {
      toast(t('Save failed: {why}', { why: friendlyError(e) }), 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={embedded ? 'embedded-panel' : 'palette-backdrop'} onClick={embedded ? undefined : onClose}>
      <div
        className={embedded ? '' : 'panel-dialog settings-dialog'}
        onClick={(e) => e.stopPropagation()}
      >
        {!embedded && (
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2 style={{ margin: 0 }}><Icon n="bx-cog" /> {t('Settings')}</h2>
            <button className="icon-btn" title={t('Close (Esc)')} aria-label={t('Close')} onClick={onClose}><Icon n="bx-x" /></button>
          </div>
        )}

        {loading ? (
          <p className="muted"><span className="spinner" /> {t('Loading…')}</p>
        ) : (
          <div className="stack" style={{ marginTop: 12 }}>
            {embedded && <AppearanceSection />}
            {}
            {cfg && !cfg.configured && (
              <p className="probe-result bad" style={{ marginBottom: 4 }}>
                <Icon n="bx-error" /> {t('No model is set up yet, so none of the AI features work. Pick a provider below, fill it in, click "Test" to check it, then save.')}
              </p>
            )}
            <h3 className="kb-section-title">{t('Writing model')}</h3>
            <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '2px 0 8px' }}>
              {t('The model behind continue, revise and knowledge-base extraction — local models are free but slow; cloud providers need your own API key and are usually much faster. Each provider keeps its own key, so switching never loses one.')}
            </p>

            <label className="muted" style={{ fontSize: 'var(--t-sm)' }} htmlFor="provider-select">{t('Provider')}</label>
            <select id="provider-select" aria-label={t('Writing model provider')} value={provider}
                    onChange={(e) => setProvider(e.target.value)}>
              {GROUPS().map((g) => (
                <optgroup key={g.id} label={g.label}>
                  {presets.filter((p) => p.group === g.id).map((p) => (
                    <option key={p.id} value={p.id}>{t(p.label)}{p.key_set ? ' ✓' : ''}</option>
                  ))}
                </optgroup>
              ))}
            </select>

            {cur && (
              <div className="stack" style={{ marginTop: 4 }}>
                {}
                <label className="muted" style={{ fontSize: 'var(--t-sm)' }} htmlFor="provider-base-url">{t('Model address (OpenAI-compatible)')}</label>
                <input id="provider-base-url" aria-label={t('{name} model address', { name: curLabel })}
                  placeholder={t('Default {url}', { url: cur.base_url })}
                  value={draft.base_url}
                  onChange={(e) => setDraft({ base_url: e.target.value })}
                />
                <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: 0 }}>
                  {cur.group === 'local'
                    ? t('Ollama is http://127.0.0.1:11434/v1, LM Studio is http://127.0.0.1:1234/v1, llama.cpp / vLLM use their own /v1. Leave empty for the default.')
                    : cur.group === 'custom'
                      ? t('Base URL of any OpenAI-compatible endpoint (up to /v1). Requests are shaped like OpenAI\'s own.')
                      : t('Leave empty for the official address; fill in a gateway / proxy address if you use one.')}
                  {cur.docs ? <> <a href={cur.docs} target="_blank" rel="noreferrer">{t('Docs')}</a></> : null}
                </p>
                <label className="muted" style={{ fontSize: 'var(--t-sm)', marginTop: 4 }} htmlFor="provider-model">{t('Model')}</label>
                <input id="provider-model" list="provider-model-suggestions" aria-label={t('{name} model', { name: curLabel })}
                  placeholder={provider === 'local' && cfg?.local_default_model
                    ? t('Default {model}', { model: cfg.local_default_model })
                    : cur.models[0] ? t('e.g. {model}', { model: cur.models[0] }) : t('Type the model loaded on this server, or click "Test" and pick from the list')}
                  value={draft.model}
                  onChange={(e) => setDraft({ model: e.target.value })}
                />
                <datalist id="provider-model-suggestions">
                  {cur.models.map((m) => <option key={m} value={m} />)}
                </datalist>
                <label className="muted" style={{ fontSize: 'var(--t-sm)', marginTop: 4 }} htmlFor="provider-api-key">
                  {keyRequired ? t('API key') : t('API key (usually not needed locally)')}
                </label>
                <div className="row" style={{ gap: 8 }}>
                  <input id="provider-api-key" aria-label={t('{name} API key', { name: curLabel })}
                    type="password"
                    placeholder={cur.key_set
                      ? t('Set ({preview}); leave empty to keep it', { preview: cur.key_preview })
                      : keyRequired ? 'sk-...' : t('Most local servers do not check it; leave empty')}
                    value={draft.api_key}
                    onChange={(e) => setDraft({ api_key: e.target.value })}
                  />
                  {cur.key_set && (
                    <button className="chip" title={t('Delete the key saved for this provider')} onClick={clearKey}>{t('Clear saved key')}</button>
                  )}
                </div>
                <ProviderTestButton disabled={!urlNow} onPick={(m) => setDraft({ model: m })}
                  credentialRevision={`${cur.key_set}:${cur.key_preview}`}
                  request={{ kind: 'llm', provider, base_url: urlNow, model: modelNow, api_key: draft.api_key.trim() || undefined, saved_key_of: provider }} />
                {keyRequired && !cur.key_set && !draft.api_key.trim() && (
                  <p className="muted" style={{ fontSize: 'var(--t-sm)', color: 'var(--del)' }}>
                    {t('No API key set — even if saved, this provider will not be used and the app falls back to the local model.')}
                  </p>
                )}
              </div>
            )}

            {/* Voice service (whisper.cpp / AssemblyAI / Speechmatics): see VoiceSettings.tsx */}
            <VoiceSettings cfg={cfg} value={voice} onChange={setVoice} />

            {}
            <p className="kb-section-title" style={{ marginTop: 18 }}>{t('Vision (screen activity / image to table)')}</p>
            <label className="row" style={{ gap: 8, fontSize: 'var(--t-md)', alignItems: 'center' }}>
              <input type="checkbox" checked={!visionOwn} onChange={(e) => setVisionOwn(!e.target.checked)} />
              {t('Use the writing model above')}
            </label>
            {!visionOwn ? (
              <>
                <p className="muted" style={{ fontSize: 'var(--t-sm)', marginTop: 0 }}>
                  {t('Screenshots and images are sent to ')}<b>{t('the writing model\'s server')}</b>{t('. To keep screenshots on this machine / your LAN, untick this and set a local vision model separately.')}
                </p>
                <p className="mono-line">{visionModelNow || t('(model not set)')} @ {visionUrlNow || t('(not configured)')}</p>
              </>
            ) : (
              <div className="stack" style={{ marginTop: 4 }}>
                <p className="muted" style={{ fontSize: 'var(--t-sm)', marginTop: 0 }}>
                  {t('Screenshots go only here, ')}<b>{t('independent of the writing provider above')}</b>{t(' — switching writing to the cloud does not send screenshots there.')}
                </p>
                <label className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('Vision model address')}</label>
                <input aria-label={t('Vision model address')}
                  placeholder="http://127.0.0.1:11434/v1"
                  value={visionBaseUrl}
                  onChange={(e) => setVisionBaseUrl(e.target.value)}
                />
                <label className="muted" style={{ fontSize: 'var(--t-sm)', marginTop: 4 }}>{t('Vision model (must support images)')}</label>
                <input aria-label={t('Vision model')}
                  placeholder={t('e.g. {model}', { model: 'qwen2.5vl:7b' })}
                  value={visionModel}
                  onChange={(e) => setVisionModel(e.target.value)}
                />
                <label className="muted" style={{ fontSize: 'var(--t-sm)', marginTop: 4 }}>{t('API key (usually not needed locally)')}</label>
                <input aria-label={t('Vision API key')}
                  type="password"
                  placeholder={cfg?.vision_api_key_set ? t('Set; leave empty to keep it') : t('Leave empty')}
                  value={visionApiKey}
                  onChange={(e) => setVisionApiKey(e.target.value)}
                />
              </div>
            )}
            {}
            <ProviderTestButton disabled={!visionUrlNow} label={t('Test (sends an image)')}
              onPick={visionOwn ? setVisionModel : undefined}
              credentialRevision={visionOwn ? String(cfg?.vision_api_key_set) : `${cur?.key_set}:${cur?.key_preview}`}
              request={{ kind: 'vision', base_url: visionUrlNow, model: visionModelNow,
                api_key: (visionOwn ? visionApiKey : draft.api_key).trim() || undefined,
                saved_key_of: visionOwn ? 'vision' : provider, provider: visionOwn ? undefined : provider }} />

            <p className="kb-section-title" style={{ marginTop: 18 }}>{t('Notes ↔ knowledge base')}</p>
            <label className="row" style={{ gap: 8, fontSize: 'var(--t-md)', alignItems: 'center' }}>
              <input type="checkbox" checked={autoSync} onChange={(e) => setAutoSync(e.target.checked)} />
              {t('Sync notes to the knowledge base automatically after edits')}
            </label>
            <p className="muted" style={{ fontSize: 'var(--t-sm)', marginTop: 0 }}>
              {t('Only for notes already ingested: 2 minutes after you stop editing, or when you switch notes, the previously extracted facts are replaced (facts you added by hand stay). Each sync is one model call. When off, a yellow ⇡ in the tree marks notes edited but not synced.')}
            </p>

            <button className="primary" onClick={save} disabled={saving} style={{ marginTop: 8 }}>
              {saving ? <span className="spinner" /> : t('Save')}
            </button>
            {embedded && <UsageSection />}
          </div>
        )}
      </div>
    </div>
  )
}
