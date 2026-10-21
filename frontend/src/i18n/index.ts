/**
 * UI language. **English source text is the key**: `t('Restore failed')` returns the
 * English text as-is; in Chinese mode it looks the key up in `zh/` and falls back to
 * English when missing (visible, and `scripts/check-i18n.mts` reports it).
 *
 * Why English keys instead of ids like `t('trash.restoreFailed')`: the source stays
 * readable, a missing translation only costs one untranslated sentence, and the
 * repo rule "no Chinese characters in code" (comments included) is enforced by a
 * single gate that counts Han characters.
 *
 * Placeholders are `{name}`: `t('Imported {n} notes', { n })` — same on both sides.
 * The product defaults to English; the Settings page switches to Chinese.
 */
import { useSyncExternalStore } from 'react'
import { ZH } from './zh'

export type Lang = 'en' | 'zh'
export const LANG_KEY = 'memoket-note-lang'
export const LANGS: { id: Lang; label: string }[] = [
  { id: 'en', label: 'English' },
  { id: 'zh', label: ZH['Chinese'] ?? 'Chinese' },
]

function detect(): Lang {
  try {
    const saved = localStorage.getItem(LANG_KEY)
    if (saved === 'en' || saved === 'zh') return saved
  } catch { /* no localStorage (node, private mode): default */ }
  return 'en'
}

let lang: Lang = detect()
const listeners = new Set<() => void>()

export function getLang(): Lang { return lang }

export function setLang(next: Lang): void {
  if (next === lang) return
  lang = next
  try { localStorage.setItem(LANG_KEY, next) } catch { /* cannot persist; the user picks again next time */ }
  if (typeof document !== 'undefined') document.documentElement.lang = next === 'zh' ? 'zh-CN' : 'en'
  try { (window as Window & { memoketDesktop?: { rememberLang?: (l: string) => void } }).memoketDesktop?.rememberLang?.(next) } catch { /* web build has no shell */ }
  listeners.forEach((fn) => fn())
}

/** The root component subscribes; a language change remounts the whole tree (`main.tsx` keys `<App>` by lang). */
export function useLang(): Lang {
  return useSyncExternalStore(
    (fn) => { listeners.add(fn); return () => { listeners.delete(fn) } },
    () => lang,
    () => lang,
  )
}

export type Params = Record<string, string | number>

function fill(s: string, params?: Params): string {
  if (!params) return s
  return s.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m))
}

/** Translate one UI string. `en` is the English source text (and the dictionary key). */
export function t(en: string, params?: Params): string {
  const s = lang === 'zh' ? (ZH[en] ?? en) : en
  return fill(s, params)
}

/** Whether the Chinese dictionary has this key — for gates and tests. */
export function hasZh(en: string): boolean { return Object.prototype.hasOwnProperty.call(ZH, en) }

if (typeof document !== 'undefined') {
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
}
