import { afterEach, describe, expect, it } from 'vitest'
import { setLang } from '../../i18n'
import { checkDone } from '../../util/doneChecks'
import { WRITING_TEMPLATES } from '../writingTemplates'

afterEach(() => setLang('en'))
describe('English section criteria', () => {
  it('requires every named heading and accepts headings longer than eight characters', () => {
    const criterion = 'Sections: Project scope, Risks and blockers; Keep decisions explicit'
    expect(checkDone(criterion, '## Project scope\n\nA paragraph')[0]).toMatchObject({ status: 'fail', why: 'Missing headings: Risks and blockers' })
    expect(checkDone(criterion, '## PROJECT SCOPE\n\nA paragraph\n\n## Risks and blockers\n\nB paragraph')[0]).toMatchObject({ status: 'pass', why: 'All 2 sections present' })
  })
  it('checks the shipped English template criteria against their own scaffolds', () => {
    for (const template of WRITING_TEMPLATES.filter((t) => t.intent.done.startsWith('Sections:'))) {
      expect(checkDone(template.intent.done, '')[0].status, template.id).toBe('fail')
      expect(checkDone(template.intent.done, template.scaffold)[0].status, template.id).toBe('pass')
    }
  })
})
