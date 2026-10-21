import { describe, expect, it } from 'vitest'
import { friendlyError, isLlmUnreachable } from '../../util/friendlyError'

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
})

describe('friendlyError (round 253)', () => {
  it('a 4xx with a human sentence keeps only the sentence', () => {
    expect(friendlyError(new Error('400 The model address must start with http:// or https://'))).toBe('The model address must start with http:// or https://')
    expect(friendlyError(new Error('404 note not found'))).toBe('note not found')
    expect(friendlyError('')).toBe('Unknown error')
  })
})
