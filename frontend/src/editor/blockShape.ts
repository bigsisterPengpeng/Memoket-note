
import { t } from '../i18n'

/** Strip a code fence around the whole block (models like to wrap output in ```); only for judging shape, the text landing in the body is unchanged. */
function unfence(text: string): string {
  const s = text.trim()
  if (!s.startsWith('```')) return s
  const i = s.indexOf('\n')
  if (i < 0) return s
  const inner = s.slice(i + 1)
  const j = inner.lastIndexOf('```')
  return (j < 0 ? inner : inner.slice(0, j)).trim()
}

/** Whether the whole block is one JSON object / array. **It must really parse** -- looking only at a leading `{`
 *  would misjudge a normal sentence like "{product name} pricing" as JSON. */
export function looksLikeJson(text: string): boolean {
  const s = unfence(text)
  if (!((s.startsWith('{') && s.endsWith('}')) || (s.startsWith('[') && s.endsWith(']')))) return false
  try {
    const v = JSON.parse(s)
    return typeof v === 'object' && v !== null
  } catch {
    return false
  }
}

const HAS_TABLE_ROW = /^\s*\|.*\|/m
const HAS_FENCE = /^\s*(```|~~~)/m
const HAS_IMAGE = /!\[[^\]]*\]\([^)]+\)/

/** The shape this block should have: `table` = must have markdown table rows; `figure` = must have a fence or an image;
 *  `markdown` = anything but a whole JSON string. **New modes default to `markdown`** --
 *  a miss is cheaper than a false block, and adding an item to the `/` menu will not silently open a new gate. */
export function shapeOf(key: string): 'table' | 'figure' | 'markdown' {
  if (key === 'table') return 'table'
  if (key === 'eda') return 'figure'
  return 'markdown'
}

// The line on the placeholder is **plain text** (the textContent of `cm-run-phase`); writing `**bold**` shows up raw --

const retryTail = () => t(' — this block was not written into the note. Click “Retry” to try again.')

/** If the shape is wrong, return a **plain sentence** (shown right on the placeholder); if right, an empty string. */
export function blockShapeProblem(key: string, text: string): string {
  const s = (text || '').trim()
  if (!s) return ''                       // empty output has its own path ("no output")
  if (looksLikeJson(s)) {
    return t('The model answered with raw JSON, not content that can go into the note') + retryTail()
  }
  const shape = shapeOf(key)
  if (shape === 'table' && !HAS_TABLE_ROW.test(s)) {
    return t('This block should be a table, but the answer has no table rows') + retryTail()
  }
  if (shape === 'figure' && !HAS_FENCE.test(s) && !HAS_IMAGE.test(s)) {
    return t('This block should be a figure (chart code or an image), but the answer has neither') + retryTail()
  }
  return ''
}


export function revisionIsJson(text: string): boolean {
  return looksLikeJson((text || '').trim())
}

/** Which suggestions in a batch are whole JSON strings. Returned separately so the caller can say "blocked N". */
export function splitBadRevisions<T extends { text: string }>(list: T[]): { keep: T[]; bad: T[] } {
  const keep: T[] = []
  const bad: T[] = []
  for (const r of list) (revisionIsJson(r.text) ? bad : keep).push(r)
  return { keep, bad }
}


export function badRevisionNote(label: string, n: number): string {
  return t('{label}: the model answered with raw JSON, not content that can go into the note — {n} suggestions were dropped and the text is unchanged. Try again.', { label, n })
}


export function unparsedEditNote(label: string): string {
  return t('{label}: the model did not answer in the required format, so no usable suggestion could be extracted — the text is unchanged. Try again.', { label })
}
