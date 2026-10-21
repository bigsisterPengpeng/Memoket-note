

export type Inline = { t: 'text' | 'b' | 'code'; s: string }
export type Block =
  | { kind: 'h'; parts: Inline[] }
  | { kind: 'p'; parts: Inline[] }
  | { kind: 'ul'; items: Inline[][] }
  /** A code fence. `lang` is the word after the fence (mermaid / python / empty). */
  | { kind: 'pre'; lang: string; text: string }

const INLINE = /\*\*([^*]+)\*\*|`([^`]+)`/g

export function parseInline(line: string): Inline[] {
  const out: Inline[] = []
  let last = 0
  for (const m of line.matchAll(INLINE)) {
    if (m.index! > last) out.push({ t: 'text', s: line.slice(last, m.index) })
    out.push(m[1] !== undefined ? { t: 'b', s: m[1] } : { t: 'code', s: m[2] })
    last = m.index! + m[0].length
  }
  if (last < line.length) out.push({ t: 'text', s: line.slice(last) })
  return out.length ? out : [{ t: 'text', s: line }]
}

export function parseMini(md: string): Block[] {
  const out: Block[] = []
  let para: string[] = []
  const flush = () => { if (para.length) { out.push({ kind: 'p', parts: parseInline(para.join('')) }); para = [] } }

  const lines = (md || '').split('\n')
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i]
    const fence = /^\s*```(.*)$/.exec(raw)
    if (fence) {
      flush()
      const lang = fence[1].trim().split(/\s+/)[0] ?? ''
      const buf: string[] = []
      for (i++; i < lines.length && !/^\s*```/.test(lines[i]); i++) buf.push(lines[i])
      out.push({ kind: 'pre', lang, text: buf.join('\n') })
      continue
    }
    const line = raw.trimEnd()
    if (!line.trim()) { flush(); continue }
    const h = /^#{1,6}\s+(.*)$/.exec(line)
    if (h) { flush(); out.push({ kind: 'h', parts: parseInline(h[1]) }); continue }
    const li = /^\s*[-*]\s+(.*)$/.exec(line)
    if (li) {
      flush()
      const prev = out[out.length - 1]
      if (prev?.kind === 'ul') prev.items.push(parseInline(li[1]))
      else out.push({ kind: 'ul', items: [parseInline(li[1])] })
      continue
    }
    // Soft line breaks in a paragraph join into one line: the daily report has no "layout by Enter"
    para.push(para.length ? (/[\u4e00-\u9fff]$/.test(para[para.length - 1]) ? '' : ' ') + line : line)
  }
  flush()
  return out
}
