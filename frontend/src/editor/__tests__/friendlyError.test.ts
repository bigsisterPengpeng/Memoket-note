import { describe, expect, it } from 'vitest'
import { friendlyError, isLlmUnreachable } from '../../util/friendlyError'
import { setLang } from '../../i18n'

describe('friendlyError', () => {
  it('connection errors point to Settings', () => {
    expect(friendlyError(new Error('All connection attempts failed'))).toContain('Settings')
    // P3: the browser cannot reach the backend != the backend cannot reach the model -- this one no longer points to Settings
    expect(friendlyError('TypeError: Failed to fetch')).toContain('Cannot reach the app backend')
    expect(isLlmUnreachable(new Error('500 Internal Server Error'))).toBe(true)
  })
  it('other errors are kept as-is, minus the Error: prefix', () => {
    expect(friendlyError(new Error('anchor not found'))).toBe('anchor not found')
    expect(friendlyError('Error: 422 validation')).toBe('validation')   // since round 253 4xx status codes are not shown to users
    expect(isLlmUnreachable('anchor not found')).toBe(false)
  })
  it('classifies provider errors containing Chinese in the current interface language', () => {
    const error = 'invalid_api_key: \u5bc6\u94a5\u5931\u6548'
    try {
      setLang('en')
      expect(friendlyError(error)).toBe('Model service refused the request: wrong API key or no permission — fix it in Settings')
      expect(isLlmUnreachable(error)).toBe(true)
      setLang('zh')
      expect(friendlyError(error)).toContain('\u6a21\u578b\u670d\u52a1')
      expect(friendlyError('\u7528\u6237\u81ea\u5b9a\u4e49\u6d88\u606f')).toBe('\u7528\u6237\u81ea\u5b9a\u4e49\u6d88\u606f')
    } finally { setLang('en') }
  })
})

describe('friendlyError (round 253)', () => {
  it('a 4xx with a human sentence keeps only the sentence', () => {
    expect(friendlyError(new Error('400 The model address must start with http:// or https://'))).toBe('The model address must start with http:// or https://')
    expect(friendlyError(new Error('404 note not found'))).toBe('note not found')
    expect(friendlyError('')).toBe('Unknown error')
  })
})
