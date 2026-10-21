import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { clientLog } from './api'
import { restoreTheme } from './theme'
import { checkBackendIdentity } from './util/backendIdentity'
import { useLang } from './i18n'
import './design-tokens.css'  // First: source tokens (the only file permitting literal colors; docs/UI_SPEC.md)
import './shell.css'   // Then: shell tokens refer to source tokens
import './styles.css'  // Finally: older variable names refer to those tokens

restoreTheme()

if (new URLSearchParams(location.search).get('probe')) requestAnimationFrame(() => void clientLog('info', `first paint ${Math.round(performance.now())} ms · js ${Math.round((performance.getEntriesByType('resource') as PerformanceResourceTiming[]).filter((r) => r.name.endsWith('.js')).reduce((a, r) => a + (r.transferSize || r.encodedBodySize || 0), 0) / 1024)} KB`, '', 'first-paint'))
// Application menu Help > Keyboard shortcuts uses the same path as Cmd+/
// Flush unsaved text before quitting (App handles flush-save and replies with flushed)
window.memoketDesktop?.onFlush?.(() => window.dispatchEvent(new CustomEvent('flush-save')))
window.memoketDesktop?.onMenu?.((name) => {
  if (name === 'shortcuts') window.dispatchEvent(new CustomEvent('show-shortcuts'))
  if (name === 'export-all') window.dispatchEvent(new CustomEvent('export-all'))
  if (name === 'new-note') window.dispatchEvent(new CustomEvent('new-note'))
  if (name === 'today') window.dispatchEvent(new CustomEvent('open-today'))
  if (name === 'import') window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'app:import' }))
  if (name === 'trash') window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'app:trash' }))
  if (name === 'journey') window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'app:journey' }))
  if (name.startsWith('tab:')) window.dispatchEvent(new CustomEvent('tab-action', { detail: name.slice(4) }))
})


// showing a banner on mismatch. The web build has no shell and returns quietly.
void checkBackendIdentity()

// Report errors that escape all try blocks too
window.addEventListener('error', (e) => void clientLog('error', String(e.message), e.error?.stack ?? '', 'window'))
window.addEventListener('unhandledrejection', (e) => void clientLog('error', String(e.reason?.message ?? e.reason), e.reason?.stack ?? '', 'promise'))

// Reserve traffic-light space only on macOS (shell.css .tab-row-left-spacer)
if (/Mac/.test(navigator.platform)) document.documentElement.classList.add('is-mac')

// Remount the whole tree when the language changes (`key`): `t()` is evaluated at render time.
function Root() {
  const lang = useLang()
  return <ErrorBoundary key={lang}><App /></ErrorBoundary>
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
