import { useSyncExternalStore } from 'react'
import { dismissToast, getSnapshot, subscribe } from '../toast'
import { t } from '../i18n'

export default function Toaster() {
  const toasts = useSyncExternalStore(subscribe, getSnapshot)
  if (toasts.length === 0) return null
  return (
    <div className="toaster">
      {toasts.map((item) => (
        <div key={item.id} className={'toast ' + item.kind}>
          <span onClick={() => dismissToast(item.id)} title={t('Click to dismiss')} style={{ cursor: 'pointer' }}>
            {item.message}
          </span>
          {}
          {item.action && (
            <button className="linklike link" style={{ marginLeft: 10 }} onClick={item.action.onClick}>
              {item.action.label}
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
