/**
 * Personal preferences -- a different thing from the knowledge base: no extraction, effective as soon as written; the writing outline / smart edit /
 * magic tap continuation all read them. Lives in Settings (it used to be squeezed into the knowledge-base panel in the right pane).
 */
import { useEffect, useState } from 'react'
import { addProfileEntry, deleteProfileEntry, listProfile } from '../api'
import type { ProfileEntry } from '../api'
import Icon from './Icon'
import { t } from '../i18n'

export default function PreferencesPanel() {
  const [profile, setProfile] = useState<ProfileEntry[]>([])
  const [newPref, setNewPref] = useState('')
  const [addingPref, setAddingPref] = useState(false)
  useEffect(() => { listProfile().then(setProfile).catch(() => {}) }, [])

  async function doAddPref() {
    if (!newPref.trim()) return
    setAddingPref(true)
    try {
      const entry = await addProfileEntry(newPref.trim())
      setProfile((prev) => [entry, ...prev])
      setNewPref('')
    } finally { setAddingPref(false) }
  }

  async function doDeletePref(id: string) {
    await deleteProfileEntry(id)
    setProfile((prev) => prev.filter((p) => p.id !== id))
  }

  return (
    <div className="stack">
      <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>
        {t('Separate from the knowledge base — no extraction here; takes effect immediately. Outline, Smart edit and magic-tap Continue all read these.')}
      </p>
      <div className="stack">
        <div className="row">
          <input aria-label={t('Writing preference')}
            maxLength={400}   /* Matches backend profile.MAX_CHARS: one entry is a sentence, not an essay */
            placeholder={t('e.g. Prefer concise language; in weekly reports lead with the conclusion, then the data…')}
            value={newPref}
            onChange={(e) => setNewPref(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && doAddPref()}
            style={{ flex: 1 }}
          />
          <button onClick={doAddPref} disabled={!newPref.trim() || addingPref} title={!newPref.trim() ? t('Write a preference first') : undefined}>
            {addingPref ? <span className="spinner" /> : t('Add')}
          </button>
        </div>
        {profile.map((p) => (
          <div className="card" key={p.id}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span>{p.text}</span>
              <button className="icon-btn" aria-label={t('Delete this')} title={t('Delete this')} onClick={() => doDeletePref(p.id)}><Icon n="bx-x" /></button>
            </div>
          </div>
        ))}
      </div>

    </div>
  )
}
