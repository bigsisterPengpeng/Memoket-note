import { createPortal } from 'react-dom'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent } from 'react'

import { INTENT_FIELD_MAX, type DocIntent } from '../util/docIntent'
import {
  TEMPLATE_CATEGORIES, WRITING_TEMPLATES, localizeTemplate, searchTemplates, templatesIn,
  type WritingTemplate, type WritingTemplateCategoryId, type WritingTemplateId,
} from '../editor/writingTemplates'
import { t } from '../i18n'
import Icon from './Icon'
import './WritingWorkflowPicker.css'

type CustomTask = Pick<DocIntent, 'goal' | 'reader' | 'done'>

/**
 * Writing mode picker: 12 category tabs + a search box + compact cards (label + one-line hint) +
 * one detail block (the sourcing / writing / checks / finish lines of the selected, hovered or
 * focused card). 104 cards are not laid out as a wall: cards are for recognising, rules are read
 * in the detail.
 *
 * Keyboard: tabs switch with Left / Right / Home / End (roving tabindex); each card is a button,
 * reachable with Tab, and focusing it previews it; Esc closes. While the search box has text the
 * search spans all categories (English and Chinese both match); clicking a tab clears it.
 */
export default function WritingWorkflowPicker({ intent, resume, focus, onSelect, onCustom, onClose, anchor, initialCategory, initialQuery }: {
  anchor?: HTMLElement | null
  intent: DocIntent
  resume: boolean
  focus?: 'goal' | 'done'
  onSelect: (id: WritingTemplateId) => void
  onCustom: (task: CustomTask) => void
  onClose: () => void

  initialCategory?: WritingTemplateCategoryId
  initialQuery?: string
}) {
  const panelRef = useRef<HTMLElement>(null)
  const [position, setPosition] = useState<{ top: number; left: number; width: number } | null>(null)
  const tabRefs = useRef<Map<string, HTMLButtonElement>>(new Map())
  const workflow = intent.workflow ?? ''
  // For the four originals the workflow is the template id; for category templates it is the category id (which card was picked is not stored in the intent).
  const activeTemplate = WRITING_TEMPLATES.find((item) => item.id === workflow)
  const [category, setCategory] = useState<WritingTemplateCategoryId>(
    initialCategory ?? activeTemplate?.category ?? (TEMPLATE_CATEGORIES.some((c) => c.id === workflow) ? workflow as WritingTemplateCategoryId : 'favorites'),
  )
  const [query, setQuery] = useState(initialQuery ?? '')
  const [preview, setPreview] = useState<WritingTemplateId | null>(null)
  const [focused, setFocused] = useState<WritingTemplateId | null>(null)
  const [custom, setCustom] = useState<CustomTask>({ goal: intent.goal, reader: intent.reader, done: intent.done })
  useLayoutEffect(() => {
    const panel = panelRef.current
    if (!panel) return
    const measure = () => {
      const rect = anchor?.getBoundingClientRect()
      const width = Math.min(720, window.innerWidth - 32)
      const height = Math.min(620, window.innerHeight - 32)
      const top = Math.max(16, Math.min((rect?.bottom ?? 64) + 8, window.innerHeight - height - 16))
      const left = Math.max(16, Math.min((rect?.right ?? window.innerWidth - 16) - width, window.innerWidth - width - 16))
      setPosition((current) => current?.top === top && current.left === left && current.width === width ? current : { top, left, width })
    }
    measure()
    window.addEventListener('resize', measure)
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    if (anchor) observer?.observe(anchor)
    window.addEventListener('scroll', measure, true)
    return () => { window.removeEventListener('resize', measure); window.removeEventListener('scroll', measure, true); observer?.disconnect() }
  }, [anchor])
  useEffect(() => setCustom({ goal: intent.goal, reader: intent.reader, done: intent.done }), [intent])
  useEffect(() => {
    if (!focus) panelRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [focus, onClose])

  const searching = query.trim() !== ''
  const shown = useMemo(() => (searching ? searchTemplates(query) : templatesIn(category)), [searching, query, category])
  const detailSource: WritingTemplate | undefined =
    ((focused ?? preview) ? shown.find((item) => item.id === (focused ?? preview)) : undefined)
    ?? (activeTemplate && shown.some((item) => item.id === activeTemplate.id) ? activeTemplate : undefined)
    ?? shown[0]
  const detail = detailSource ? localizeTemplate(detailSource) : undefined

  const isActive = (template: WritingTemplate) => template.id === workflow
  const pickCategory = (id: WritingTemplateCategoryId) => { setCategory(id); setQuery(''); setPreview(null); setFocused(null) }
  const onTabKey = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const ids = TEMPLATE_CATEGORIES.map((c) => c.id)
    const at = ids.indexOf(category)
    let next = -1
    if (event.key === 'ArrowRight') next = (at + 1) % ids.length
    else if (event.key === 'ArrowLeft') next = (at - 1 + ids.length) % ids.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = ids.length - 1
    if (next < 0) return
    event.preventDefault()
    pickCategory(ids[next])
    tabRefs.current.get(ids[next])?.focus()
  }

  return createPortal(
    <section ref={panelRef} className="workflow-picker" role="dialog" aria-modal="false" aria-label={t('Writing mode picker')} tabIndex={-1}
             style={position === null ? undefined : { '--workflow-top': `${position.top}px`, '--workflow-left': `${position.left}px`, '--workflow-width': `${position.width}px` } as CSSProperties}>
      <div className="workflow-picker-head">
        <div>
          <strong>{t('How should this one be written?')}</strong>
          <span>{resume ? t('Pick a scenario; Smart Continue follows its goal, sourcing, writing and finishing rules.') : t('A template sets the note structure and writing workflow rules.')}</span>
        </div>
        <button className="icon-btn sm" title={t('Close writing mode')} aria-label={t('Close writing mode')} onClick={onClose}><Icon n="bx-x" /></button>
      </div>
      <div className="workflow-toolbar">
        <label className="workflow-search">
          <Icon n="bx-search" />
          <input type="search" value={query} aria-label={t('Search templates')} placeholder={t('Search template names or descriptions')}
                 onChange={(e) => { setQuery(e.target.value); setPreview(null); setFocused(null) }} />
        </label>
        <span className="workflow-count">{t('{n} templates', { n: shown.length })}</span>
      </div>
      <div className="workflow-tabs" role="tablist" aria-label={t('Template categories')} onKeyDown={onTabKey}>
        {TEMPLATE_CATEGORIES.map((c) => {
          const selected = !searching && c.id === category
          return (
            <button key={c.id} type="button" role="tab" id={`workflow-tab-${c.id}`} aria-selected={selected}
                    aria-controls="workflow-tabpanel" tabIndex={c.id === category ? 0 : -1}
                    ref={(el) => { if (el) tabRefs.current.set(c.id, el); else tabRefs.current.delete(c.id) }}
                    className={'workflow-tab' + (selected ? ' active' : '')}
                    onClick={() => pickCategory(c.id)}>
              {t(c.label)}
            </button>
          )
        })}
      </div>
      <div className="workflow-body">
      <div id="workflow-tabpanel" role="tabpanel" aria-labelledby={searching ? undefined : `workflow-tab-${category}`}
           className="workflow-grid" onMouseLeave={() => setPreview(null)}>
        {shown.map((template) => (
          <button key={template.id} type="button"
                  className={'workflow-card' + (isActive(template) ? ' active' : '') + (detailSource?.id === template.id ? ' workflow-card-preview' : '')}
                  title={t('Use the “{label}” template', { label: t(template.label) })}
                  onClick={() => onSelect(template.id)}
                  onMouseEnter={() => setPreview(template.id)}
                  onMouseMove={() => { setFocused(null); setPreview(template.id) }}
                  onFocus={() => setFocused(template.id)}
                  onBlur={() => setFocused(null)}>
            <span className="workflow-card-title"><Icon n={template.icon} /><span>{t(template.label)}</span>{isActive(template) && <em>{t('In use')}</em>}</span>
            <span className="workflow-card-hint">{t(template.hint)}</span>
            {searching && <span className="workflow-card-cat">{t(TEMPLATE_CATEGORIES.find((c) => c.id === template.category)?.label ?? '')}</span>}
          </button>
        ))}
        {shown.length === 0 && <p className="workflow-empty">{t('No matching templates')}</p>}
      </div>
      {detail && (
        <div className="workflow-detail" aria-live="polite">
          <span className="workflow-detail-title"><Icon n={detail.icon} /><span>{detail.label}</span></span>
          <span><b>{t('Sourcing')}</b>{detail.contract.retrieve}</span>
          <span><b>{t('Writing')}</b>{detail.contract.write}</span>
          <span><b>{t('Checks')}</b>{detail.contract.verify}</span>
          <span><b>{t('Finish')}</b>{detail.contract.finish}</span>
        </div>
      )}
      </div>
      <div className="workflow-custom">
        <div className="workflow-custom-title">
          <strong>{t('Custom writing task')}</strong>
          <span>{t('Set a custom goal, audience and completion criteria for the writing workflow.')}</span>
        </div>
        <div className="workflow-custom-fields">
          <label><span>{t('What you want')}</span><input value={custom.goal} maxLength={INTENT_FIELD_MAX} aria-label={t('What you want')} autoFocus={focus === 'goal'} placeholder={t('e.g. turn the material into a product retrospective for investors')}
            onChange={(e) => setCustom({ ...custom, goal: e.target.value })} /></label>
          <label><span>{t('Who it is for')}</span><input value={custom.reader} maxLength={INTENT_FIELD_MAX} aria-label={t('Who it is for')} placeholder={t('e.g. potential investors')}
            onChange={(e) => setCustom({ ...custom, reader: e.target.value })} /></label>
          <label><span>{t('Must satisfy')}</span><input value={custom.done} maxLength={INTENT_FIELD_MAX} aria-label={t('Must satisfy')} autoFocus={focus === 'done'} placeholder={t('e.g. conclusions are grounded, with risks and next steps explicit')}
            onChange={(e) => setCustom({ ...custom, done: e.target.value })} /></label>
          <button className="primary" disabled={!custom.goal.trim()}
                  title={!custom.goal.trim() ? t('Fill in “What you want” first') : (resume ? t('Save the task and continue with Smart Continue') : t('Save this note\'s writing task'))}
                  onClick={() => onCustom(custom)}>
            {resume ? t('Continue with this task') : t('Use this task')}
          </button>
        </div>
        <p>{t('This defines a task for one note. A reusable custom template would also need structure, sourcing rules and a quality contract, not just a prompt.')}</p>
      </div>
    </section>,
    document.body,
  )
}
