import { useMemo } from 'react'
import type { Revision } from '../api'
import { t } from '../i18n'

/**
 * Track-changes panel.
 *
 * Revisions are anchored (the backend guarantees the anchor appears verbatim in the body), so accepting a
 * revision is one string replacement in the body -- no rich-text diff engine needed.
 * If the user does not accept, nothing changes; the original input is never overwritten by the model directly.
 */

type Props = {
  revisions: Revision[]
  content: string
  loading: boolean
  onAccept: (r: Revision) => void
  onReject: (r: Revision) => void
  onRun: () => void
}

function applyPreview(content: string, r: Revision): { before: string; after: string } {
  const i = content.indexOf(r.anchor)
  if (i < 0) return { before: r.anchor, after: r.text }
  if (r.op === 'insert') return { before: r.anchor, after: r.anchor + r.text }
  if (r.op === 'insert_before') return { before: r.anchor, after: r.text + r.anchor }
  if (r.op === 'delete') return { before: r.anchor, after: '' }
  return { before: r.anchor, after: r.text }
}

/** The range `[start, end)` this revision touches. Returns `[-1, -1]` if not found.
 *
 * When the anchor appears several times in the body, take the pair (anchor, nearest following
 * anchor_end) with the **smallest span**. That is the right semantics for deduplication:
 *
 *     ## Crowdfunding pace      <- first anchor
 *     Launch in early March.
 *     ## Crowdfunding pace      <- second anchor
 *     Launch the crowdfunding in early March. <- anchor_end
 *
 * "Delete the duplicated section" gives exactly this pair. Searching for anchor_end from the first anchor onward
 * would delete both sections; taking the smallest span lands on the second one.
 *
 * **This is ported from `_locate()` in backend `harness/revision.py`.** Before,
 * this only had `indexOf(anchor)`, a different range from the backend's -- auto-apply goes through the backend,
 * a manual "Accept" goes through here, and for the same dedup revision the backend deleted the duplicated section while the frontend deleted
 * the whole note (measured with the example above: the frontend kept a single newline). Two implementations of the same semantics are
 * intentional (the backend must auto-apply when nobody reviews, it cannot rely on a copy that only runs in the browser);
 * the price is that they must be pinned -- `scripts/check-revision-parity.mts` and the backend's
 * `tests/test_revision_parity.py` read the same case table.
 */
function locate(content: string, anchor: string, anchorEnd: string): [number, number] {
  let i = content.indexOf(anchor)
  if (i < 0) return [-1, -1]
  if (!anchorEnd) return [i, i + anchor.length]
  const first = i
  let best: [number, number] = [-1, -1]
  while (i >= 0) {
    const j = content.indexOf(anchorEnd, i + anchor.length)
    if (j >= 0) {
      const end = j + anchorEnd.length
      if (best[0] < 0 || end - i < best[1] - best[0]) best = [i, end]
    }
    i = content.indexOf(anchor, i + 1)
  }
  // When the end marker never matches, fall back to the anchor alone: better to change a little less than change
  // the wrong range, and certainly not to drop the whole revision over one mistyped end marker.
  return best[0] >= 0 ? best : [first, first + anchor.length]
}

export function applyRevision(content: string, r: Revision): string {
  const [i, located] = locate(content, r.anchor, r.anchor_end ?? '')
  if (i < 0) return content // the anchor was already edited by the user; give up on this one
  const end = r.anchor_end && located <= i + r.anchor.length
    ? i + r.anchor.length
    : located
  if (r.op === 'insert') return content.slice(0, end) + r.text + content.slice(end)
  if (r.op === 'insert_before') return content.slice(0, i) + r.text + content.slice(i)
  if (r.op === 'delete') return content.slice(0, i) + content.slice(end)
  return content.slice(0, i) + r.text + content.slice(end)
}

export default function RevisionPanel({
  revisions, content, loading, onAccept, onReject, onRun,
}: Props) {
  // Revisions whose anchor cannot be found should not show -- the user already changed that text
  const live = useMemo(
    () => revisions.filter((r) => !r.anchor || content.includes(r.anchor)),
    [revisions, content],
  )

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>{t('Smart edit')}</h2>
        <button onClick={onRun} disabled={loading}>
          {loading ? <span className="spinner" /> : t('Generate revisions')}
        </button>
      </div>

      {!loading && live.length === 0 && (
        <p className="muted">{t('No revision suggestions. Click “Generate revisions” to have the model check the text against the outline and knowledge base.')}</p>
      )}

      {live.map((r) => {
        const p = applyPreview(content, r)
        return (
          <div className="card" key={r.id}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span className="badge">{r.op}</span>
              <div className="row">
                <button onClick={() => onAccept(r)}>{t('Accept')}</button>
                <button onClick={() => onReject(r)}>{t('Reject')}</button>
              </div>
            </div>

            <div style={{ marginTop: 8 }}>
              {r.op !== 'insert' && r.op !== 'insert_before' && <div><span className="del">{p.before}</span></div>}
              {r.op !== 'delete' && <div><span className="ins">{r.text}</span></div>}
            </div>

            {r.reason && <p className="muted" style={{ margin: '8px 0 0' }}>{r.reason}</p>}
            {r.sources.length > 0 && (
              <p className="muted" style={{ margin: '4px 0 0' }}>
                {t('Source: ')}{r.sources.join('; ')}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
