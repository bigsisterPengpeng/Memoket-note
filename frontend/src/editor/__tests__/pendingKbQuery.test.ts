import { beforeEach, describe, expect, it } from 'vitest'
import { setPendingKbQuery, takePendingKbQuery } from '../../util/pendingKbQuery'

describe('the word carried over by "Search the knowledge base for this"', () => {
  beforeEach(() => { takePendingKbQuery() })

  it('cleared once taken -- opening the knowledge base again should not refill last time\'s word', () => {
    setPendingKbQuery('Yan Ya')
    expect(takePendingKbQuery()).toBe('Yan Ya')
    expect(takePendingKbQuery()).toBe('')
  })

  it('empty when nobody put a word', () => {
    expect(takePendingKbQuery()).toBe('')
  })
})
