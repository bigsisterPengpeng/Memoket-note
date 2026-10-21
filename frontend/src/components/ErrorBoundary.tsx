
import { Component, type ReactNode } from 'react'

import { clientLog } from '../api'
import { t } from '../i18n'

type S = { error: Error | null; info: string }

export default class ErrorBoundary extends Component<{ children: ReactNode }, S> {
  state: S = { error: null, info: '' }
  static getDerivedStateFromError(error: Error): Partial<S> { return { error } }
  componentDidCatch(error: Error, info: { componentStack?: string }) {
    this.setState({ info: info.componentStack ?? '' })
    void clientLog('error', error.message, (error.stack ?? '') + '\n--- component stack ---' + (info.componentStack ?? ''), 'render')
  }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div style={{ padding: 32, maxWidth: 760, margin: '0 auto', fontFamily: 'var(--sans)' }}>
        <h2 style={{ textTransform: 'none', fontSize: 'var(--t-xl)' }}>{t('The interface hit an error; your text is safe')}</h2>
        <p style={{ color: 'var(--muted)' }}>{t('Autosave kept running and the note is in the database. Reload to get back; the error has been logged.')}</p>
        <pre style={{ whiteSpace: 'pre-wrap', fontSize: 'var(--t-sm)', background: 'var(--card-alt)', padding: 12, borderRadius: 'var(--r)' }}>
          {this.state.error.message}{'\n'}{this.state.info.split('\n').slice(0, 8).join('\n')}
        </pre>
        <button onClick={() => window.location.reload()}>{t('Reload')}</button>
      </div>
    )
  }
}
