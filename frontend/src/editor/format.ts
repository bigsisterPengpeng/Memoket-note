/** One-click formatting of a whole markdown note.
 *
 * **Pure function, no model**: formatting has clear rules; handing it to a model only adds uncertainty
 * (different results each time, and it might edit content in passing). This only touches layout, not a single character of content.
 *
 * The most important invariant is **idempotence**: formatting twice must equal formatting once. If it were not idempotent, every
 * click would produce a pile of diffs, and "Accept/Revert" would become noise. scripts/check-format.mts
 * guards it with fixed cases + random fuzz.
 *
 * Content inside code blocks, inline code and table separator rows is **left exactly as is** -- applying layout rules inside code
 * is editing the user's program.
 */

const FENCE = /^(\s*)(`{3,}|~{3,})/

/** Split the body into "outside code blocks / inside code blocks". Lines inside code blocks are kept as-is. */
function splitFences(lines: string[]): { code: boolean; lines: string[] }[] {
  const out: { code: boolean; lines: string[] }[] = []
  let cur: { code: boolean; lines: string[] } = { code: false, lines: [] }
  let fence = ''
  for (const line of lines) {
    const m = FENCE.exec(line)
    if (!fence && m) {
      if (cur.lines.length) out.push(cur)
      fence = m[2]
      cur = { code: true, lines: [line] }
      continue
    }
    if (fence) {
      cur.lines.push(line)
      // The closing marker must be the same type and no shorter than the opening run
      if (m && m[2][0] === fence[0] && m[2].length >= fence.length) {
        out.push(cur)
        cur = { code: false, lines: [] }
        fence = ''
      }
      continue
    }
    cur.lines.push(line)
  }
  if (cur.lines.length) out.push(cur)
  return out
}

const cells = (line: string): string[] => {
  const t = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  const out: string[] = []
  let cur = ''
  for (let i = 0; i < t.length; i++) {
    if (t[i] === '\\' && t[i + 1] === '|') { cur += '\\|'; i++; continue }
    if (t[i] === '|') { out.push(cur.trim()); cur = ''; continue }
    cur += t[i]
  }
  out.push(cur.trim())
  return out
}

const isSep = (line: string): boolean => {
  const cs = cells(line)
  return cs.length > 0 && cs.every((c) => /^:?-{1,}:?$/.test(c))
}

/** Display width: CJK and full-width punctuation take two cells. Table alignment must use this; counting characters
 * leaves CJK tables ragged even in a monospace font. */
function width(s: string): number {
  let w = 0
  for (const ch of s) {
    const c = ch.codePointAt(0) ?? 0
    w += (c >= 0x1100 && (c <= 0x115f || c === 0x2329 || c === 0x232a
      || (c >= 0x2e80 && c <= 0xa4cf && c !== 0x303f)
      || (c >= 0xac00 && c <= 0xd7a3) || (c >= 0xf900 && c <= 0xfaff)
      || (c >= 0xfe30 && c <= 0xfe6f) || (c >= 0xff00 && c <= 0xff60)
      || (c >= 0xffe0 && c <= 0xffe6))) ? 2 : 1
  }
  return w
}

const pad = (s: string, w: number, align: 'left' | 'center' | 'right'): string => {
  const gap = Math.max(0, w - width(s))
  if (align === 'right') return ' '.repeat(gap) + s
  if (align === 'center') {
    const l = Math.floor(gap / 2)
    return ' '.repeat(l) + s + ' '.repeat(gap - l)
  }
  return s + ' '.repeat(gap)
}

/** Align tables by column. The AI now generates whole tables (smart tables / EDA), and the pipes in raw output do not line up,
 * so the structure is unreadable in the source. */
function formatTable(rows: string[]): string[] {
  const grid = rows.map(cells)
  const sepIdx = rows.findIndex(isSep)
  const aligns = (grid[sepIdx] ?? []).map((c) => {
    const l = c.startsWith(':')
    const r = c.endsWith(':')
    return l && r ? 'center' as const : r ? 'right' as const : 'left' as const
  })
  const cols = Math.max(...grid.map((g) => g.length))
  const widths: number[] = []
  for (let i = 0; i < cols; i++) {
    widths[i] = Math.max(3, ...grid.map((g, ri) => (ri === sepIdx ? 0 : width(g[i] ?? ''))))
  }
  return grid.map((g, ri) => {
    if (ri === sepIdx) {
      return '|' + widths.map((w, i) => {
        const a = aligns[i] ?? 'left'
        // The separator row's total width must be the same for all three alignments (w + 2), otherwise column pipes do not line up
        const bar = '-'.repeat(Math.max(1, w))
        return a === 'center' ? `:${bar}:` : a === 'right' ? ` ${bar}:` : ` ${bar} `
      }).join('|') + '|'
    }
    return '| ' + widths.map((w, i) => pad(g[i] ?? '', w, aligns[i] ?? 'left')).join(' | ') + ' |'
  })
}

/** Add a space between CJK and Latin text (common CJK typesetting practice). **Not inside code, links or URLs**. */
function cjkSpacing(s: string): string {
  const parts = s.split(/(`[^`]*`|\[[^\]]*\]\([^)]*\)|https?:\/\/\S+)/g)
  return parts.map((p, i) => {
    if (i % 2) return p                          // the split capture group: code/links as-is
    return fixBoldPunct(p)
      .replace(/([\u4e00-\u9fff\u3040-\u30ff])([A-Za-z0-9])/g, '$1 $2')
      .replace(/([A-Za-z0-9])([\u4e00-\u9fff\u3040-\u30ff])/g, '$1 $2')
  }).join('')
}


