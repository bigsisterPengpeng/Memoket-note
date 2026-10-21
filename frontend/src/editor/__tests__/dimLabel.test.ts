import { describe, expect, it } from 'vitest'
import { checkLabel, dimLabel } from '../dimLabel'

describe('dimLabel', () => {
  it('the hard-coded dimensions have display names', () => {
    expect(dimLabel('non_repetition')).toBe('No repetition')
    expect(dimLabel('follows_prompt')).toBe('Follows your instruction')
    expect(dimLabel('workflow_fidelity')).toBe('Workflow quality')
  })

  it('the ones generated on the spot must not show text like checklist_1', () => {
    // backend `harness/checklist.py` names them `checklist_<n>` (dimension names are JSON keys the scorer must
    // reproduce verbatim, and long CJK sentences as keys get rewritten too easily) -- the nice names are added in this layer.
    expect(dimLabel('checklist_1')).toBe('Your requirement 1')
    expect(dimLabel('checklist_12')).toBe('Your requirement 12')
  })

  it('the criteria\'s fallback bucket has its own name and must not borrow coherence', () => {
    // plan 4.4: `mechanics` is not a scoring dimension, it is "a code criterion caught a mechanical defect".
    // Borrowing `coherence` as the fallback made the UI say "Coherence 0 points", while in that round
    // the scorer never ran once.
    expect(dimLabel('mechanics')).toBe('Mechanical defect')
  })

  it('unknown dimensions are shown raw, not blank', () => {
    expect(dimLabel('future_dimension')).toBe('future_dimension')
  })

  it('template-specific criteria do not expose internal function names to users', () => {
    expect(checkLabel('workflow_quality')).toBe('Template sections and categories')
  })
})
