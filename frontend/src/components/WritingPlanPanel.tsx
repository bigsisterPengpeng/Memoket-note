import { useEffect, useRef, useState } from 'react'
import { memoryScope, SCOPE_LABEL } from '../api'
import { displayTitle } from '../util/displayTitle'
import { friendlyError } from '../util/friendlyError'
import * as api from '../api'
import type { TreeRow, WritingPlan, WritingSection } from '../api'
import type { HarnessState } from '../App'
import { toast } from '../toast'
import Icon from './Icon'
import { t } from '../i18n'

/** Status uses icons + semantic colors, not emoji: **emoji cannot take token colors**, they stay the same
 *  colored blobs in dark mode, while "done" should be --ins and "writing" should be --brand. */
const STATUS_ICON: Record<WritingSection['status'], string> = {
  pending: 'bx-circle', in_progress: 'bx-loader-circle', done: 'bx-check-circle',
}
const STATUS_TEXT: Record<WritingSection['status'], string> = {
  pending: 'To write', in_progress: 'Writing', done: 'Done',
}
const STATUS_COLOR: Record<WritingSection['status'], string> = {
  pending: 'var(--ink-3)', in_progress: 'var(--brand)', done: 'var(--ins)',
}

/**
 * The subtree-level endless-writing harness console: set a goal -> split into sections automatically -> write one section
 * after another (each section lands as a note) -> after the known sections are written, check automatically whether there are more,
 * and only truly stop when there are none. A different thing from the note-level magic tap, so it is a separate entry point, not
 * a button in the editor toolbar.
 *
 * The run state (harness) is held by App, not this component's own state -- closing this
 * panel does not stop a running harness (answering "must the writing plan page stay open?? can't it run in
 * the background?"); this is just a view to "watch and control that state". When there is no active
 * harness (or the active one is another folder's), pull this folder's current
 * plan/sections locally for a "static" display.
 */
