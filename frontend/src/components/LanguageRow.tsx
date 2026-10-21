import { LANGS, setLang, t, useLang } from '../i18n'

/** Settings › Interface language. Takes effect immediately (the root remounts by language); remembered on this browser / machine. */
export default function LanguageRow() {
  const lang = useLang()
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <label htmlFor="ui-lang" style={{ minWidth: 96 }}>{t('Interface language')}</label>
      <select id="ui-lang" aria-label={t('Interface language')} value={lang} onChange={(e) => setLang(e.target.value as typeof lang)}>
        {LANGS.map((l) => <option key={l.id} value={l.id}>{t(l.label)}</option>)}
      </select>
    </div>
  )
}
