import { useId } from 'react'
import { appleAvailable } from '../api'
import { t } from '../i18n'
import { ConnectionStatus, useConnectionAvailability } from './ConnectionAvailability'

export default function AppleNotesImport({ disabled, onImport }: { disabled: boolean; onImport: () => void }) {
  const { state, retry } = useConnectionAvailability(appleAvailable)
  const id = useId()
  return <section className="apple-import" aria-label={t('Apple Notes import')}>
    <div className="row" style={{ gap: 8, alignItems: 'center' }}>
      <span style={{ width: 88 }}>Apple Notes</span>
      <button onClick={onImport} disabled={disabled || state.status !== 'ready'} aria-describedby={id}>
        {disabled ? <span className="spinner" /> : t('Import all notes')}
      </button>
    </div>
    <ConnectionStatus id={id} name="Apple Notes" state={state} onRetry={retry} disabled={disabled} />
    {state.status === 'ready' && <p className="muted">
      {t('On the first import macOS shows an "allow to control Notes" permission prompt; just click Allow.')}
    </p>}
  </section>
}
