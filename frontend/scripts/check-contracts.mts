import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { checkDoneItem, splitDone } from '../src/util/doneChecks.ts'
import { notePrecondition, type NoteAction } from '../src/editor/preconditions.ts'
import { splitBeatLabel } from '../src/util/sectionStatus.ts'
import { setLang } from '../src/i18n/index.ts'

const table = JSON.parse(readFileSync(new URL('../../shared/contracts.json', import.meta.url), 'utf8'))
setLang('en')
for (const c of table.done) {
  const result = checkDoneItem(c.item, table.contents[c.content])
  assert.deepEqual(result ? { status: result.status, why: result.why } : null, c.expect, c.name)
}
for (const c of table.note) assert.equal(notePrecondition(c.action as NoteAction, c.content, c.title), c.expect, c.name)
for (const c of table.split) assert.deepEqual(splitDone(c.done), c.items)
for (const c of table.beat_labels) assert.deepEqual(splitBeatLabel(c.input), { status: c.status, text: c.text, line: c.line })
console.log(`Shared contracts passed: ${table.done.length} completion, ${table.note.length} precondition, ${table.split.length} splitting, ${table.beat_labels.length} saved-label cases`)
