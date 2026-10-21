import { describe, expect, it } from 'vitest'
import { micError } from '../../util/micError'

function err(name: string, message = 'x') {
  const e = new Error(message)
  e.name = name
  return e
}

describe('micError', () => {
  it('denied by the system -> points to System Settings', () => {
    expect(micError(err('NotAllowedError'))).toContain('System Settings')
  })
  it('no device / in use each have a sentence', () => {
    expect(micError(err('NotFoundError'))).toContain('No microphone found')
    expect(micError(err('NotReadableError'))).toContain('in use')
  })
  it('other errors go through friendlyError and keep the original message', () => {
    expect(micError(new Error('weird thing'))).toBe('Could not open the microphone: weird thing')
    expect(micError(null)).toContain('Could not open the microphone')
  })
})
