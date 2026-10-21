// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { getUser, setUser, switchUserHref } from '../../api'

/** The desktop opens at `/?user=<last identity>`. The old switch used `setUser` followed by reload:
 *  the old `?user=` took precedence after reloading and replaced the selected identity. */
function openAt(search: string) {
  history.replaceState(null, '', '/' + search)
}

describe('Switch user', () => {
  beforeEach(() => localStorage.clear())

  it('reloading the same address restores its old identity (the original bug)', () => {
    openAt('?user=test-user')
    expect(getUser()).toBe('test-user')
    setUser('alice')
    expect(getUser()).toBe('test-user')
  })

  it('navigating to the updated ?user= reads and remembers the new identity', () => {
    openAt('?user=test-user')
    setUser('alice')
    const next = new URL(switchUserHref(location.href, 'alice'))
    openAt(next.search)
    expect(getUser()).toBe('alice')
    expect(localStorage.getItem('memoket-note-user')).toBe('alice')
  })

  it('changes only user, preserving other parameters and adding user if absent', () => {
    const a = new URL(switchUserHref('http://127.0.0.1:5123/?user=test-user&probe=p1#x', 'alice'))
    expect(a.searchParams.get('user')).toBe('alice')
    expect(a.searchParams.get('probe')).toBe('p1')
    expect(a.hash).toBe('#x')
    expect(new URL(switchUserHref('http://127.0.0.1:5123/', 'bob')).searchParams.get('user')).toBe('bob')
  })
})
