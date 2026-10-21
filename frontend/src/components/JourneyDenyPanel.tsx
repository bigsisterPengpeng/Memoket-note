import { useEffect, useState } from 'react'

import { journeyDeny, journeySetDeny, type JourneyDeny } from '../api'
import { friendlyError } from '../util/friendlyError'
import { toast } from '../toast'
import Icon from './Icon'
import { t } from '../i18n'

/**
 * "Don't record these".
 *
 * **If users can't add their own, the only option is to turn the feature off** (docs/daily-journey-plan.md §1 ②):
 * the default list blocks generic things like password managers, banks and private windows, but not "that internal system
 * at our company" or "the site where I see my doctor" — and it's exactly these that decide whether someone dares keep it on all the time.
 *
 * The built-in list is read-only: **"put the password manager back into recording scope" is not an option that should be offered.**
 */
export default function JourneyDenyPanel() {
  const [d, setD] = useState<JourneyDeny | null>(null)
  const [draft, setDraft] = useState('')
  const [kind, setKind] = useState<'apps' | 'words'>('apps')

  useEffect(() => { journeyDeny().then(setD).catch(() => setD(null)) }, [])

  async function put(apps: string[], words: string[]) {
    try { setD(await journeySetDeny(apps, words)) }
    catch (e) { toast(friendlyError(e), 'error') }
  }

  function add() {
    const t = draft.trim()
    if (!d || !t) return
    setDraft('')
    if (d[kind].includes(t)) return
    void put(kind === 'apps' ? [...d.apps, t] : d.apps, kind === 'words' ? [...d.words, t] : d.words)
  }

  if (!d) return null
  const drop = (k: 'apps' | 'words', v: string) =>
    put(k === 'apps' ? d.apps.filter((x) => x !== v) : d.apps,
        k === 'words' ? d.words.filter((x) => x !== v) : d.words)

  return (
    <div className="journey-deny">
      <h3 className="kb-section-title">{t('Never record these')}</h3>
      <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '2px 0 8px' }}>
        {t('On a match, ')}<b>{t('no screenshot is even taken')}</b>{t('. App names must be exact (as shown in the menu bar); title words match by inclusion.')}
      </p>

      <div className="chip-wrap">
        {[...d.builtin_apps, ...d.builtin_words].map((x) => (
          <span key={x} className="chip" title={t('Excluded by default; cannot be removed')}>{x}</span>
        ))}
      </div>

      {(d.apps.length > 0 || d.words.length > 0) && (
        <div className="chip-wrap" style={{ marginTop: 6 }}>
          {d.apps.map((x) => (
            <span key={'a' + x} className="chip mine">{x}
              <button className="icon-btn sm" title={t('Remove')} onClick={() => void drop('apps', x)}><Icon n="bx-x" /></button>
            </span>
          ))}
          {d.words.map((x) => (
            <span key={'w' + x} className="chip mine">{t('Title contains “{x}”', { x })}
              <button className="icon-btn sm" title={t('Remove')} onClick={() => void drop('words', x)}><Icon n="bx-x" /></button>
            </span>
          ))}
        </div>
      )}

      <div className="row" style={{ gap: 6, marginTop: 8 }}>
        <span className="seg">
          <button className={kind === 'apps' ? 'on' : ''} onClick={() => setKind('apps')}>{t('App')}</button>
          <button className={kind === 'words' ? 'on' : ''} onClick={() => setKind('words')}>{t('Title word')}</button>
        </span>
        <input aria-label={t('App or window keyword to exclude')} value={draft} onChange={(e) => setDraft(e.target.value)} style={{ flex: 1 }}
               placeholder={kind === 'apps' ? t('e.g. Signal') : t('e.g. medical report')}
               onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }} />
        <button onClick={add} disabled={!draft.trim()} title={draft.trim() ? '' : t('Enter one first')}>{t('Add')}</button>
      </div>
    </div>
  )
}
