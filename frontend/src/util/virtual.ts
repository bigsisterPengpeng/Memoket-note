
import { t } from '../i18n'

export const VIRTUAL_LABELS: Record<string, string> = {
  'app:settings': 'Settings', 'app:skills': 'Writing Skills', 'app:import': 'Import', 'app:trash': 'Trash', 'app:journey': 'Screen activity',
  kb: 'Knowledge base', 'kb:graph': 'Topic map', 'kb:digest': 'Digests', 'kb:timeline': 'Timeline',
  'kb:topics': 'Topics', 'kb:entities': 'Entities', 'kb:recent': 'Recent imports',
  'kb:merges': 'Possible duplicates',
}

/** Recognized knowledge-base virtual id shapes (`kb:facts?topic=x` counts too -- on restart a facts-table tab with a query string must not be dropped as unknown) */
export const KNOWN_KB_RE = /^kb:(topic|entity|unit|material|fact|facts|etype)(:|\?|$)/

/** The knowledge base is one workspace, not a set of independent note tabs. */
export function isKbVirtual(id: string): boolean {
  return id === 'kb' || id.startsWith('kb:')
}

export type VirtualTabLike = { id: string; noteId: string; title: string }

/**
 * Opening an ordinary virtual page keeps the old "one tab per page". Navigation inside the knowledge base always reuses the same
 * tab, and also cleans up the multiple knowledge-base tabs older versions left in localStorage.
 */
export function syncVirtualTab<T extends VirtualTabLike>(
  tabs: T[], next: T, activeTabId: string | null,
): T[] {
  if (!isKbVirtual(next.noteId)) {
    const found = tabs.find((t) => t.noteId === next.noteId)
    if (!found) return [...tabs, next]
    return found.title === next.title
      ? tabs
      : tabs.map((t) => (t.id === found.id ? { ...t, title: next.title } : t))
  }

  const kbTabs = tabs.filter((t) => isKbVirtual(t.noteId))
  const keep = kbTabs.find((t) => t.id === activeTabId) ?? kbTabs[0]
  if (!keep) return [...tabs, next]
  return tabs.flatMap((t) => {
    if (t.id === keep.id) return [{ ...t, noteId: next.noteId, title: next.title }]
    return isKbVirtual(t.noteId) ? [] : [t]
  })
}

/** Whether this virtual id is recognized: fixed pages, the various knowledge-base nodes, app:* special pages */
export function isKnownVirtual(id: string): boolean {
  return !!VIRTUAL_LABELS[id] || KNOWN_KB_RE.test(id) || id.startsWith('app:')
}

/** What a filtered facts table is called: "Facts table · work" (with the query values appended). Tabs / split headers / breadcrumbs use the same one,
 *  otherwise a page entered from the tree's tail row "N more · see facts table" would carry that entry sentence as its name. */
export function factsLabel(id: string): string | undefined {
  if (!id.startsWith('kb:facts')) return undefined
  return t('Facts table') + (id.includes('?') ? ' · ' + Array.from(new URLSearchParams(id.split('?')[1]).values()).filter(Boolean).join(' · ') : '')
}

/** First non-empty line of a note's content, syntax markers stripped, for
 * the sidebar preview -- strip rather than render so it stays plain text
 * in a one-line ellipsis instead of showing raw "## " or "- " noise. */
export function previewLine(content: string, skip = ''): string {

  // skip the line identical to the display name (for placeholder-titled notes the display name is the first body line); code fences / image lines do not count;
  // strip list markers / hashes / emphasis markers; single-character lines do not count; prefer body lines, falling back to the first subheading only if there is no body line at all; 60 characters.
  // The frontend used to just take "the first line not equal to the title", so `# subheading` and `![image](…)` were printed as previews,
  // and the ⌘K note group (server first_body) and tab group (computed locally) gave different snippets for same-name disambiguation.
  const lines = (content || '').split('\n').slice(0, 60).map((l) => l.trim())
  const clean = (t: string) => t.replace(/^([-*>+]|\d+\.|#{1,6})\s*/, '').replace(/[*_`[\]]/g, '').trim()
  let shown = (skip || '').trim()
  if (shown === '' || shown === '\u672a\u547d\u540d' || shown === 'Untitled' || shown === 'note') shown = clean(lines.find((l) => l) ?? '')
  const body: string[] = []; const heads: string[] = []
  let fenced = false
  for (const l of lines) {
    if (l.startsWith('```')) { fenced = !fenced; continue }   // inside a fence is code, not body
    if (fenced || !l || l.startsWith('![')) continue
    const c = clean(l)
    if (c.length <= 1 || c.toLowerCase() === shown.toLowerCase()) continue
    ;(l.startsWith('#') ? heads : body).push(c)
  }
  return (body[0] ?? heads[0] ?? '').slice(0, 60)
}

/** Which category a lazily loaded virtual node hangs under in the tree (for building the breadcrumb parent chain) */
export function virtualParentOf(id: string): string | undefined {
  if (id === 'kb:merges') return 'kb:entities'     // the merge inbox hangs under entities so the breadcrumb can get back
  return ({ entity: 'kb:entities', etype: 'kb:entities', topic: 'kb:topics', month: 'kb:timeline', unit: 'kb:recent', material: 'kb:recent' } as Record<string, string>)[id.split(':')[1]]
}
