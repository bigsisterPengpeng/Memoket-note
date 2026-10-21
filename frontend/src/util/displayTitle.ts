/** Resolve placeholder titles from the first body line without changing stored notes. */
import { t } from '../i18n'
export const PLACEHOLDER = new Set(['', '\u672a\u547d\u540d', 'Untitled', 'note'])   // includes the Chinese "Untitled" placeholder of older notes
export const isPlaceholderTitle = (s: string) => PLACEHOLDER.has((s ?? '').trim())

export function displayTitle(n: { title?: string; preview?: string; content?: string }): string {
  const title = (n.title ?? '').trim()
  if (!PLACEHOLDER.has(title)) return title
  const firstLine = (n.preview ?? n.content ?? '')
    .split('\n')
    .map((l) => l.trim().replace(/^#+\s*/, '').trim())     // trim first: in a note indented throughout, "    # Title" would otherwise show as "# Title"
    .find((l) => l.length > 0)
  return firstLine ? clipTitle(firstLine) : t('Untitled')
}


export function clipTitle(line: string, max = 60): string {
  // Find the first "qualifying" break in order of appearance: sentence-ending marks (CJK full stop / exclamation / question) count unless within the first character or two;
  // commas / semicolons / colons too early (< 8 characters) do not make a title (e.g. "OK, let's settle it", "APP definition: first anchor the scope"), so skip to the next
  for (const m of line.matchAll(/[\u3002\uff01\uff1f\uff1b\uff0c,\uff1a:]/g)) {   // CJK and ASCII clause punctuation
    const min = /[\u3002\uff01\uff1f]/.test(m[0]) ? 2 : 8   // CJK sentence-ending marks
    if (m.index >= min) return line.slice(0, Math.min(m.index, max))
  }
  return line.slice(0, max)
}
