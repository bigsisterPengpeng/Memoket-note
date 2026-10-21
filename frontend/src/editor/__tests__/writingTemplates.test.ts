/**
 * Writing template catalogue (104 templates, 12 categories): data integrity and bilingual coverage.
 *
 * The catalogue stores English source text; every string is also the key of its Chinese
 * translation in `i18n/zh/templates.ts`. These strings are not literal `t('...')` calls, so the
 * check-i18n gate cannot see them -- **this file proves each one has a Chinese entry**.
 */
import { afterEach, describe, expect, it } from 'vitest'

import { ICONS } from '../../components/Icon'
import { getLang, hasZh, setLang } from '../../i18n'
import { ZH } from '../../i18n/zh'
import { EMPTY_INTENT, INTENT_FIELD_MAX, WORKFLOW_LABEL, intentText } from '../../util/docIntent'
import { checkDone } from '../../util/doneChecks'
import {
  TEMPLATE_CATEGORIES, WRITING_TEMPLATES, localizeTemplate, missingTemplateScaffold, searchTemplates,
  templateStrings, templatesIn, writingTemplate,
} from '../writingTemplates'

const HAN = /[\u3400-\u9fff]/
const heads = (scaffold: string) => scaffold.split('\n').filter((l) => l.startsWith('## ')).map((l) => l.slice(3))

/** Section headings of the four originals: the backend `harness/workflows.py` names exactly these. */
const ORIGINALS: Record<string, string> = {
  daily: "## Today's results\n\n## Key progress and decisions\n\n## Blockers and support needed\n\n## Tomorrow's priorities",
  weekly: "## This week's results\n\n## Key progress and decisions\n\n## Risks and blockers\n\n## Next week's focus",
  journal: '## What happened today\n\n## How I felt and what I judged\n\n## For my future self',
  meeting: '## Context\n\n## Decisions\n\n## Action items\n\n## Open questions',
}