export function fixBoldPunct(s: string): string {
  const out: string[] = []
  let fenced = false
  for (const line of s.split('\n')) {
    if (/^\s*(`{3,}|~{3,})/.test(line)) { fenced = !fenced; out.push(line); continue }
    // The opening ** must not directly follow a character: in "**keep** the approach; **stop**" the closing ** after "keep"

    out.push(fenced ? line : line.replace(/(?<![\w\u4e00-\u9fff])\*\*([^*\n]+?)([\uff1a:\uff0c,\u3002\uff1b;\uff01!\uff1f?\u3001\uff09)])\*\*/g, '**$1**$2'))
  }
  return out.join('\n')
}

/** Which kind a block is. **Markdown's block structure is separated by blank lines** -- whenever the kind changes there must
 * be a blank line, otherwise it is not just ugly, it parses wrong:
 *   · a quote right after a list item -> taken as a continuation of that item (lazy continuation)
 *   · text right after an HTML block -> that line is swallowed into the HTML block and **does not render at all**
 *   · an unordered list right after an ordered list -> the two lists stick together into one
 * All of these were found by running content this app itself generates (audio tags, AI tables).
 */
type Kind = 'blank' | 'heading' | 'para' | 'ul' | 'ol' | 'quote' | 'table' | 'code' | 'html'

const HTML_BLOCK = /^\s*<\/?[a-zA-Z][^>]*>/


export function stripCommonIndent(src: string): string {
  const lines = src.split('\n')
  if (lines.some((l) => /^\s*(`{3,}|~{3,})/.test(l))) return src
  const nonBlank = lines.filter((l) => l.trim())
  if (nonBlank.length < 2) return src
  const indents = nonBlank.map((l) => (l.match(/^[ \t]*/)?.[0] ?? '').replace(/\t/g, '    ').length)
  const common = Math.min(...indents)
  if (common < 4) return src
  return lines.map((l) => {
    const lead = (l.match(/^[ \t]*/)?.[0] ?? '')
    let width = 0; let cut = 0
    for (const ch of lead) { if (width >= common) break; width += ch === '\t' ? 4 : 1; cut++ }
    return l.slice(cut)
  }).join('\n')
}

