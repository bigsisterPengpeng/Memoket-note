
import { t } from '../i18n'
const KEY = 'memoket.tray.default'

export function trayByDefault(): boolean {
  try {
    const v = localStorage.getItem(KEY)
    return v === null ? true : v === '1'
  } catch { return true }
}

export function setTrayByDefault(on: boolean): void {
  try { localStorage.setItem(KEY, on ? '1' : '0') } catch { /* does not matter */ }
  window.dispatchEvent(new CustomEvent('tray-default-changed', { detail: on }))
}

/** The title of a recording / clip landed as a tray item: like "Recording 14:05", so the user can tell which one it is in the tray */
export function recordingTitle(now: Date = new Date()): string {
  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  return t('Recording {hh}:{mm}', { hh, mm })
}
