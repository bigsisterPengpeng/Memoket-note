import type { DocIntent } from '../util/docIntent'
import { t } from '../i18n'
import { ZH } from '../i18n/zh'
import { TEMPLATE_CATALOG } from './writingTemplateCatalog'

/**
 * Writing templates inside the editor.
 *
 * A template is not another Harness: the visible part is a Markdown scaffold the user can keep
 * editing, the hidden part is just a Doc Intent the existing Harness already understands. When
 * the user picks one, both land together; planning, retrieval, writing and checks still run
 * through the same note harness.
 *
 * 104 templates in 12 categories (`writingTemplateCatalog.ts`). The four originals (daily /
 * weekly / journal / meeting) each have their own backend contract; the other 100 share one
 * contract per **category** -- `intent.workflow` is the category id, the backend
 * `harness/workflows.py` picks the Recipe by it, and the sections come from the template's own
 * scaffold.
 *
 * English is the source text: the catalogue stores English, the Chinese lives in
 * `i18n/zh/templates.ts`. Fields that reach the body or the intent go through
 * `writingTemplate()` to get the current-language copy; `WRITING_TEMPLATES` itself is always
 * the English source.
 */
export type WritingTemplateId = string

export type WritingTemplateCategoryId =
  | 'favorites' | 'reports' | 'meetings' | 'product' | 'research' | 'writing'
  | 'personal' | 'sales' | 'engineering' | 'people' | 'learning' | 'ops'

export type WritingTemplate = {
  id: WritingTemplateId
  category: WritingTemplateCategoryId
  label: string
  hint: string
  icon: string
  scaffold: string
  /** Execution summary shown in the UI; the full rules are enforced by the backend harness/workflows.py. */
  contract: { retrieve: string; write: string; verify: string; finish: string }
  intent: Pick<DocIntent, 'workflow' | 'goal' | 'reader' | 'done'>
}

/** Category order is the tab order in the picker; "Favorites" holds the four originals. Labels are English keys, shown through `t()`. */
export const TEMPLATE_CATEGORIES: { id: WritingTemplateCategoryId; label: string }[] = [
  { id: 'favorites', label: 'Favorites' },
  { id: 'reports', label: 'Reports' },
  { id: 'meetings', label: 'Meetings' },
  { id: 'product', label: 'Product' },
  { id: 'research', label: 'Research' },
  { id: 'writing', label: 'Writing' },
  { id: 'personal', label: 'Personal' },
  { id: 'sales', label: 'Sales & marketing' },
  { id: 'engineering', label: 'Engineering' },
  { id: 'people', label: 'People' },
  { id: 'learning', label: 'Learning & teaching' },
  { id: 'ops', label: 'Operations & finance' },
]

export const WRITING_TEMPLATES: WritingTemplate[] = TEMPLATE_CATALOG

/** Every string of a template that people see or that reaches the body / intent (the dictionary coverage test checks each one). */
export function templateStrings(template: WritingTemplate): string[] {
  return [
    template.label, template.hint, template.scaffold,
    template.contract.retrieve, template.contract.write, template.contract.verify, template.contract.finish,
    template.intent.goal, template.intent.reader, template.intent.done,
  ]
}

/** A copy of the template in the current UI language: scaffold, labels, contract and the three
 *  intent fields are translated; `workflow` is a stable id and stays. The intent fields follow the
 *  UI language -- a Chinese user sees Chinese in "Custom writing task"; the shared intent text only
 *  carries field labels and the workflow id, which `intentText` keeps in English. */
export function localizeTemplate(template: WritingTemplate): WritingTemplate {
  return {
    ...template,
    label: t(template.label),
    hint: t(template.hint),
    scaffold: t(template.scaffold),
    contract: {
      retrieve: t(template.contract.retrieve),
      write: t(template.contract.write),
      verify: t(template.contract.verify),
      finish: t(template.contract.finish),
    },
    intent: {
      workflow: template.intent.workflow,
      goal: t(template.intent.goal),
      reader: t(template.intent.reader),
      done: t(template.intent.done),
    },
  }
}

/** Template by id -- returns the **current-language** copy (App uses it to insert the scaffold and set the intent). */
export function writingTemplate(id: WritingTemplateId): WritingTemplate {
  const found = WRITING_TEMPLATES.find((template) => template.id === id)
  if (!found) throw new Error(`unknown writing template: ${id}`)
  return localizeTemplate(found)
}

export function templatesIn(category: WritingTemplateCategoryId): WritingTemplate[] {
  return WRITING_TEMPLATES.filter((template) => template.category === category)
}

function fold(s: string): string {
  return s.toLowerCase().replace(/\s+/g, '')
}

/** Search label and hint in English and Chinese (whatever the UI language), ignoring case and
 *  whitespace; an empty query returns everything. With `category` only that category is searched;
 *  the picker searches across categories while the box has text. */
export function searchTemplates(query: string, category?: WritingTemplateCategoryId): WritingTemplate[] {
  const pool = category ? templatesIn(category) : WRITING_TEMPLATES
  const q = fold(query)
  if (!q) return pool
  return pool.filter((template) => {
    const hay = [template.label, template.hint, ZH[template.label] ?? '', ZH[template.hint] ?? '']
    return hay.some((s) => fold(s).includes(q))
  })
}

/** Insert the template at the cursor, keeping exactly one blank line to the text before and after. */
export function templateTextAt(template: WritingTemplate, before: string, after: string): string {
  const left = before && !before.endsWith('\n\n') ? (before.endsWith('\n') ? '\n' : '\n\n') : ''
  const right = after && !after.startsWith('\n\n') ? (after.startsWith('\n') ? '\n' : '\n\n') : ''
  return `${left}${template.scaffold}${right}`
}

/** With existing text only the missing sections are added, so choosing the same mode again does not repeat the headings. */
export function missingTemplateScaffold(template: WritingTemplate, content: string): string {
  const existing = new Set(Array.from(content.matchAll(/^##\s+(.+?)\s*$/gm), (m) => m[1].trim()))
  return template.scaffold
    .split(/\n(?=##\s+)/)
    .filter((section) => {
      const title = /^##\s+(.+?)\s*(?:\n|$)/.exec(section)?.[1]?.trim()
      return !!title && !existing.has(title)
    })
    .join('\n')
}
