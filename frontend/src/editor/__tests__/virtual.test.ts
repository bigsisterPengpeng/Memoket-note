import { describe, expect, it } from 'vitest'
import { factsLabel, isKbVirtual, isKnownVirtual, previewLine, syncVirtualTab, VIRTUAL_LABELS } from '../../util/virtual'

describe('pure rules of virtual pages', () => {
  it('factsLabel: a filtered facts table is called "Facts table · value"', () => {
    expect(factsLabel('kb:facts')).toBe('Facts table')
    expect(factsLabel('kb:facts?topic=work')).toBe('Facts table · work')
    expect(factsLabel('kb:facts?kind=plan&who=speaker%20b')).toBe('Facts table · plan · speaker b')
    expect(factsLabel('kb:topic:work')).toBeUndefined()
  })
  it('isKnownVirtual: fixed pages / knowledge-base nodes / facts tables with a query string / app:*', () => {
    for (const id of Object.keys(VIRTUAL_LABELS)) expect(isKnownVirtual(id)).toBe(true)
    for (const id of ['kb:topic:work', 'kb:entity:acme', 'kb:facts?topic=work', 'kb:material:u1', 'app:trash']) expect(isKnownVirtual(id)).toBe(true)
    for (const id of ['kb:overview', 'kb:nope:x', 'note:123', '']) expect(isKnownVirtual(id)).toBe(false)
  })
  it('inside the knowledge base a single workspace tab is reused; ordinary virtual pages still open their own tabs', () => {
    const old = [
      { id: 'note', noteId: 'n1', title: 'Note' },
      { id: 'kb-a', noteId: 'kb', title: 'Knowledge base' },
      { id: 'kb-b', noteId: 'kb:fact:f1', title: 'Old fact' },
      { id: 'settings', noteId: 'app:settings', title: 'Settings' },
    ]
    const moved = syncVirtualTab(old, { id: 'new', noteId: 'kb:graph', title: 'Topic map' }, 'kb-b')
    expect(moved.filter((t) => isKbVirtual(t.noteId))).toEqual([
      { id: 'kb-b', noteId: 'kb:graph', title: 'Topic map' },
    ])
    expect(moved.map((t) => t.id)).toEqual(['note', 'kb-b', 'settings'])

    const withImport = syncVirtualTab(moved, { id: 'import', noteId: 'app:import', title: 'Import' }, 'kb-b')
    expect(withImport.map((t) => t.noteId)).toEqual(['n1', 'kb:graph', 'app:settings', 'app:import'])
  })
  it('previewLine: skips a first line equal to the title, strips markers, strips whole-note indentation; follows backend _first_body_line', () => {
    expect(previewLine('# Meeting notes 10\n- First item', 'Meeting notes 10')).toBe('First item')
    // no title: the display name is the first line "Timeline", so the preview gives the next body line
    expect(previewLine('    ## Timeline\nbody', '')).toBe('body')
    // image lines / code fences do not count; body lines win over subheadings; only with no body line at all fall back to a subheading
    expect(previewLine('# T\n![image](/api/assets/a.png)\n```\ncode\n```\n## Subheading\n**Key** sentence', 'T')).toBe('Key sentence')
    expect(previewLine('# T\n## Only a subheading', 'T')).toBe('Only a subheading')
    expect(previewLine('', '')).toBe('')
  })
})