export default function WritingPlanPanel({ parent, onClose, onNoteChanged, harness, onRun, onToggleFollow, confirm }: {
  parent: TreeRow
  onClose: () => void
  onNoteChanged: () => void
  harness: HarnessState | null
  onRun: () => void
  onToggleFollow: () => void
  /** App's confirm dialog (the same one as deleting a subtree); this used to be window.confirm, which in Electron pops a native system box that does not match the rest of the UI, especially jarring in dark mode. */
  confirm: (req: { title: string; detail?: string; okLabel?: string; danger?: boolean }) => Promise<boolean>
}) {
  const [localPlan, setLocalPlan] = useState<WritingPlan | null>(null)
  const [localSections, setLocalSections] = useState<WritingSection[]>([])
  const [goal, setGoal] = useState('')

  const startAbort = useRef<AbortController | null>(null)
  const scope = memoryScope()   // reading it once when the dialog opens is enough: scope is switched in the right pane, then reopen
  const scopeLabel = scope === 'all' ? '' : t(SCOPE_LABEL[scope]).replace(/ only$/, '').replace(/^\u53ea\u770b/, '')
  const [starting, setStarting] = useState(false)

  const isActive = harness?.folderId === parent.note_id
  const plan = isActive ? harness.plan : localPlan
  const sections = isActive ? harness.sections : localSections
  const running = isActive && harness.running

  // Esc closes the panel (all Trilium dialogs close on Esc). When a confirm dialog is stacked on top, Esc only closes the confirm:
  // the confirm intercepts the event itself, so defaultPrevented seen here is true.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !e.defaultPrevented) onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    api.getWritingPlan(parent.note_id).then((r) => {
      setLocalPlan(r.plan)
      setLocalSections(r.sections)
    }).catch((e) => toast(t('Could not load the writing plan: {err}', { err: friendlyError(e) }), 'error'))
  }, [parent.note_id])

  // When the harness updates this folder's plan/sections (once running), sync a copy
  // locally, so even if the panel is closed and reopened midway, or you switch to another folder's harness,
  // this folder's "static" view is still current and does not fall back to the old snapshot from when the panel opened.
  useEffect(() => {
    if (isActive && harness) {
      setLocalPlan(harness.plan)
      setLocalSections(harness.sections)
    }
  }, [isActive, harness])

  /** Abandon the current plan, so the same folder can restart with a different goal.
   *
   * Without this action, once a folder had a plan it could never be replaced: the plan status has only two sources
   * -- set to `done` when finished, and set to `abandoned` here. Without this button `abandoned`
   * would never appear, and the "no plan -> show the form" branch above would never be reached.
   *
   * Notes already written are **not touched at all** -- what is abandoned is the plan, not its output. */
  async function abandon() {
    if (!plan) return
    if (!await confirm({ title: t('Abandon the plan “{goal}”?', { goal: plan.goal }), detail: t('Notes already written are kept; writing just stops following this goal.'), okLabel: t('Abandon plan'), danger: true })) return
    try {
      await api.abandonWritingPlan(parent.note_id)
      setLocalPlan({ ...plan, status: 'abandoned' })
      setLocalSections([])
      setGoal('')
      onNoteChanged()
    } catch (e) {
      toast(t('Could not abandon the plan: {err}', { err: friendlyError(e) }), 'error')
    }
  }


  async function start() {
    if (starting) { startAbort.current?.abort(); return }
    if (!goal.trim()) return
    setStarting(true)
    const ctrl = new AbortController()
    startAbort.current = ctrl
    try {
      const r = await api.startWritingPlan(parent.note_id, goal.trim(), ctrl.signal)
      setLocalPlan(r.plan)
      setLocalSections(r.sections)
      onNoteChanged()
    } catch (e) {

      if ((e as Error).name === 'AbortError') toast(t('Stopped; no plan was generated — the goal is still in the box, try again any time'))
      else toast(t('Could not generate the writing plan: {err}', { err: friendlyError(e) }), 'error')
    } finally {
      startAbort.current = null
      setStarting(false)
    }
  }

  return (
    <div className="palette-backdrop" onClick={onClose}>
      <div
        className="panel-dialog plan-dialog"
        role="dialog" aria-label={t('Writing plan')}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}><Icon n="bx-rocket" /> <span className="plain-case">{displayTitle(parent)}</span> · {t('Writing plan')}</h2>
          <button className="icon-btn" title={t('Close (Esc)')} aria-label={t('Close')} onClick={onClose}><Icon n="bx-x" /></button>
        </div>

        {!plan || plan.status === 'abandoned' ? (
          <div className="stack" style={{ marginTop: 12 }}>
            <p className="muted" style={{ fontSize: 'var(--t-md)' }}>
              {t('Give a writing goal; it is split into sections, each its own note, written one after another. After the known sections it checks whether more is worth writing and only then stops.')}
              {scopeLabel && <>{t('Materials come only from “{scope}” (change the scope in the Memory tab).', { scope: scopeLabel })}</>}
            </p>
            <textarea aria-label={t('Writing goal')}
              rows={3}
              placeholder={t('e.g. Lay out how project X progressed from technical design to launch plan')}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            />
            {/* **Not disabled** while spinning: that click is "Stop"; disabling it would leave this run with no way out */}
            <button className="primary" onClick={start} disabled={!starting && !goal.trim()}
                    title={starting ? t('Stop this generation') : !goal.trim() ? t('Describe what this folder should become first') : undefined}>
              {starting ? <><span className="spinner" /> {t('Generating… Stop')}</> : t('Generate writing plan')}
            </button>
          </div>
        ) : (
          <div className="stack" style={{ marginTop: 12 }}>
            <p className="muted" style={{ fontSize: 'var(--t-md)' }}>{plan.goal}</p>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span className={'badge' + (plan.status === 'done' ? ' ok' : '')}>
                {plan.status === 'done' ? t('Done') : t('In progress')}
              </span>
              <div className="row" style={{ gap: 6 }}>
                {/* nowrap, same as App.tsx's "I decide each round": CJK text in a flex row can be
                    squeezed to one character per line, and this panel is narrower, so more prone to it. */}
                {running && (
                  <label className="muted"
                         style={{ fontSize: 'var(--t-sm)', cursor: 'pointer',
                                  whiteSpace: 'nowrap', flexShrink: 0 }}>
                    <input type="checkbox" checked={harness.follow} onChange={onToggleFollow} style={{ marginRight: 4 }} />
                    {t('Editor follows writing')}
                  </label>
                )}
                {plan.status === 'active' && (
                  <button
                    className="primary"
                    onClick={onRun}
                    disabled={!!harness?.running && !running}
                    title={!!harness?.running && !running ? t('“{name}” is running; stop it before starting this one', { name: harness.folderName }) : undefined}
                  >
                    {running ? '■ ' + t('Stop') : '▶ ' + t('Keep writing')}
                  </button>
                )}
                {!running && (
                  <button onClick={abandon} title={t('Start over with a new goal. Notes already written are kept')}>
                    {t('New goal')}
                  </button>
                )}
              </div>
            </div>

            {/* Pinned at the top, no scrolling to find it -- the streaming preview used to be a little block of grey text inside the matching section card;
               if the harness had moved on to a section further down the list, a user
               looking at the top of the list saw no change at all, and the feedback was literally "I can't see
               progress". This block stays in the same place whatever section is being written, with much bigger font size and contrast
               -- you can tell at a glance whether it is "writing" or "stuck". */}
            {running && (
              <div className="card" style={{ background: 'var(--panel)' }}>
                <div className="row" style={{ gap: 6 }}>
                  <span className="spinner" />
                  <strong style={{ fontSize: 'var(--t-md)' }}>
                    {harness.currentSectionTitle ? t('Writing: {title}', { title: harness.currentSectionTitle }) : t('Starting…')}
                  </strong>
                </div>
                {harness.waitingFirstToken ? (
                  <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '6px 0 0' }}>
                    {t('Searching the knowledge base and starting the model… (a local model usually takes a few seconds here)')}
                  </p>
                ) : (
                  <div style={{ fontSize: 'var(--t-md)', marginTop: 8, whiteSpace: 'pre-wrap',
                               maxHeight: 220, overflowY: 'auto' }}>
                    {harness.preview || '…'}
                  </div>
                )}
              </div>
            )}

            <div className="stack" style={{ marginTop: 8 }}>
              {sections.map((s) => (
                <div key={s.id} className="card">
                  <div>
                    <span style={{ color: STATUS_COLOR[s.status] }}>
                      <Icon n={STATUS_ICON[s.status]} /> {t(STATUS_TEXT[s.status])}
                    </span>{' '}
                    <strong>{s.title}</strong>
                  </div>
                  {s.summary && (
                    <div className="muted" style={{ fontSize: 'var(--t-sm)', marginTop: 4 }}>{s.summary}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
