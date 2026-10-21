import type { CompletionContext, CompletionResult } from '@codemirror/autocomplete'
import * as api from '../api'
import { t } from '../i18n'

/**
 * Type "@" + a few characters to search the knowledge base and insert a
 * citation inline -- this is the "manual, verifiable" counterpart to the
 * automatic grounding in magic-tap/edit. Competitive research kept surfacing
 * "AI can't find something that's clearly in my notes" as the #1 AI
 * complaint across Notion/Copilot/etc.; giving the user an explicit,
 * always-available search-and-cite action means they're never stuck hoping
 * the automatic path picks up a fact -- they can just go get it.
 *
 * Citations are inserted as plain text (`original text [fact-id]`), not a custom
 * widget/reference token: the document must stay a single plain string for
 * the anchor-based revision system, so there's no round-trip-safe way to
 * embed a "live" reference object without breaking that contract. The
 * `[fact-id]` tail is what the backend's `store.cited_fact_ids` and the
 * editor's `factCite` plugin both recognise -- the three "find and cite" paths
 * (@ completion / related memory / ⌘K) must insert the same thing, otherwise only one would count as a citation.
 */
export async function recallSource(context: CompletionContext): Promise<CompletionResult | null> {
  const match = context.matchBefore(/@[\u4e00-\u9fff\w][\u4e00-\u9fff\w ]{0,40}$/)
  if (!match) return null
  const query = match.text.slice(1).trim()
  if (!query) return null

  let facts: api.Fact[]
  let kbEmpty = false
  try {
    const res = await api.recall(query, 8)
    facts = res.facts
    kbEmpty = !!res.kb_empty
  } catch {
    return null
  }
  if (context.aborted) return null
  if (facts.length === 0) {
    // **"The library is empty" and "nothing found this time" must be said as two things.** For the former, any rewording is still empty,

    // anything typed `@prototype` and saw "No records related to 'prototype' found in the knowledge base"

    return {
      from: match.from,
      to: match.to,
      options: [{
        label: kbEmpty
          ? t('The knowledge base is still empty — import meeting notes or notes first, then there is something to cite')
          : t('No records related to "{query}" in the knowledge base', { query }),
        apply: () => {},
      }],
      filter: false,
    }
  }

  return {
    from: match.from,
    to: match.to,
    filter: false,
    options: facts.map((f) => ({
      label: f.text.length > 44 ? f.text.slice(0, 44) + '…' : f.text,
      detail: f.when || undefined,
      info: () => {
        const div = document.createElement('div')
        div.style.maxWidth = '340px'
        div.style.whiteSpace = 'pre-wrap'
        div.style.fontSize = '13px'
        div.textContent = f.sources.length ? `${f.text}\n\n${t('Original:')}\n${f.sources.join('\n')}` : f.text
        return div
      },
      apply: (view, _completion, from, to) => {
        const citation = `${f.text} [${f.id}]`
        view.dispatch({
          changes: { from, to, insert: citation },
          selection: { anchor: from + citation.length },
        })
      },
    })),
  }
}
