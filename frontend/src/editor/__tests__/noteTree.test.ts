/**
 * Tree flattening: what gets drawn, at which level, in what order.
 *
 * This is the foundation of a usable tree. Each of the three properties corresponds to a real failure:
 *   · only expanded nodes are flattened -- otherwise a deep tree draws hundreds of rows right away
 *   · a collapsed node's whole subtree is not drawn
 *   · **a cycle must not blow the stack**: the backend has a guard, but the frontend should not assume it never leaks; recursion on a cycle means
 *     a white screen, while iteration with a seen set at worst draws duplicates and the UI stays alive
 */
import { describe, expect, it } from 'vitest'

import { flattenTreeForTest as flatten } from '../../components/NoteTree'
import type { TreeRow } from '../../api'

function row(note: string, parent: string, extra: Partial<TreeRow> = {}): TreeRow {
  return {
    id: `${parent}>${note}`, note_id: note, parent_note_id: parent,
    position: 0, is_expanded: false, title: note, preview: '',
    pinned: false, source: "", updated_at: "", child_count: 0, branch_count: 1,
    cite_count: 0, ingested_at: "", fact_count: 0,
    ...extra,
  }
}

describe('flatten', () => {
  it('draws only the level under the root; collapsed nodes are not expanded', () => {
    const rows = [
      row('a', 'root', { child_count: 1 }),
      row('a1', 'a'),
    ]
    expect(flatten(rows).map((n) => n.note_id)).toEqual(['a'])
  })

  it('expanded nodes draw their children one level deeper', () => {
    const rows = [
      row('a', 'root', { child_count: 1, is_expanded: true }),
      row('a1', 'a'),
    ]
    const got = flatten(rows)
    expect(got.map((n) => n.note_id)).toEqual(['a', 'a1'])
    expect(got.map((n) => n.depth)).toEqual([0, 1])
  })

  it('the same level is sorted by position, ties broken by title', () => {
    const rows = [
      row('b', 'root', { position: 1 }),
      row('a', 'root', { position: 0 }),
      row('c', 'root', { position: 0, title: 'aa' }),
    ]
    // two with position 0 are sorted by title: 'a' before 'aa'
    expect(flatten(rows).map((n) => n.note_id)).toEqual(['a', 'c', 'b'])
  })

  it('clones: the same note draws one row in each of its two places', () => {
    const rows = [
      row('p1', 'root', { child_count: 1, is_expanded: true }),
      row('p2', 'root', { child_count: 1, is_expanded: true, position: 1 }),
      row('shared', 'p1', { branch_count: 2 }),
      row('shared', 'p2', { branch_count: 2 }),
    ]
    const got = flatten(rows)
    expect(got.filter((n) => n.note_id === 'shared')).toHaveLength(2)
  })

  it('a cycle in the data must not blow the stack', () => {
    // the backend's _would_cycle guards it, but the frontend should not assume it never leaks. Recursion on a cycle is a white screen.
    const rows = [
      row('a', 'root', { child_count: 1, is_expanded: true }),
      row('b', 'a', { child_count: 1, is_expanded: true }),
      row('a', 'b', { child_count: 1, is_expanded: true }),
    ]
    const got = flatten(rows)
    expect(got.length).toBeLessThan(20)
    expect(got.map((n) => n.note_id)).toContain('b')
  })

  it('orphan nodes are not drawn -- if the parent is not in the tree, it has no place', () => {
    expect(flatten([row('x', 'a parent that does not exist')])).toEqual([])
  })
})
