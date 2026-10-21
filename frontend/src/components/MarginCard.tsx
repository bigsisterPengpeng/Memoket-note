
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { clickable } from '../util/clickable'
import { RELATION_LABEL, markKey, type MarginMark } from '../editor/marginMemory'
import { alreadyCited, citeText, fillInText, ignoreRelation, mergeRelation, supersedeRelation, type RelationLike } from '../util/relationActions'
import Icon from './Icon'
import { CARD_WIDTH, placeCard, pushLineBelow, seamPush } from '../util/cardPlacement'
import { t } from '../i18n'

const REL_CLS: Record<MarginMark['relation'], string> = {
  conflict: 'rel-conflict', continuation: 'rel-continuation', corroborated: 'rel-corroborated',
  unsupported: 'rel-unsupported', accumulation: 'rel-accumulation', merge: 'rel-merge',
}
const REL_ICON: Record<MarginMark['relation'], string> = {
  conflict: 'bx-error', continuation: 'bx-trending-up', corroborated: 'bx-check-shield',
  unsupported: 'bx-question-mark', accumulation: 'bx-layer-plus', merge: 'bx-git-merge',
}
/** What the relation means, in one sentence (the card's `say` sentence is about "this paragraph"; this one is about "this color") */
const REL_HINT: Record<MarginMark['relation'], string> = {
  conflict: 'The knowledge base records something different from this paragraph',
  continuation: 'The knowledge base has a timeline for this matter',
  corroborated: 'A knowledge base record matches this paragraph',
  unsupported: 'No record matches the figures or dates in this paragraph',
  accumulation: 'The knowledge base has conditions on this matter that you have not written',
  merge: 'Two knowledge base records describe the same thing',
}

const GAP = 10
export { CARD_WIDTH }

export type MarginCardState = { m: MarginMark; anchor: DOMRect; reason: 'hover' | 'click' | 'cursor' }

export default function MarginCard({ card, content, onClose, onInsert, onSeeAll }: {
  card: MarginCardState
  content: string
  onClose: () => void
  onInsert: (text: string) => void
  onSeeAll: () => void
}) {
  const { m, reason } = card
  const rel: RelationLike = { relation: m.relation, fact_ids: m.fact_ids ?? [], facts: m.facts ?? [] }
  const ref = useRef<HTMLDivElement>(null)
  const [anchor, setAnchor] = useState<DOMRect>(card.anchor)
  useEffect(() => { setAnchor(card.anchor) }, [card])
  const [pos, setPos] = useState<{ left: number; top: number; width: number }>({ left: anchor.right + GAP, top: anchor.top - 8, width: CARD_WIDTH })


  // if there is room inside the column to the right of the dot, sit to the right; otherwise hang below this line, right edge aligned with the column's right edge (`util/cardPlacement`).


  useLayoutEffect(() => {
    const h = ref.current?.offsetHeight ?? 160
    const pane = (ref.current?.closest('.note-pane') ?? document.querySelector('.note-pane')) as HTMLElement | null
    const b = pane?.getBoundingClientRect()
    const bounds = b && b.width > 0 ? b : { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight, width: window.innerWidth, height: window.innerHeight }
    const p = placeCard(anchor, bounds, h, window.innerHeight)
    setPos({ left: p.left, top: p.top, width: p.width })
    return pushLineBelow(anchor, seamPush(p.side, h))
  }, [anchor, m])

  // Body scrolled: follow the dot if it moved, close if it scrolled out of the viewport
  useEffect(() => {
    const onScroll = () => {
      const el = document.querySelector(`.cm-memory-gutter .mm-dot[data-line="${m.line}"]`)
      if (!el) { onClose(); return }
      setAnchor(el.getBoundingClientRect())
    }
    document.addEventListener('scroll', onScroll, true)
    return () => document.removeEventListener('scroll', onScroll, true)
  }, [m.line, onClose])

  // Esc closes; clicking outside the card closes; when opened by hover: close once the mouse is on neither the dot nor the card
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    const onDown = (e: MouseEvent) => {
      const t = e.target as HTMLElement
      if (ref.current?.contains(t) || t.closest?.('.mm-dot')) return
      onClose()
    }
    const onMove = (e: MouseEvent) => {
      if (reason !== 'hover') return
      const inCard = ref.current?.contains(e.target as Node)
      const a = anchor
      const nearDot = e.clientX >= a.left - 8 && e.clientX <= a.right + GAP + 4 && e.clientY >= a.top - 8 && e.clientY <= a.bottom + 8
      if (!inCard && !nearDot) onClose()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('mousemove', onMove)
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onDown); document.removeEventListener('mousemove', onMove) }
  }, [reason, anchor, onClose])

  const key = markKey(m)
  const ignore = () => { ignoreRelation(key); onClose() }
  const facts = rel.facts
  const cited = alreadyCited(rel, content)

  return (
    <div ref={ref} className={'margin-card rel-card ' + REL_CLS[m.relation]} role="dialog" aria-label={t('How this paragraph relates to the knowledge base: {rel}', { rel: t(RELATION_LABEL[m.relation]) })}
         style={{ left: pos.left, top: pos.top, width: pos.width }}>
      <div className="row margin-card-head">
        <span className={'badge ' + REL_CLS[m.relation]} title={t(REL_HINT[m.relation])}><Icon n={REL_ICON[m.relation]} /> {t(RELATION_LABEL[m.relation])}</span>
        <span className="muted margin-card-where">{t('This paragraph (from line {line})', { line: m.line })}{(m.kinds ?? 1) > 1 ? ' · ' + t('{n} more relations', { n: (m.kinds ?? 1) - 1 }) : ''}</span>
        <button className="icon-btn margin-card-close" title={t('Collapse (Esc)')} onClick={onClose}><Icon n="bx-x" /></button>
      </div>
      <div className="margin-card-say">{m.say}</div>
      {facts.length > 0 && (
        <div className="stack margin-card-facts">
          {facts.map((f) => (
            <div key={f.id} className="margin-card-fact" title={t('Open this record')}
                 {...clickable(() => window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:fact:' + f.id })))}>
              <span className="badge">{f.when || '—'}</span><span>{f.text}</span>
            </div>
          ))}
        </div>
      )}
      <div className="row margin-card-actions">
        {facts.length > 0 && (cited
          ? <span className="badge ok" title={t('Already cited in the note')}>{t('Cited')}</span>
          : <button onClick={() => { onInsert(citeText(rel)); onClose() }} title={t('Insert the latest record with its source at the cursor')}>{t('Cite this')}</button>)}
        {m.relation === 'conflict' && <button onClick={() => void supersedeRelation(rel).then((ok) => ok && onClose())} title={t('Mark the earlier record as superseded by the later one')}>{t('New supersedes old')}</button>}
        {m.relation === 'accumulation' && facts.length > 0 && <button onClick={() => { onInsert(fillInText(rel)); ignoreRelation(key); onClose() }} title={t('Insert those conditions from the knowledge base, with citations, into the note')}>{t('Fill in')}</button>}
        {m.relation === 'merge' && facts.length === 2 && <button onClick={() => void mergeRelation(rel).then((ok) => ok && onClose())} title={t('Keep the later record and mark the earlier one as superseded by it')}>{t('Merge into one')}</button>}
        <button onClick={ignore} title={t('Stop mentioning this pair (remembered on this machine)')}>{t('Ignore')}</button>
        <button className="linklike margin-card-more" onClick={onSeeAll} title={t('See all relations and recall for this paragraph in the Memory tab')}>{t('See all in the sidebar')}</button>
      </div>
    </div>
  )
}
