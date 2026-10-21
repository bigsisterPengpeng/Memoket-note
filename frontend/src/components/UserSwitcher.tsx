import { useState } from 'react'
import * as api from '../api'
import { toast } from '../toast'
import { TextPrompt } from './Dialogs'
import { t } from '../i18n'

/**
 * The user avatar at the bottom of the launch bar (modeled on the GlobalMenu at the bottom of Trilium's launch bar).
 *
 * getUser() assigns a random `user-xxxxxx` on first access, and no UI used to let you change it --
 * a knowledge base imported by script into a named user was never visible from the app. Switching does a full page reload,
 * which is the simplest and most correct way to wipe every bit of per-note React state at once.
 */
export default function UserSwitcher() {
  const [asking, setAsking] = useState(false)
  const user = api.getUser()
  return (
    <>
      <button className="launcher-btn launcher-user" title={t('Current user: {user}', { user }) + '\n' + t('Click to switch')}
              onClick={() => setAsking(true)}>
        <span className="avatar">{(user[0] ?? '?').toUpperCase()}</span>
      </button>
      {asking && (
        <TextPrompt req={{ title: t('Switch user (each user has a separate note library and knowledge base)'), initial: user,
          resolve: (v) => {
            setAsking(false)
            const next = (v ?? '').trim()
            if (!next || next === user) return
            // The user name is spliced into the backend data directory and put into an HTTP header: only letters, digits, _ . - (same regex as the backend, else 400)
            if (!/^[A-Za-z0-9_.-]{1,64}$/.test(next)) { toast(t('User names may only contain letters, digits, _ . - (max 64 characters)'), 'error'); return }
            api.setUser(next); window.location.replace(api.switchUserHref(window.location.href, next))
          } }} />
      )}
    </>
  )
}
