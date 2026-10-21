/** A running AI block: a placeholder block at the cursor; open it to see what it is doing.
 *
 * Why not a toast floating in a corner:
 *
 * · **Position**: `/` can fire anywhere in the document, and the output lands there. The farther the status is from the output,
 *   the harder it is to see "which block is running" -- especially with several running at once.
 * · **Concurrency**: a placeholder carries its own position, mapped along with document edits, so several can run at once
 *   without stepping on each other. The old version had a single global slashBusy, **only one could run at a time**.
 * · **No streaming into the body**: content being generated is previewed only inside the placeholder, and lands in the body all at once when done.
 *   Streaming straight into the document would interleave the text of several concurrent tasks.
 */
import { StateEffect, StateField, type Range } from '@codemirror/state'
import { Decoration, EditorView, WidgetType } from '@codemirror/view'
import { t } from '../i18n'

export type RunLog = { at: string; text: string }

export type RunState = {
  id: string
  /** Where the output should land in the document. Mapped through every document change. */
  from: number
  label: string
  phase: string
  /** Preview of the streamed output. Shown only inside the placeholder, never in the body. */
  preview: string
  log: RunLog[]
  expanded: boolean
  error: string

  retry?: boolean
}

export const startRun = StateEffect.define<{ id: string; from: number; label: string }>()
export const patchRun = StateEffect.define<{ id: string } & Partial<Omit<RunState, 'id'>>>()
export const appendPreview = StateEffect.define<{ id: string; text: string }>()
export const logRun = StateEffect.define<{ id: string; at: string; text: string }>()
export const endRun = StateEffect.define<string>()
export const toggleRun = StateEffect.define<string>()

export const runsField = StateField.define<RunState[]>({
  create: () => [],
  update(runs, tr) {
    let next = runs
    for (const e of tr.effects) {
      if (e.is(startRun)) {
        next = [...next, { ...e.value, phase: '', preview: '', log: [], expanded: false, error: '' }]
      } else if (e.is(endRun)) {
        next = next.filter((r) => r.id !== e.value)
      } else if (e.is(toggleRun)) {
        next = next.map((r) => (r.id === e.value ? { ...r, expanded: !r.expanded } : r))
      } else if (e.is(patchRun)) {
        next = next.map((r) => (r.id === e.value.id ? { ...r, ...e.value } : r))
      } else if (e.is(appendPreview)) {
        next = next.map((r) => (r.id === e.value.id
          ? { ...r, preview: r.preview + e.value.text } : r))
      } else if (e.is(logRun)) {
        next = next.map((r) => (r.id === e.value.id
          ? { ...r, log: [...r.log, { at: e.value.at, text: e.value.text }] } : r))
      }
    }
    if (tr.docChanged && next.length) {
      // The position follows document changes. assoc=1: text inserted exactly at this position goes **before** the placeholder,
      // i.e. when the user keeps typing above the placeholder, the output's landing point moves down with it.
      next = next.map((r) => ({ ...r, from: tr.changes.mapPos(r.from, 1) }))
    }
    return next === runs ? runs : next
  },
})

/** Stop a given run. Injected by App -- the extension should not know about AbortController. */
export type StopRun = (id: string) => void
/** Rerun as-is. Also injected by App (only it knows which item, what instruction, where it lands). */
export type RetryRun = (id: string) => void

class RunWidget extends WidgetType {
  constructor(readonly run: RunState, readonly stop: StopRun, readonly retry: RetryRun) { super() }

  eq(o: RunWidget) {
    const a = this.run
    const b = o.run
    return a.id === b.id && a.phase === b.phase && a.expanded === b.expanded
      && a.preview.length === b.preview.length && a.log.length === b.log.length
      && a.error === b.error && a.retry === b.retry
  }

  toDOM(view: EditorView) {
    const r = this.run
    const wrap = document.createElement('div')
    wrap.className = 'cm-run-block' + (r.error ? ' has-error' : '')

    const head = document.createElement('div')
    head.className = 'cm-run-head'
    const spin = document.createElement('span')
    spin.className = r.error ? 'cm-run-bad' : 'spinner'
    spin.textContent = r.error ? '!' : ''
    const title = document.createElement('span')
    title.className = 'cm-run-title'
    title.textContent = r.label
    const phase = document.createElement('span')
    phase.className = 'cm-run-phase'
    phase.textContent = r.error || r.phase || t('Running…')
    const chev = document.createElement('span')
    chev.className = 'cm-run-chev'
    chev.textContent = r.expanded ? '▾' : '▸'
    const stop = document.createElement('button')
    stop.type = 'button'
    stop.className = 'cm-run-stop'
    stop.textContent = t('Stop')
    stop.addEventListener('mousedown', (e) => {
      e.preventDefault()
      e.stopPropagation()
      this.stop(r.id)
    })
    head.append(chev, spin, title, phase)
    // For the wrong-shape failures, give a "Retry" -- what the user sees is a plain sentence + a clickable button,

    if (r.retry && r.error) {
      const again = document.createElement('button')
      again.type = 'button'
      again.className = 'cm-run-retry'
      again.textContent = t('Retry')
      again.addEventListener('mousedown', (e) => {
        e.preventDefault()
        e.stopPropagation()
        this.retry(r.id)
      })
      head.append(again)
    }
    head.append(stop)
    head.addEventListener('mousedown', (e) => {
      e.preventDefault()
      view.dispatch({ effects: toggleRun.of(r.id) })
    })
    wrap.append(head)

    if (r.expanded) {
      const body = document.createElement('div')
      body.className = 'cm-run-body'
      if (r.log.length) {
        const ul = document.createElement('ul')
        ul.className = 'cm-run-log'
        for (const l of r.log) {
          const li = document.createElement('li')
          const at = document.createElement('span')
          at.className = 'cm-run-at'
          at.textContent = l.at
          li.append(at, document.createTextNode(l.text))
          ul.append(li)
        }
        body.append(ul)
      }
      if (r.preview.trim()) {
        const pre = document.createElement('pre')
        pre.className = 'cm-run-preview'
        // Show only the tail: a block may be thousands of characters, stuffing it all into the placeholder would push the editor apart
        pre.textContent = r.preview.length > 1200
          ? '…' + r.preview.slice(-1200) : r.preview
        body.append(pre)
      }
      if (!r.log.length && !r.preview.trim()) {
        const empty = document.createElement('div')
        empty.className = 'cm-run-empty'
        empty.textContent = t('No output yet')
        body.append(empty)
      }
      wrap.append(body)
    }
    return wrap
  }

  // There are buttons inside to click, so events must not be swallowed
  ignoreEvent() { return false }
}

export function runningBlocks(stop: StopRun, retry: RetryRun = () => {}) {
  const decos = EditorView.decorations.compute([runsField, 'doc'], (state) => {
    const runs = state.field(runsField)
    if (!runs.length) return Decoration.none
    const len = state.doc.length
    const out: Range<Decoration>[] = runs
      .map((r) => Decoration.widget({
        widget: new RunWidget(r, stop, retry), side: -1, block: true,
      }).range(Math.max(0, Math.min(r.from, len))))
    // With several at the same position they must be sorted by position, otherwise CM6 throws "Ranges must be sorted"
    out.sort((a, b) => a.from - b.from)
    return Decoration.set(out, true)
  })
  return [runsField, decos]
}
