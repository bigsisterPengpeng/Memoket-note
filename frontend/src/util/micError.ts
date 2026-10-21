import { friendlyError } from './friendlyError'
import { t } from '../i18n'


export function micError(e: unknown): string {
  const name = (e as { name?: string } | null)?.name || ''
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError' || name === 'SecurityError') {
    return t('Microphone access denied by the system: enable MEMOKET NOTE under “System Settings → Privacy & Security → Microphone”, then retry')
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError' || name === 'OverconstrainedError') {
    return t('No microphone found — connect one or check the input device settings')
  }
  if (name === 'NotReadableError' || name === 'AbortError') {
    return t('The microphone is in use by another program — close the app that is recording and retry')
  }
  return t('Could not open the microphone: {err}', { err: friendlyError(e) })
}
