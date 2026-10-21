import { describe, expect, it } from 'vitest'
import { EditorState } from '@codemirror/state'
import { acceptLayer, addLayer, diffParts, dropHunk, layersOf, roundDiffField } from '../roundDiff'

function mk(doc: string) { return EditorState.create({ doc, extensions: [roundDiffField] }) }
import { minimalChange } from '../minimalChange'
function push(state: EditorState, label: string, before: string, after: string) {
  // Only swap the part that really changed (the layer above uses minimalChange): replacing the whole note maps all old-layer positions onto one point, and the old layers vanish
  const change = minimalChange(before, after)
  return state.update({ changes: change ?? [], effects: addLayer.of({ label, parts: diffParts(before, after) }) }).state
}

describe('proposal layers', () => {
  it('two actions are two layers, each remembering its own hunks', () => {
    let s = mk('\u7532\u4e59\u4e19\u4e01')   // CJK is diffed per character
    s = push(s, 'Polish', '\u7532\u4e59\u4e19\u4e01', '\u7532\u4e59X\u4e19\u4e01')
    s = push(s, 'Rewrite', '\u7532\u4e59X\u4e19\u4e01', '\u7532\u4e59X\u4e19\u4e01Y')
    const st = s.field(roundDiffField)
    expect(st.layers.map((l) => l.label)).toEqual(['Polish', 'Rewrite'])
    expect(st.hunks.length).toBe(2)
    expect(new Set(st.hunks.map((h) => h.layer)).size).toBe(2)
  })
  it('accepting one layer removes only that layer; reverting the other restores the document', () => {
    let s = mk('\u7532\u4e59\u4e19\u4e01')
    s = push(s, 'Polish', '\u7532\u4e59\u4e19\u4e01', '\u7532\u4e59X\u4e19\u4e01')
    s = push(s, 'Rewrite', '\u7532\u4e59X\u4e19\u4e01', '\u7532\u4e59X\u4e19\u4e01Y')
    const [l1, l2] = s.field(roundDiffField).layers
    s = s.update({ effects: acceptLayer.of(l1.id) }).state
    // **On the panel** only l2 remains. Since P39 the field's `layers` keeps the handled layer
    // (it still carries the "N handled" ledger, which must be persisted); whether it is listed is up to `layersOf`.
    expect(layersOf({ state: s, dispatch: () => {} }).map((l) => l.id)).toEqual([l2.id])
    // revert l2: restore its hunks
    const h = s.field(roundDiffField).hunks.find((x) => x.layer === l2.id)!
    s = s.update({ changes: { from: h.from, to: h.to, insert: h.del }, effects: dropHunk.of(h.id) }).state
    expect(s.doc.toString()).toBe('\u7532\u4e59X\u4e19\u4e01')
    expect(layersOf({ state: s, dispatch: () => {} })).toEqual([])
  })
  it('replace clears existing layers (the cumulative diff of Smart Continue)', () => {
    let s = mk('\u7532\u4e59\u4e19\u4e01')
    s = push(s, 'Polish', '\u7532\u4e59\u4e19\u4e01', '\u7532\u4e59X\u4e19\u4e01')
    s = s.update({ effects: addLayer.of({ label: 'Smart Continue', parts: diffParts('\u7532\u4e59X\u4e19\u4e01', '\u7532\u4e59X\u4e19\u4e01'), replace: true }) }).state
    expect(s.field(roundDiffField).layers).toEqual([])
    expect(s.field(roundDiffField).settled).toEqual([])          // replace clears the handled-changes ledger too
  })
})
