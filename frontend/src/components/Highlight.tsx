/** Wrap the hit of `q` in `text` in <mark>, case-insensitive, marking only the first — one per list row
 * is enough; marking all gets noisy. Shared by search cards / ⌘K; don't write another indexOf each. */
export default function Highlight({ text, q }: { text: string; q: string }) {
  const needle = q.trim()
  const i = needle ? text.toLowerCase().indexOf(needle.toLowerCase()) : -1
  if (i < 0) return <>{text}</>
  return <>{text.slice(0, i)}<mark>{text.slice(i, i + needle.length)}</mark>{text.slice(i + needle.length)}</>
}
