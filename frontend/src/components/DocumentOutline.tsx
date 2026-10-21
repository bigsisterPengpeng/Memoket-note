import { useEffect, useMemo, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { EditorView } from '@codemirror/view'
import { SECTION_LABEL, materialsText, sectionStatuses, sectionSummary } from '../util/sectionStatus'
import { t } from '../i18n'

type Heading = { level: number; text: string; pos: number }


const INLINE_HEADING = /(?<![A-Za-z0-9#])#{1,6}\s+\S/

/** Parse headings outside fenced code while retaining source offsets. */
export function parseHeadings(content: string): Heading[] {
  const out: Heading[] = []
  const re = /^(#{1,6})\s+(.+)$/gm
  const fence = /^\s*(`{3,}|~{3,})/
  // Start offset of each line → whether it's inside a fence
  const inFence = new Set<number>()
  let fenced = false
  let at = 0
  for (const line of content.split('\n')) {
    const isFence = fence.test(line)
    if (isFence || fenced) inFence.add(at)
    if (isFence) fenced = !fenced
    at += line.length + 1
  }
  let m: RegExpExecArray | null
  while ((m = re.exec(content))) {
    if (inFence.has(m.index)) continue



    //
    // **Strip first, then cut, not the other way round**: when a whole heading is wrapped in a pair of `**` (`### **A ### B**`),
    // cutting first would cut off the second half of the pair, leaving an unstrippable half marker like `**A`.
    const plain = stripInline(m[2])
    const inner = INLINE_HEADING.exec(plain)
    const text = (inner ? plain.slice(0, inner.index) : plain).trim()
    if (!text) continue                            // the whole line is just a wedged-in marker, no outer text
    out.push({ level: m[1].length, text, pos: m.index })
  }
  return out
}


export type FallbackOutline = { items: Heading[]; how: 'short' | 'paragraph' | 'none' }
const COLON_HEAD = /^(.{1,16}?)\s*[\uff1a:]\s*$/   // fullwidth or ASCII colon
/** Short standalone lines can form a fallback outline; sentences and list items cannot. */
const BARE_HEAD = /^(?![-*+>])(?!\(?\uff08?\d+[\uff09)\u3001.]\s*)[^\s].{0,15}[^\s\u3002\uff01\uff1f\uff1b\uff0c\u3001\uff1a:.!?;,…—-]$/   // no list marker / (n) numbering; must not end with CJK or ASCII punctuation
const PARA_MIN_CHARS = 20
const FALLBACK_MAX = 200


export function stripInline(s: string): string {
  return s
    .replace(/!\[([^\]\n]*)\]\([^)\s]*\)/g, (_m, alt) => (alt ? t('Image: {alt}', { alt }) : t('Image')))   // image: keep alt
    .replace(/\[([^\]\n]*)\]\([^)\s]*\)/g, '$1')                                      // link: keep label
    .replace(/\[\[([^\]|\n]*\|)?([^\]\n]*)\]\]/g, '$2')                                 // wiki link: keep label
    .replace(/`([^`\n]*)`/g, '$1')                                                      // inline code
    .replace(/\*\*([^*\n]+)\*\*|__([^_\n]+)__/g, (_m, a, b) => a ?? b)                   // bold
    .replace(/(?<![*\w])\*([^*\n]+)\*(?!\*)/g, '$1')                                    // italic
    .replace(/~~([^~\n]+)~~/g, '$1')                                                    // strikethrough
    .trim()
}

function firstSentence(s: string): string {
  const t = stripInline(s.replace(/^[-*>\s]+|^\d+[.\u3001]\s*/g, '').trim())
  const m = t.match(/^(.{4,28}?)(?:[\u3002\uff01\uff1f\uff1b!?;]|$)/)   // first sentence: up to CJK/ASCII sentence-ending punctuation
  const head = m ? m[1] : t.slice(0, 28)
  return head.length < t.length ? head + '…' : head
}

export function parseFallbackAnchors(content: string): FallbackOutline {
  const fence = /^\s*(`{3,}|~{3,})/
  const paras: { pos: number; first: string; len: number }[] = []
  let cur: { pos: number; first: string; len: number } | null = null
  let fenced = false
  let at = 0
  for (const line of content.split('\n')) {
    const isFence = fence.test(line)
    if (isFence) fenced = !fenced
    if (!line.trim() || isFence || fenced) {
      if (cur) { paras.push(cur); cur = null }
    } else {
      if (!cur) cur = { pos: at, first: line.trim(), len: 0 }
      cur.len += line.trim().length
    }
    at += line.length + 1
  }
  if (cur) paras.push(cur)
  const heads = paras.filter((p) => p.len <= 17 && p.len >= 2 && (COLON_HEAD.test(p.first) || BARE_HEAD.test(p.first)))
  if (heads.length >= 3) {
    return { how: 'short', items: heads.slice(0, FALLBACK_MAX).map((p) => ({ level: 1, text: stripInline(p.first.replace(/\s*[\uff1a:]\s*$/, '')), pos: p.pos })) }
  }
  const long = paras.filter((p) => p.len >= PARA_MIN_CHARS)
  if (long.length >= 2) {
    return { how: 'paragraph', items: long.slice(0, FALLBACK_MAX).map((p) => ({ level: 1, text: firstSentence(p.first), pos: p.pos })) }
  }
  return { how: 'none', items: [] }
}


