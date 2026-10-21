import { describe, expect, it } from 'vitest'
import { EditorState } from '@codemirror/state'
import { dotWorthy, marginField, noRecordNote, paragraphsWithLines, setMarginMarks } from '../marginMemory'

describe('margin memory', () => {
  it('paragraph splitting gives the first line number of each paragraph', () => {
    expect(paragraphsWithLines('# Title\n\nPara one\nline two\n\n\nPara two\n')).toEqual([
      { text: '# Title', line: 1 }, { text: 'Para one\nline two', line: 3 }, { text: 'Para two', line: 7 },
    ])
  })
  it('line numbers follow document changes', () => {
    let s = EditorState.create({ doc: 'a\n\nb 420mAh\n', extensions: [marginField] })
    s = s.update({ effects: setMarginMarks.of([{ line: 3, relation: 'conflict', say: 'x' }]) }).state
    s = s.update({ changes: { from: 0, insert: 'A new line\n\n' } }).state
    expect(s.field(marginField)[0].line).toBe(5)
  })
  // -- P25 #4 (P22 #8): one N1 note had 106 grey dots on its 136 numbered paragraphs, 89 of them "not even a related record in the library"
  it('no grounding · not even a related record -> no dot; related but without the figure -> dot', () => {
    expect(dotWorthy({ relation: 'unsupported', why: 'no_record' })).toBe(false)
    expect(dotWorthy({ relation: 'unsupported', why: 'no_value' })).toBe(true)
    // when the backend gives no `why` (old version / other relations), always draw -- **if unrecognized, do not draw less**
    expect(dotWorthy({ relation: 'unsupported' })).toBe(true)
    for (const r of ['conflict', 'continuation', 'corroborated', 'accumulation', 'merge'] as const) {
      expect(dotWorthy({ relation: r, why: 'no_record' })).toBe(true)
    }
  })
  it('the folded tier says on the panel how many paragraphs there are', () => {
    expect(noRecordNote(89)).toContain('89 paragraphs')
    expect(noRecordNote(89)).toContain('no related records yet')
  })
})
