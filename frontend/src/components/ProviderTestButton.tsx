import { useEffect, useMemo, useRef, useState } from 'react'
import { testProvider, type ProviderTest, type ProviderTestRequest } from '../api'
import { t } from '../i18n'
import { friendlyError } from '../util/friendlyError'
import Icon from './Icon'

export default function ProviderTestButton({ request, credentialRevision = '', disabled, disabledReason, label, onPick }: {
  request: ProviderTestRequest
  credentialRevision?: string
  disabled?: boolean
  disabledReason?: string
  label?: string
  onPick?: (model: string) => void
}) {
  const { kind, base_url, model, api_key, saved_key_of, provider, asr_provider, region } = request
  const target = useMemo(() => ({ kind, base_url, model, api_key, saved_key_of, provider, asr_provider, region }),
    [kind, base_url, model, api_key, saved_key_of, provider, asr_provider, region])
  // Use object identity rather than putting credentials into React keys or DOM attributes.
  const context = useMemo(() => ({ target, credentialRevision }), [target, credentialRevision])
  type Run = { context: typeof context; controller: AbortController; timeout?: ReturnType<typeof setTimeout> }
  const running = useRef<Run | null>(null)
  const [state, setState] = useState<{ context: typeof context; busy: boolean; result: ProviderTest | null } | null>(null)
  const active = state?.context === context ? state : null
  const busy = !!active?.busy
  const result = active?.result

  useEffect(() => () => {
    if (running.current?.context === context) {
      clearTimeout(running.current.timeout)
      running.current.controller.abort()
      running.current = null
    }
  }, [context])

  async function test() {
    if (running.current) {
      clearTimeout(running.current.timeout)
      running.current.controller.abort()
    }
    const run: Run = { context, controller: new AbortController() }
    running.current = run
    setState({ context, busy: true, result: null })
    const failure = (message: string): ProviderTest => ({ ok: false, message, models: [], model_found: null, elapsed_ms: 0 })
    run.timeout = setTimeout(() => {
      if (running.current !== run) return
      run.controller.abort()
      running.current = null
      setState({ context, busy: false, result: failure(t('Connection test timed out. Check the endpoint and try again.')) })
    }, 45_000)
    try {
      const response = await testProvider(target, run.controller.signal)
      if (running.current === run && !run.controller.signal.aborted) {
        setState({ context, busy: false, result: response })
      }
    } catch (error) {
      if (running.current === run && !run.controller.signal.aborted) {
        setState({ context, busy: false, result: failure(t('Could not test: {why}', { why: friendlyError(error) })) })
      }
    } finally {
      clearTimeout(run.timeout)
      if (running.current === run) running.current = null
    }
  }

  const name = kind === 'llm' ? t('Test writing model') : kind === 'vision' ? t('Test vision model') : t('Test voice service')
  return <>
    <div className="row" style={{ gap: 8, marginTop: 6 }}>
      <button className="chip chip-action" disabled={busy || disabled} aria-label={name}
        title={disabled ? disabledReason ?? t('Fill in the address first') : t('Make one real request with these values; the result shows below')}
        onClick={() => void test()}>
        {busy ? <span className="spinner" /> : <Icon n="bx-link" />} {label ?? t('Test')}
      </button>
      {busy && <span className="muted" role="status">{t('Connecting…')}</span>}
    </div>
    {state && !active && <p className="muted" role="status">{t('Settings changed. Test again to check the current values.')}</p>}
    {result && <p className={'probe-result' + (result.ok ? ' ok' : ' bad')} role="status">
      <Icon n={result.ok ? 'bx-check-circle' : 'bx-error'} /> {result.message}
    </p>}
    {result && onPick && result.models.length > 0 && <div className="stack" style={{ gap: 4, marginTop: 4 }}>
      <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: 0 }}>
        {t('Models available on this server — click one to fill in "Model":')}
      </p>
      <ul className="provider-models" aria-label={t('Available models')}>
        {result.models.map((item) => <li key={item}>
          <button className={'chip' + (item === model ? ' active' : '')} aria-pressed={item === model}
            title={t('Use as model: {m}', { m: item })} onClick={() => onPick(item)}>
            {item === model && <Icon n="bx-check" />} {item}
          </button>
        </li>)}
      </ul>
    </div>}
  </>
}