export function activeHeadingPos(
  headings: { pos: number }[],
  topPos: number, bottomPos: number, atBottom: boolean, pinned: number | null = null,
): number {
  if (pinned != null && headings.some((h) => h.pos === pinned) && pinned >= topPos && pinned <= bottomPos) return pinned
  let active = -1
  for (const h of headings) if (h.pos <= topPos) active = h.pos
  if (atBottom) for (const h of headings) if (h.pos <= bottomPos) active = h.pos
  return active
}

/** Jump-to-heading outline -- cheap to add now that the editor is real
 * markdown with real heading syntax, and it's table-stakes for anything
 * pitching itself as a Notion-class editor for longer documents. */
export default function DocumentOutline({ content, viewRef, withStatus = false }: {
  content: string
  viewRef: RefObject<EditorView | null>

  withStatus?: boolean
}) {
  const real = useMemo(() => parseHeadings(content), [content])
  const fallback = useMemo<FallbackOutline | null>(() => (real.length ? null : parseFallbackAnchors(content)), [content, real.length])
  const headings = useMemo(() => (real.length ? real : (fallback?.items ?? [])), [real, fallback])
  const statuses = useMemo(() => (withStatus && real.length ? sectionStatuses(content, real) : []), [withStatus, content, real])
  const statusAt = useMemo(() => new Map(statuses.map((s) => [s.pos, s])), [statuses])
  const summary = useMemo(() => sectionSummary(statuses), [statuses])
  // Which section is being viewed: follows the top line of the body's scroll area (Obsidian's outline does this too).
  // What scrolls is .note-scroll, not CM itself, so listen to it.
  const [activePos, setActivePos] = useState(-1)
  const listRef = useRef<HTMLDivElement>(null)

  const pinnedRef = useRef<number | null>(null)
  useEffect(() => {
    const view = viewRef.current
    const scroller = view?.scrollDOM.closest('.note-scroll') as HTMLElement | null
    if (!view || !scroller || headings.length === 0) return
    const update = () => {
      const r = scroller.getBoundingClientRect()
      const at = (y: number) => view.posAtCoords({ x: r.left + 60, y }) ?? view.posAtCoords({ x: r.left + 60, y }, false) ?? 0
      const topPos = at(r.top + 90)
      const bottomPos = at(r.bottom - 10)
      const atBottom = scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 2
      const active = activeHeadingPos(headings, topPos, bottomPos, atBottom, pinnedRef.current)
      if (pinnedRef.current != null && active !== pinnedRef.current) pinnedRef.current = null
      setActivePos(active)
    }
    update()
    scroller.addEventListener('scroll', update, { passive: true })
    return () => scroller.removeEventListener('scroll', update)
  }, [headings, viewRef])

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>('.outline-item.active')?.scrollIntoView({ block: 'nearest' })
  }, [activePos])
  if (headings.length === 0) return (
    <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: 0 }}>
      {t('The ')}<code>#</code>{t(' headings in the text are listed here; click one to jump to it')}{withStatus ? t('; each section shows a state (empty / draft / sourced) — empty means not written yet') : ''}{t('.')}
    </p>
  )

  function jump(pos: number) {
    const view = viewRef.current
    if (!view) return
    pinnedRef.current = pos
    setActivePos(pos)
    view.dispatch({
      selection: { anchor: pos },
      effects: EditorView.scrollIntoView(pos, { y: 'center' }),
    })
    view.focus()
  }

  return (
    <div>
      {fallback && fallback.how !== 'none' && (
        <p className="muted outline-fallback-note" style={{ fontSize: 'var(--t-xs)', margin: '0 0 6px', lineHeight: 1.6 }}>
          {fallback.how === 'short'
            ? t('This note has no # headings, so short standalone lines are listed instead; add # headings to list by heading.')
            : t('This note has no # headings, so paragraphs are listed ({n}, first sentence of each); add # headings to list by heading.', { n: headings.length })}
        </p>
      )}
      {statuses.length > 0 && (
        <p className="muted plan-outline-summary" title={t('Each section’s state is computed from the text: empty = nothing under the heading; draft = text without sources; sourced = cites knowledge base facts or links to other notes')}>
          {t('{n} sections · {empty} empty · {draft} draft · {sourced} sourced', { n: statuses.length, empty: summary.empty, draft: summary.draft, sourced: summary.sourced })}
        </p>
      )}
      <div className="stack" style={{ gap: 2 }} ref={listRef}>
        {headings.map((h, i) => {
          const s = statusAt.get(h.pos)
          const mats = s ? materialsText(s) : ''
          return (
            <a
              key={i}
              className={'link outline-item' + (h.pos === activePos ? ' active' : '') + (s ? ' with-state' : '')}
              style={{
                display: s ? 'flex' : 'block', fontSize: 'var(--t-sm)',
                paddingLeft: 6 + (h.level - 1) * 12,
                textDecoration: 'none',
              }}
              title={s ? `${t(SECTION_LABEL[s.state])}${s.words ? ` · ${t('{n} chars', { n: s.words })}` : ''}${mats ? ` · ${mats}` : ''}` : undefined}
              onClick={() => jump(h.pos)}
            >
              <span className="outline-text">{h.text}</span>
              {s && (
                <span className={'plan-state ' + s.state}>
                  {SECTION_LABEL[s.state]}{s.cites + s.links > 0 ? ` ${s.cites + s.links}` : ''}
                </span>
              )}
            </a>
          )
        })}
      </div>
    </div>
  )
}