describe('writing template catalogue', () => {
  afterEach(() => setLang('en'))

  it('exactly 104: 4 favorites + 100 across 11 categories, 8-12 each, unique snake_case ids', () => {
    expect(WRITING_TEMPLATES).toHaveLength(104)
    expect(WRITING_TEMPLATES.filter((x) => x.category !== 'favorites')).toHaveLength(100)
    expect(templatesIn('favorites').map((x) => x.id)).toEqual(['daily', 'weekly', 'journal', 'meeting'])
    const ids = WRITING_TEMPLATES.map((x) => x.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const id of ids) expect(id).toMatch(/^[a-z][a-z0-9_]*$/)
    expect(TEMPLATE_CATEGORIES).toHaveLength(12)
    for (const c of TEMPLATE_CATEGORIES) {
      const n = templatesIn(c.id).length
      if (c.id === 'favorites') expect(n).toBe(4)
      else expect(n, c.id).toBeGreaterThanOrEqual(8)
      expect(n, c.id).toBeLessThanOrEqual(12)
    }
    const known = new Set(TEMPLATE_CATEGORIES.map((c) => c.id))
    for (const x of WRITING_TEMPLATES) expect(known.has(x.category), x.id).toBe(true)
  })

  it('every icon is in the Icon.tsx ICONS table (not in the table = nothing drawn)', () => {
    for (const x of WRITING_TEMPLATES) expect(ICONS[x.icon], `${x.id}: ${x.icon}`).toBeDefined()
  })

  it('scaffolds have 3-5 level-two headings; scaffolds, hints, done criteria and labels are all distinct', () => {
    const scaffolds = new Set<string>(); const hints = new Set<string>(); const dones = new Set<string>(); const labels = new Set<string>()
    for (const x of WRITING_TEMPLATES) {
      const h = heads(x.scaffold)
      expect(h.length, x.id).toBeGreaterThanOrEqual(3)
      expect(h.length, x.id).toBeLessThanOrEqual(5)
      expect(x.scaffold.split('\n').filter((l) => l.trim() && !l.startsWith('## ')), x.id).toEqual([])
      scaffolds.add(x.scaffold); hints.add(x.hint); dones.add(x.intent.done); labels.add(x.label)
      for (const k of ['retrieve', 'write', 'verify', 'finish'] as const) expect(x.contract[k], `${x.id}.${k}`).not.toBe('')
    }
    expect(scaffolds.size).toBe(104)
    expect(hints.size).toBe(104)
    expect(dones.size).toBe(104)
    expect(labels.size).toBe(104)
  })

  it('the catalogue source is English (no Han characters in any template string)', () => {
    for (const x of WRITING_TEMPLATES) for (const s of templateStrings(x)) expect(s, x.id).not.toMatch(HAN)
    for (const c of TEMPLATE_CATEGORIES) expect(c.label).not.toMatch(HAN)
  })

  it('workflow: originals use their own id, category templates the category id; the shared text carries it', () => {
    for (const x of WRITING_TEMPLATES) {
      expect(x.intent.workflow).toBe(x.category === 'favorites' ? x.id : x.category)
      expect(WORKFLOW_LABEL[x.intent.workflow!], x.id).toBeTruthy()
      expect(intentText({ ...x.intent, source: 'user' })).toMatch(new RegExp(`^Workflow: ${x.intent.workflow}; Goal: `))
    }
    // An unknown id does not leave a "Workflow: undefined" in the text
    expect(intentText({ ...EMPTY_INTENT, goal: 'x', source: 'user', workflow: 'nope' })).toBe('Goal: x')
  })

  it('the three intent fields fit the field cap in both languages (backend FIELD_MAX is the same; longer is silently cut)', () => {
    for (const x of WRITING_TEMPLATES) {
      for (const k of ['goal', 'reader', 'done'] as const) {
        expect(x.intent[k].length, `${x.id}.${k}`).toBeLessThanOrEqual(INTENT_FIELD_MAX)
        expect((ZH[x.intent[k]] ?? '').length, `${x.id}.${k} (zh)`).toBeLessThanOrEqual(INTENT_FIELD_MAX)
      }
    }
  })

  it('done criteria start by naming every scaffold section (English: "Sections: A, B, C;")', () => {
    for (const x of WRITING_TEMPLATES) {
      expect(x.intent.done.startsWith(`Sections: ${heads(x.scaffold).join(', ')};`), x.id).toBe(true)
    }
  })

  it('in Chinese, doneChecks judges the section clause of every category template on the spot', () => {
    setLang('zh')
    for (const raw of WRITING_TEMPLATES.filter((x) => x.category !== 'favorites')) {
      const x = localizeTemplate(raw)
      const [withScaffold] = checkDone(x.intent.done, x.scaffold)
      expect(withScaffold.status, `${x.id}: ${withScaffold.why}`).toBe('pass')
      const [empty] = checkDone(x.intent.done, '')
      expect(empty.status, x.id).toBe('fail')
    }
  })

  it('every English string has a Chinese entry: ten per template, category labels, workflow labels', () => {
    const missing: string[] = []
    for (const x of WRITING_TEMPLATES) for (const s of templateStrings(x)) if (!hasZh(s)) missing.push(`${x.id}: ${s.slice(0, 30)}`)
    for (const c of TEMPLATE_CATEGORIES) if (!hasZh(c.label)) missing.push(`category ${c.id}`)
    for (const [id, label] of Object.entries(WORKFLOW_LABEL)) if (!hasZh(label)) missing.push(`workflow ${id}`)
    expect(missing).toEqual([])
  })

  it('the Chinese scaffold keeps the same number of sections as the English one', () => {
    for (const x of WRITING_TEMPLATES) expect(heads(ZH[x.scaffold]).length, x.id).toBe(heads(x.scaffold).length)
  })

  it('the four originals keep their headings (backend workflows.py names these sections)', () => {
    for (const [id, scaffold] of Object.entries(ORIGINALS)) expect(writingTemplate(id).scaffold).toBe(scaffold)
    expect(writingTemplate('journal').contract.finish).toBe('Hands the pen back after at most two passes; it never declares your journal finished')
  })

  it('search: English and Chinese, case-insensitive, within a category, empty returns all', () => {
    const monthly = WRITING_TEMPLATES.find((x) => x.id === 'monthly_report')!
    expect(searchTemplates(ZH[monthly.label]).map((x) => x.id)).toContain('monthly_report')
    expect(searchTemplates('Monthly').map((x) => x.id)).toContain('monthly_report')
    expect(searchTemplates('monthly REPORT').map((x) => x.id)).toContain('monthly_report')
    expect(searchTemplates('postmortem').map((x) => x.id)).toContain('incident_postmortem')
    expect(searchTemplates('xyzzy-no-such')).toEqual([])
    expect(searchTemplates('', 'favorites')).toHaveLength(4)
    const daily = WRITING_TEMPLATES.find((x) => x.id === 'daily')!
    expect(searchTemplates(ZH[daily.label], 'favorites').map((x) => x.id)).toEqual(['daily'])
    expect(searchTemplates('runbook', 'personal')).toEqual([])
    // Chinese search works in the English UI and English search in the Chinese UI
    setLang('zh')
    expect(searchTemplates('postmortem').map((x) => x.id)).toContain('incident_postmortem')
  })

  it('English UI is the default: writingTemplate() is the English source; intent text keeps the id', () => {
    expect(getLang()).toBe('en')
    const daily = writingTemplate('daily')
    expect(daily.label).toBe('Daily report template')
    expect(daily.intent.workflow).toBe('daily')
    expect(intentText({ ...daily.intent, source: 'user' })).toMatch(/^Workflow: daily; Goal: Turn today/)
    const prd = writingTemplate('prd')
    expect(prd.scaffold.split('\n\n')).toHaveLength(5)
    // Picking the same template again on an English scaffold only adds the missing English sections
    expect(missingTemplateScaffold(prd, '## Problem\n\ntext')).not.toContain('## Problem')
    expect(missingTemplateScaffold(prd, '## Problem\n\ntext')).toContain('## Success metrics')
    // In English localizeTemplate is the identity
    const raw = WRITING_TEMPLATES.find((x) => x.id === 'prd')!
    expect(localizeTemplate(raw)).toEqual(raw)
  })

  it('Chinese UI: writingTemplate() gives the Chinese scaffold and intent; the workflow id and the intent field labels stay', () => {
    setLang('zh')
    const raw = WRITING_TEMPLATES.find((x) => x.id === 'daily')!
    const daily = writingTemplate('daily')
    expect(daily.label).toBe(ZH[raw.label])
    expect(daily.scaffold).toBe(ZH[raw.scaffold])
    expect(daily.scaffold).toMatch(HAN)
    expect(daily.intent.workflow).toBe('daily')
    expect(daily.intent.goal).toBe(ZH[raw.intent.goal])
    expect(intentText({ ...daily.intent, source: 'user' })).toMatch(/^Workflow: daily; Goal: /)
  })
})