export function formatMarkdown(src: string): string {
  const out: string[] = []
  let prev = 'blank' as Kind
  src = stripCommonIndent(src ?? '')

  /** Push a block, adding a blank line first if needed. */
  const push = (kind: Kind, lines: string[]) => {
    if (!lines.length) return
    const needBlank = prev !== 'blank' && (
      kind !== prev
      // Kinds that need a blank line even between blocks of the same kind: headings, tables, code blocks, HTML blocks each stand alone
      || kind === 'heading' || kind === 'table' || kind === 'code' || kind === 'html'
    )
    if (needBlank && out.length && out[out.length - 1].trim()) out.push('')
    out.push(...lines)
    prev = kind
  }

  for (const seg of splitFences((src ?? '').replace(/\r\n?/g, '\n').split('\n'))) {
    if (seg.code) {
      // A blank line before and after code blocks, not a character inside touched
      push('code', seg.lines.map((l) => l.replace(/\s+$/, '')))
      continue
    }
    let i = 0
    const lines = seg.lines
    // List indent widths seen in this passage (ascending). Two lists separated by a blank line are counted separately.
    let indents: number[] = []
    while (i < lines.length) {
      const raw = lines[i]
      const line = raw.replace(/\s+$/, '')

      // Tables: consecutive lines starting with | are handled as one block
      if (/^\s*\|/.test(line)) {
        const rows: string[] = []
        while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(lines[i].trim()); i++ }
        if (rows.length >= 2 && isSep(rows[1])) push('table', formatTable(rows))
        else push('para', rows)                  // not a valid table: leave it alone
        continue
      }
      i++

      if (!line.trim()) { prev = 'blank'; out.push(''); indents = []; continue }

      // Headings: `#Heading` -> `# Heading`, standing alone
      const h = /^(#{1,6})\s*(.*)$/.exec(line)
      if (h) { push('heading', [`${h[1]} ${cjkSpacing(h[2].trim())}`]); continue }

      // Quotes
      if (/^\s*>/.test(line)) {
        push('quote', [line.replace(/^(\s*>+)\s?/, (_m, g) => g.trim() + ' ').trimEnd()])
        continue
      }

      // HTML blocks (this app inserts <audio> itself)
      if (HTML_BLOCK.test(line)) { push('html', [line.trim()]); continue }

      // Lists: always -, indented 2 spaces per level; ordered lists always `1.`
      const li = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(line)
      if (li) {
        // **Levels are inferred from indent width, not fixed division.** Some use 2 spaces per level, some 4;
        // a hard-coded /2 would turn "one level of 4 spaces" into level two, and formatting would change the user's structure.
        const w = li[1].replace(/\t/g, '  ').length
        if (!indents.includes(w)) { indents.push(w); indents.sort((a, b) => a - b) }
        const level = indents.indexOf(w)
        const ordered = /^\d/.test(li[2])
        const marker = ordered ? li[2].replace(/\)$/, '.') : '-'
        // Nested child items count as the same block as the parent list (no blank line); only a change of kind at top level adds one
        const kind: Kind = ordered ? 'ol' : 'ul'
        if (level > 0 && (prev === 'ul' || prev === 'ol')) {
          out.push('  '.repeat(level) + marker + ' ' + cjkSpacing(li[3].trim()))
        } else {
          push(kind, ['  '.repeat(level) + marker + ' ' + cjkSpacing(li[3].trim())])
        }
        continue
      }

      push('para', [cjkSpacing(line.replace(/^\s+/, (m) => m.replace(/\t/g, '  ')))])
    }
  }
  // Squeeze consecutive blank lines into one, trim both ends, keep one trailing newline
  return out.join('\n').replace(/\n{3,}/g, '\n\n').replace(/^\n+/, '').replace(/\s+$/, '') + '\n'
}
