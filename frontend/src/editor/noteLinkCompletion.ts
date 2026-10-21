import type { CompletionContext, CompletionResult } from '@codemirror/autocomplete'
import * as api from '../api'
import { displayTitle } from '../util/displayTitle'
import { fmtDate } from '../util/time'
import { t } from '../i18n'

/**
 * `[[` + a few characters -> search note titles, the pick is inserted as `[title](note://<id>)`.
 *
 * A standard markdown link rather than `[[wiki]]`: the body exported elsewhere is still a valid link,
 * and the backend's `store.note_links_in` and backlink queries recognize `note://<id>` too.
 * This is the path that corresponds to Trilium's internal links (`~` / the link dialog).
 */

export function disambiguate(hits: { title?: string; content?: string; preview?: string; first_body?: string; updated_at: string }[]): string[] {
  const names = hits.map(displayTitle)
  const dup = new Set(names.filter((t, i) => names.indexOf(t) !== i))
  return hits.map((n, i) => {
    const date = fmtDate(n.updated_at)
    if (!dup.has(names[i])) return date
    if (n.first_body) return `${date} · ${n.first_body.slice(0, 28)}${n.first_body.length > 28 ? '…' : ''}`   // first body line computed by the server
    // Subheadings ("Timeline and milestones") are the same across notes and tell nothing apart -- prefer body lines, heading lines only as a fallback
    // With only the preview (first 80 characters) the last line may be cut in half ("## Timeline" leaving a "#"): drop that whole line
    const src = n.content ?? n.preview ?? ''
    const lines = src.split('\n')
    if (n.content == null && lines.length > 1) lines.pop()
    const clean = (l: string) => l.replace(/^\s*(#{1,6}|[-*>]|\d+\.)\s+/, '').replace(/[*_`\[\]#]/g, '').trim()
    const pick = (ls: string[]) => ls.map(clean).filter((l) => l.length > 1 && l !== names[i])
    const body = pick(lines.filter((l) => !/^\s*#{1,6}\s/.test(l)))
    const heads = pick(lines.filter((l) => /^\s*#{1,6}\s/.test(l)))
    const first = body.find((l) => l.length > 6) ?? body[0] ?? heads[0] ?? ''
    return first ? `${date} · ${first.slice(0, 28)}${first.length > 28 ? '…' : ''}` : date
  })
}

export async function noteLinkSource(context: CompletionContext): Promise<CompletionResult | null> {
  const match = context.matchBefore(/\[\[([^\]\n]{0,40})$/)
  if (!match) return null
  const query = match.text.slice(2).trim()
  let notes: api.NoteBrief[]
  try { notes = (await api.listNotesBrief(query)).notes } catch { return null }
  if (context.aborted) return null
  // Match by title only (or the first body line when untitled); do not mix in body hits -- a link points to "a note"
  const q = query.toLowerCase()
  const hits = notes
    .filter((n) => !q || displayTitle(n).toLowerCase().includes(q))
    .slice(0, 8)
  if (hits.length === 0) {
    return { from: match.from, to: match.to, filter: false,
             options: [{ label: query ? t('No note named "{query}"', { query }) : t('Type a few characters to search note titles'), apply: () => {} }] }
  }
  const details = disambiguate(hits)
  return {
    from: match.from,
    to: match.to,
    filter: false,
    options: hits.map((n, i) => ({
      label: displayTitle(n),
      detail: details[i],
      apply: (view, _c, from, to) => {
        const text = `[${displayTitle(n)}](note://${n.id})`
        view.dispatch({ changes: { from, to, insert: text }, selection: { anchor: from + text.length } })
      },
    })),
  }
}
