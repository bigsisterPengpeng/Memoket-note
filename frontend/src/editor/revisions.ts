import { StateEffect, StateField, type Range } from '@codemirror/state'
import { Decoration, EditorView, type DecorationSet } from '@codemirror/view'
import type { Revision } from '../api'
import { t } from '../i18n'

/** Revisions live in React state, outside CM6's own document -- this effect
 * is how the React wrapper pushes a fresh list in whenever it changes. */
export const setRevisions = StateEffect.define<Revision[]>()

/** Same overlap rule as the old HighlightedEditor: two anchors can't both
 * own a range, so the earlier one wins and the rest stay list-only. */
function buildRanges(doc: string, revisions: Revision[]): { from: number; to: number; revision: Revision }[] {
  const matches = revisions
    .filter((r) => r.anchor && doc.includes(r.anchor))
    .map((r) => {
      const from = doc.indexOf(r.anchor)
      return { from, to: from + r.anchor.length, revision: r }
    })
    .sort((a, b) => a.from - b.from)

  const out: typeof matches = []
  let lastEnd = -1
  for (const m of matches) {
    if (m.from >= lastEnd) { out.push(m); lastEnd = m.to }
  }
  return out
}

function classFor(op: Revision['op']): string {
  return op === 'delete' ? 'del' : (op === 'insert' || op === 'insert_before') ? 'ins' : 'replace'
}

function tooltipFor(r: Revision): string {
  const base = r.op === 'insert' ? t('Click to accept: insert “{text}” after this', { text: r.text })
    : r.op === 'insert_before' ? t('Click to accept: insert “{text}” before this', { text: r.text })
    : r.op === 'delete' ? t('Click to accept: delete this passage')
    : t('Click to accept: replace with “{text}”', { text: r.text })
  return r.reason ? `${base}\n${t('Reason: {reason}', { reason: r.reason })}` : base
}

export const revisionField = StateField.define<{ list: Revision[]; decos: DecorationSet }>({
  create() {
    return { list: [], decos: Decoration.none }
  },
  update(value, tr) {
    let list = value.list
    for (const effect of tr.effects) {
      if (effect.is(setRevisions)) list = effect.value
    }
    if (!tr.docChanged && list === value.list) return value
    if (list.length === 0) return { list, decos: Decoration.none }
    const doc = tr.state.doc.toString()
    const ranges = buildRanges(doc, list)
    const decos: Range<Decoration>[] = ranges.map((r) =>
      Decoration.mark({
        class: classFor(r.revision.op),
        attributes: { title: tooltipFor(r.revision), 'data-revision-id': r.revision.id },
      }).range(r.from, r.to === r.from ? r.to + 1 : r.to))
    return { list, decos: Decoration.set(decos, true) }
  },
  provide: (f) => EditorView.decorations.from(f, (v) => v.decos),
})

/** Click handling reads the clicked DOM node's data-revision-id rather than
 * recomputing hit-testing against the range list -- CM6 already rendered the
 * mark as a real element, so this is simpler and can't drift from what's on
 * screen. */
export function revisionClickHandler(onAccept: (id: string) => void) {
  return EditorView.domEventHandlers({
    mousedown(event, _view) {
      const target = event.target as HTMLElement
      const id = target?.closest?.('[data-revision-id]')?.getAttribute('data-revision-id')
      if (id) {
        event.preventDefault()
        onAccept(id)
        return true
      }
      return false
    },
  })
}
