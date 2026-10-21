import { Fragment, type ReactNode } from 'react'

import type { Fact } from '../api'
import { citeChipLabel } from '../editor/factCite'
import Icon from './Icon'
import { t } from '../i18n'

export type TraceLine = { date: string; text: string }

const DATE_HEAD = /^(?:[-*•]\s*|\d+[.)\u3001]\s*)?\[((?:\d{4}(?:[-/.\u5e74]\d{1,2})?(?:[-/.\u6708]\d{1,2}\u65e5?)?(?:\s*[?\uff1f])?|\u65e5\u671f\u672a\u77e5|\u65f6\u95f4\u672a\u77e5|\u7ea6[^\]]+))\]\s*(.*)$/
const PLAIN_DATE_HEAD = /^(?:[-*•]\s*|\d+[.)\u3001]\s*)?(\d{4}(?:[-/.\u5e74]\d{1,2})?(?:[-/.\u6708]\d{1,2}\u65e5?)?(?:\s*[?\uff1f])?)\s*[\uff1a:]\s*(.*)$/

/** KITE's timeline answer is one node per line; tolerate the bullets and numbering the model sometimes adds. */
export function traceLines(answer: string): TraceLine[] {
  return (answer || '').split(/\n+/).map((line) => line.trim()).filter(Boolean).map((line) => {
    const bracketed = DATE_HEAD.exec(line)
    if (bracketed) return { date: bracketed[1].trim(), text: bracketed[2].trim() }
    const plain = PLAIN_DATE_HEAD.exec(line)
    return plain ? { date: plain[1].trim(), text: plain[2].trim() } : { date: '', text: line }
  })
}

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

function openFact(factId: string) {
  window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:fact:' + factId }))
}

function linkedText(text: string, facts: Pick<Fact, 'id'>[]): ReactNode {
  const ids = Array.from(new Set(facts.map((f) => f.id).filter(Boolean))).sort((a, b) => b.length - a.length)
  if (!ids.length) return text
  const byId = new Set(ids)
  const re = new RegExp(`(\\[?(?:${ids.map(escapeRe).join('|')})\\]?)`, 'g')
  return text.split(re).map((part, i) => {
    const factId = part.startsWith('[') && part.endsWith(']') ? part.slice(1, -1) : part
    return byId.has(factId)
      ? <button key={`${factId}-${i}`} type="button" className="trace-answer-cite"
                title={t('Open source {id}', { id: factId })} onClick={() => openFact(factId)}>
          {citeChipLabel(factId)}
        </button>
      : <Fragment key={i}>{part}</Fragment>
  })
}

export default function TraceAnswer({ answer, facts, onInsert }: {
  answer: string
  facts: Fact[]
  onInsert?: (text: string) => void
}) {
  const lines = traceLines(answer)

  return (
    <section className="trace-result" aria-label={t('Trace organized by time')}>
      <header className="trace-result-head">
        <div>
          <strong>{t('Timeline')}</strong>
          <span>{t('{n} events', { n: lines.length })} · {t('{n} sources', { n: facts.length })}</span>
        </div>
      </header>

      <ol className="trace-answer">
        {lines.map((line, i) => (
          <li className={'trace-answer-event' + (line.date ? '' : ' undated')} key={`${line.date}-${i}`}>
            <span className="trace-answer-rail" aria-hidden="true"><i /></span>
            <article>
              {line.date && <time className="trace-answer-date">{line.date}</time>}
              <div className="trace-answer-text">{linkedText(line.text, facts)}</div>
            </article>
          </li>
        ))}
      </ol>

      {!!facts.length && (
        <details className="trace-sources">
          <summary>
            <span><strong>{t('Sources')}</strong><small>{t('{n} items', { n: facts.length })}</small></span>
            <span className="trace-sources-hint">{t('Expand to verify')}</span>
            <span className="trace-sources-chevron" aria-hidden="true"><Icon n="bx-chevron-down" /></span>
          </summary>
          <div className="trace-source-list">
            {facts.map((fact, i) => (
              <article className="trace-source" key={fact.id}>
                <div className="trace-source-meta">
                  <span className="trace-source-number">{String(i + 1).padStart(2, '0')}</span>
                  <time>{fact.when || t('Date unknown')}</time>
                </div>
                <button type="button" className="trace-source-text" title={t('Open this knowledge base fact')}
                        onClick={() => openFact(fact.id)}>{fact.text}</button>
                <div className="trace-source-actions">
                  <button type="button" className="linklike" onClick={() => openFact(fact.id)}>{t('View original')}</button>
                  {onInsert && <button type="button" className="linklike"
                    onClick={() => onInsert(`${fact.text} [${fact.id}]\n`)}>{t('Insert into note')}</button>}
                </div>
              </article>
            ))}
          </div>
        </details>
      )}
    </section>
  )
}
