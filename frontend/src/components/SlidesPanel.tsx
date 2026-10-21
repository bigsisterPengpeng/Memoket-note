import { EditorView } from '@codemirror/view'
import type { RefObject } from 'react'

import { slidePages } from '../util/slidePages'
import { t } from '../i18n'

/**
 * Slide preview (pain point 6, docs/slides-plan.md).
 *
 * **16:9 thumbnails drawn in pure CSS, no Marp** -- that is a 600KB+ dependency, not worth it just for a preview.
 * The only three questions to answer here: how many pages, what each page says, and **which page has no grounding**. The last one
 * is the fundamental difference between this product and a generic slides tool, so it is the only thing marked with color.
 *
 * Clicking a page jumps to that page in the body: a deck is just a markdown note, editing a page is
 * editing a paragraph -- no "edit inside the preview" (syncing two copies of content has no good answer).
 */
export default function SlidesPanel({ content, viewRef }: {
  content: string
  viewRef: RefObject<EditorView | null>
}) {
  const pages = slidePages(content)
  if (!pages.length) {
    return <p className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('This note is not a slide deck yet. Generate one via “⋯ → Make slides”.')}</p>
  }
  const bare = pages.filter((p) => !p.cited).length

  const goto = (at: number) => {
    const v = viewRef.current
    if (!v) return
    const pos = Math.min(at, v.state.doc.length)
    v.dispatch({ selection: { anchor: pos }, effects: EditorView.scrollIntoView(pos, { y: 'start' }) })
    v.focus()
  }

  return (
    <div>
      <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '0 0 8px' }}>
        {t('{n} slides', { n: pages.length })}
        {bare > 0 && <> · <b className="warnish">{t('{n} slides without sources', { n: bare })}</b></>}
        {' · '}{t('click a slide to jump to the text')}
      </p>
      <div className="slide-grid">
        {pages.map((p, i) => (
          <button key={i} className={'slide-thumb' + (p.cited ? '' : ' bare')} onClick={() => goto(p.at)}
                  title={p.cited ? t('This slide carries citation ids') : t('This slide has no sources')}>
            <span className="slide-no">{i + 1}</span>
            <b>{p.title || t('(no title)')}</b>
            <span className="slide-body">{p.body.replace(/^[-*+]\s+/gm, '· ').slice(0, 120)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
