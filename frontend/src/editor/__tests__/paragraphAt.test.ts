import { describe, expect, it } from 'vitest'
import { Text } from '@codemirror/state'
import { paragraphAt } from '../../components/MarkdownEditor'

describe('paragraphAt', () => {
  const doc = Text.of(['# Title', '', 'Para one line one', 'Para one line two', '', 'Para two', ''])
  it('cursor inside a paragraph: the whole paragraph (between blank lines)', () => {
    expect(paragraphAt(doc, doc.line(3).from + 2)).toBe('Para one line one\nPara one line two')
  })
  it('a heading counts as its own paragraph; a blank line gives an empty string', () => {
    expect(paragraphAt(doc, 1)).toBe('# Title')
    expect(paragraphAt(doc, doc.line(2).from)).toBe('')
  })
})
