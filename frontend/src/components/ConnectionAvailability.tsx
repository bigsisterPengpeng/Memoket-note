import { useEffect, useState } from 'react'
import type { ConnectionAvailability } from '../api'
import { t } from '../i18n'

type Check = (signal?: AbortSignal) => Promise<ConnectionAvailability>
type CheckState = { status: 'checking' | 'ready' | 'unavailable' | 'error'; reason: string }

export function useConnectionAvailability(check: Check) {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<CheckState>({ status: 'checking', reason: '' })

  useEffect(() => {
    let active = true
    const controller = new AbortController()
    setState({ status: 'checking', reason: '' })
    const timeout = setTimeout(() => {
      if (!active) return
      active = false
      setState({ status: 'error', reason: '' })
      controller.abort()
    }, 8000)
    void Promise.resolve().then(() => check(controller.signal)).then((result) => {
      if (active) setState({ status: result.available ? 'ready' : 'unavailable', reason: result.reason })
    }).catch(() => {
      if (active) setState({ status: 'error', reason: '' })
    }).finally(() => clearTimeout(timeout))
    return () => { active = false; clearTimeout(timeout); controller.abort() }
  }, [check, attempt])

  return { state, retry: () => setAttempt((value) => value + 1) }
}

export function ConnectionStatus({ id, name, state, onRetry, disabled = false }: {
  id: string; name: string; state: CheckState; onRetry: () => void; disabled?: boolean
}) {
  const message = state.status === 'checking' ? t('Checking {name} availability…', { name })
    : state.status === 'error' ? t('Could not check {name}. Check the app connection and try again.', { name })
    : state.status === 'ready' ? t('{name} is available in this workspace.', { name })
    : state.reason ? t(state.reason) : t('{name} is unavailable in this workspace.', { name })
  return <div className="connector-check">
    <p id={id} role="status">{message}</p>
    <button type="button" disabled={disabled || state.status === 'checking'}
      onClick={onRetry} aria-label={t('Check {name} again', { name })}>{t('Check again')}</button>
  </div>
}
