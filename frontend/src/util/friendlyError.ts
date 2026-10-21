
import { t } from '../i18n'
import { ZH } from '../i18n/zh'
/** A bare HTTP reason phrase (like `500 Internal Server Error`) does not count as a human sentence from the backend. */
const HTTP_REASON = /^(Internal Server Error|Bad Gateway|Service Unavailable|Gateway Time-?out|Request Time-?out|Unauthorized|Forbidden|Not Found|Bad Request|Too Many Requests|Conflict|Unprocessable (?:Entity|Content))$/i

/** The starts of the "model unreachable / model-side error" sentences (English source; in the Chinese UI the translation is compared too). */
const LLM_SIDE_HEADS = ['Model unreachable', 'Backend error', 'Model service', 'Model took too long to respond']
const BACKEND_DOWN_HEAD = 'Cannot reach the app backend'
// Compared in both languages whatever the UI language: the backend answers in its own request language
const startsWithAny = (m: string, heads: string[]) => heads.some((h) => m.startsWith(h) || m.startsWith(t(h)) || (!!ZH[h] && m.startsWith(ZH[h])))

export function friendlyError(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e ?? '')
  const msg = raw.replace(/^Error:\s*/i, '').replace(/^TypeError:\s*/i, '')
  // The browser -> backend hop is broken: the backend process is not up / just restarted / was killed. Nothing to do with the model; do not point to Settings.
  if (/^Failed to fetch$|NetworkError when attempting|Load failed|net::ERR_/i.test(msg)) {
    return t('Cannot reach the app backend (the backend process is not running, or just restarted) — wait a few seconds and retry; if that fails, restart the app')
  }
  // After the status code there is already a Chinese sentence (made human by the backend); the status code means nothing to users, keep only the sentence
  const body = msg.replace(/^\d{3}\s+(?=\S)/, '')
  if (/[\u4e00-\u9fff]/.test(body)) return body
  // Voice-service sentences from `asr.describe_error` are already written for the user; keep them
  // as-is so their "401" / "timed out" are not re-read as LLM errors below.
  if (/\bvoice service\b|AssemblyAI|Speechmatics/i.test(body)) return body
  if (/transcription failed|whisper/i.test(msg)) {
    return t('Voice service unreachable or transcription failed — check the voice service address in Settings')
  }
  if (/connection attempts failed|ECONNREFUSED|ENOTFOUND|Connect(?:ion)? (?:error|refused)|timed? ?out|Read timeout/i.test(msg)) {
    return t('Model unreachable — check the LLM provider address and key in Settings')
  }
  // An English backend sentence is human too (has a status code, is not a bare HTTP reason phrase): pass it through as well
  if (body !== msg && /\s/.test(body.trim()) && !HTTP_REASON.test(body)) return body
  if (/\b50[023]\b|Internal Server Error|Bad Gateway|Service Unavailable/i.test(msg)) {
    return t('Backend error (most likely the model did not respond) — check the LLM provider in Settings, or try again later')
  }
  if (/\b401\b|\b403\b|Unauthorized|invalid[_ ]api[_ ]key/i.test(msg)) {
    return t('Model service refused the request: wrong API key or no permission — fix it in Settings')
  }
  if (/\b429\b|rate limit/i.test(msg)) return t('Model service is rate-limited, try again in a moment')
  return body || t('Unknown error')
}

/** Whether this error is of the "model unreachable / model-side error" kind -- callers use it to decide whether to offer an "Open settings" button. */
export function isLlmUnreachable(e: unknown): boolean {
  const m = friendlyError(e)
  return startsWithAny(m, LLM_SIDE_HEADS)
}

/** Whether it is "the backend process itself is unreachable" -- in that case "Open settings" cannot help. */
export function isBackendDown(e: unknown): boolean {
  return startsWithAny(friendlyError(e), [BACKEND_DOWN_HEAD])
}
