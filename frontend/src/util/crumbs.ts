
import type { TreeRow } from '../api'
import { VIRTUAL_LABELS, factsLabel, virtualParentOf } from './virtual'
import { t } from '../i18n'

const syntheticRow = (x: string, title: string): TreeRow =>
  ({ id: x, note_id: x, parent_note_id: '', title, position: 0, is_expanded: false, preview: '', cite_count: 0, ingested_at: '',
     pinned: false, updated_at: '', child_count: 0, branch_count: 0, fact_count: 0 } as TreeRow)

/**
 * @param id current note id or virtual page id (null = nothing open)
 * @param rows all rows in the tree (real notes + whatever of the knowledge-base virtual subtree has been delivered)
 * @param tabTitle what the tab calls this id (lazily loaded virtual pages have no tree row; only the tab knows the name)
 * @param isVirtual whether this id is a virtual page
 */
export function buildCrumbs(id: string | null | undefined, rows: TreeRow[], tabTitle: (id: string) => string | undefined,
                            isVirtual: (id: string) => boolean): TreeRow[] {
  if (!id) return []
  const byNote = new Map<string, TreeRow>()
  for (const r of rows) if (!byNote.has(r.note_id)) byNote.set(r.note_id, r)
  const out: TreeRow[] = []
  let cur = byNote.get(id); let guard = 0
  while (cur && guard++ < 50) { out.unshift(cur); cur = byNote.get(cur.parent_note_id) }
  // A facts table entered from the tree's tail row "N more · see facts table": the breadcrumb ends with the page's name (like the tab, "Facts table · work"), not the entry's sentence
  if (out.length && out[out.length - 1].note_id.startsWith('kb:facts')) {
    const last = out[out.length - 1]
    out[out.length - 1] = { ...last, title: factsLabel(last.note_id) ?? t('Facts table') }
  }
  // The lazily loaded levels (entities / facts under a topic...) are not in rows, and the status bar used to fall back to "23 notes"

  if (out.length === 0 && isVirtual(id)) {
    const parent = virtualParentOf(id)
    // The app:* pages (Recently deleted / Writing skills / Settings...) are not under the knowledge base; do not prefix them with "Knowledge base /"

    const chain = id.startsWith('app:') ? [id] : Array.from(new Set(['kb', ...(parent ? [parent] : []), id]))
    // VIRTUAL_LABELS holds English source text; translate at display
    const label = (x: string) => (VIRTUAL_LABELS[x] ? t(VIRTUAL_LABELS[x]) : undefined)
    const leaf = tabTitle(id) ?? label(id) ?? id.split(':').pop() ?? id
    return chain.map((x) => byNote.get(x) ?? syntheticRow(x, x === id ? leaf : (label(x) ?? x)))
  }
  return out
}
