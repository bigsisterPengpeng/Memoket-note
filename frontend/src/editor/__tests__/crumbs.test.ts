import { describe, expect, it } from 'vitest'
import type { TreeRow } from '../../api'
import { buildCrumbs } from '../../util/crumbs'

const row = (note_id: string, parent_note_id: string, title: string): TreeRow => ({
  id: 'b-' + note_id, note_id, parent_note_id, position: 0, is_expanded: false, title, preview: '',
  cite_count: 0, ingested_at: '', pinned: false, updated_at: '', child_count: 0, branch_count: 1, fact_count: 0,
} as TreeRow)
const isVirtual = (id: string) => id === 'kb' || id.startsWith('kb:') || id.startsWith('app:')
const noTab = () => undefined

describe('buildCrumbs', () => {
  const rows = [row('a', 'root', 'Projects'), row('b', 'a', 'Meetings'), row('kb', 'root', 'Knowledge base'), row('kb:topics', 'kb', 'Topics'),
    row('kb:topic:work', 'kb:topics', 'work'), row('kb:facts?topic=work', 'kb:topic:work', '5734 more · see facts table')]
  it('real note: up the tree to the root', () => {
    expect(buildCrumbs('b', rows, noTab, isVirtual).map((r) => r.title)).toEqual(['Projects', 'Meetings'])
  })
  it('facts table entered from the tail row: ends with the page name', () => {
    expect(buildCrumbs('kb:facts?topic=work', rows, noTab, isVirtual).map((r) => r.title)).toEqual(['Knowledge base', 'Topics', 'work', 'Facts table · work'])
  })
  it('lazily loaded node not in the tree: parent chain built from the id shape, names from the tab', () => {
    expect(buildCrumbs('kb:entity:acme', rows, (id) => (id === 'kb:entity:acme' ? 'Acme' : undefined), isVirtual).map((r) => r.title))
      .toEqual(['Knowledge base', 'Entities', 'Acme'])
  })
  it('app:* gets no knowledge-base prefix; the knowledge-base root is not repeated; nothing open gives empty', () => {
    expect(buildCrumbs('app:trash', [], noTab, isVirtual).map((r) => r.title)).toEqual(['Trash'])
    expect(buildCrumbs('kb', [], noTab, isVirtual).map((r) => r.title)).toEqual(['Knowledge base'])
    expect(buildCrumbs(null, rows, noTab, isVirtual)).toEqual([])
  })
})
