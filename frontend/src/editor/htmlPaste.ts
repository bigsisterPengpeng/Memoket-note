
import { EditorView } from '@codemirror/view'

/** Only these tags count as "formatted" and worth converting. */
const RICH = 'h1,h2,h3,h4,h5,h6,ul,ol,a[href],strong,b,em,i,blockquote,table,img,pre,code,hr,s,del,strike,input[type=checkbox]'

const BLOCK = new Set(['P', 'DIV', 'SECTION', 'ARTICLE', 'HEADER', 'FOOTER', 'MAIN', 'ASIDE', 'NAV', 'FIGURE', 'FIGCAPTION', 'DL', 'DT', 'DD', 'ADDRESS', 'DETAILS', 'SUMMARY'])
const SKIP = new Set(['SCRIPT', 'STYLE', 'HEAD', 'META', 'LINK', 'TITLE', 'TEMPLATE', 'NOSCRIPT', 'BUTTON', 'SELECT', 'TEXTAREA'])

function parse(html: string): HTMLElement {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  return doc.body
}

/** Google Docs wraps the whole passage in `<b style="font-weight:normal">`; Word's `<span style="font-weight:bold">` is the real bold */
function isBold(el: Element): boolean {
  const fw = (el as HTMLElement).style?.fontWeight ?? ''
  if (el.tagName === 'STRONG' || el.tagName === 'B') return !/^(normal|[1-4]00)$/.test(fw)
  return /^(bold|bolder|[6-9]00)$/.test(fw)
}
function isItalic(el: Element): boolean {
  if (el.tagName === 'EM' || el.tagName === 'I') return true
  return /italic|oblique/.test((el as HTMLElement).style?.fontStyle ?? '')
}

function esc(s: string): string { return s.replace(/\|/g, '\\|') }
function collapse(s: string): string { return s.replace(/[ \t\r\n ]+/g, ' ') }

/** Inline content: returns one line (no newlines; `<br>` becomes `\n`). */
function inline(node: Node, pre = false): string {
  if (node.nodeType === Node.TEXT_NODE) return pre ? (node.textContent ?? '') : collapse(node.textContent ?? '')
  if (node.nodeType !== Node.ELEMENT_NODE) return ''
  const el = node as Element
  if (SKIP.has(el.tagName)) return ''
  const kids = () => Array.from(el.childNodes).map((c) => inline(c, pre)).join('')
  switch (el.tagName) {
    case 'BR': return '\n'
    case 'IMG': { const src = el.getAttribute('src') ?? ''; if (!src) return ''; return `![${collapse(el.getAttribute('alt') ?? '')}](${src})` }
    case 'A': {
      const href = el.getAttribute('href') ?? ''
      const text = kids().trim()
      if (!href || /^(javascript|#)/.test(href)) return text
      if (!text || text === href) return href
      return `[${text}](${href})`
    }
    case 'CODE': { const t = kids(); return t.trim() ? '`' + t.replace(/`/g, '`') + '`' : '' }
    case 'S': case 'DEL': case 'STRIKE': { const t = kids(); return t.trim() ? `~~${t.trim()}~~` : t }
    case 'INPUT': return ''
    default: {
      let t = kids()
      if (!t.trim()) return t
      // Bold / italic: the markers hug the text, surrounding whitespace moves outside (`** bold **` is not bold)
      const wrap = (m: string) => { const lead = /^\s*/.exec(t)![0]; const trail = /\s*$/.exec(t)![0]; t = `${lead}${m}${t.trim()}${m}${trail}` }
      if (isBold(el)) wrap('**')
      if (isItalic(el)) wrap('*')
      return t
    }
  }
}

function blocks(node: Node, out: string[], ctx: { indent: string; quote: boolean }) {
  if (node.nodeType === Node.TEXT_NODE) { const t = collapse(node.textContent ?? '').trim(); if (t) out.push(t); return }
  if (node.nodeType !== Node.ELEMENT_NODE) return
  const el = node as Element
  if (SKIP.has(el.tagName)) return
  const tag = el.tagName
  const m = /^H([1-6])$/.exec(tag)
  if (m) { const t = inline(el).trim(); if (t) out.push('#'.repeat(Number(m[1])) + ' ' + t.replace(/\n/g, ' ')); return }
  if (tag === 'HR') { out.push('---'); return }
  if (tag === 'PRE') {
    const code = el.querySelector('code')
    const lang = /language-(\w+)/.exec(code?.className ?? '')?.[1] ?? ''
    out.push('```' + lang + '\n' + (el.textContent ?? '').replace(/\n$/, '') + '\n```')
    return
  }
  if (tag === 'BLOCKQUOTE') {
    const inner: string[] = []
    for (const c of Array.from(el.childNodes)) blocks(c, inner, ctx)
    out.push(inner.join('\n\n').split('\n').map((l) => '> ' + l).join('\n'))
    return
  }
  if (tag === 'UL' || tag === 'OL') {
    const items: string[] = []
    let n = Number(el.getAttribute('start') ?? 1) || 1
    for (const li of Array.from(el.children)) {
      if (li.tagName !== 'LI') continue
      const marker = tag === 'OL' ? `${n++}. ` : '- '
      const box = li.querySelector(':scope > input[type=checkbox], :scope > p > input[type=checkbox], :scope > label > input[type=checkbox]') as HTMLInputElement | null
      const task = box ? (box.checked ? '[x] ' : '[ ] ') : ''
      // An item's inline text and nested lists are handled separately
      const own: string[] = []
      const nested: string[] = []
      for (const c of Array.from(li.childNodes)) {
        if (c.nodeType === Node.ELEMENT_NODE && ((c as Element).tagName === 'UL' || (c as Element).tagName === 'OL')) {
          blocks(c, nested, { indent: ctx.indent + '  ', quote: ctx.quote })
        } else if (c.nodeType === Node.ELEMENT_NODE && BLOCK.has((c as Element).tagName)) {
          const t = inline(c).trim(); if (t) own.push(t)
        } else { own.push(inline(c)) }
      }
      const text = own.join('').replace(/\n+/g, ' ').replace(/\s+/g, ' ').trim()
      let line = ctx.indent + marker + task + text
      if (nested.length) line += '\n' + nested.join('\n')          // sublists carry their own indent (given during the recursion above)
      items.push(line)
    }
    out.push(items.join('\n'))
    return
  }
  if (tag === 'TABLE') {
    const rows = Array.from(el.querySelectorAll('tr')).map((tr) => Array.from(tr.children).map((c) => esc(inline(c).replace(/\n/g, ' ').trim())))
    if (!rows.length) return
    const cols = Math.max(...rows.map((r) => r.length))
    const pad = (r: string[]) => { while (r.length < cols) r.push(''); return r }
    const line = (r: string[]) => '| ' + pad(r).join(' | ') + ' |'
    out.push([line(rows[0]), '|' + ' --- |'.repeat(cols), ...rows.slice(1).map(line)].join('\n'))
    return
  }
  if (tag === 'LI') { const t = inline(el).trim(); if (t) out.push('- ' + t); return }
  // Block container: either all inline inside (joined into one paragraph), or child blocks (recurse)
  const kids = Array.from(el.childNodes)
  const hasBlockChild = kids.some((c) => c.nodeType === Node.ELEMENT_NODE && (BLOCK.has((c as Element).tagName) || /^(H[1-6]|UL|OL|PRE|BLOCKQUOTE|TABLE|HR|LI)$/.test((c as Element).tagName)))
  if (!hasBlockChild) { const t = inline(el).trim(); if (t) out.push(t); return }
  let run: Node[] = []
  const flush = () => { if (run.length) { const t = run.map((c) => inline(c)).join('').trim(); if (t) out.push(t); run = [] } }
  for (const c of kids) {
    if (c.nodeType === Node.ELEMENT_NODE && (BLOCK.has((c as Element).tagName) || /^(H[1-6]|UL|OL|PRE|BLOCKQUOTE|TABLE|HR|LI)$/.test((c as Element).tagName))) { flush(); blocks(c, out, ctx) }
    else run.push(c)
  }
  flush()
}

/** HTML -> Markdown. A blank line between blocks; inline bold / italic / code / links / strikethrough; lists with nesting and task boxes; tables to GFM. */
export function htmlToMarkdown(html: string): string {
  const body = parse(html)
  const out: string[] = []
  blocks(body, out, { indent: '', quote: false })
  return out.join('\n\n').replace(/[ \t]+$/gm, '').replace(/\n{3,}/g, '\n\n').trim()
}

/** Whether this HTML is worth converting: it has semantic tags, and the result differs from plain by more than whitespace. */
export function shouldConvertHtml(html: string, plain: string): boolean {
  if (!html) return false
  const body = parse(html)
  if (!body.querySelector(RICH)) return false
  const md = htmlToMarkdown(html)
  if (!md) return false
  const norm = (s: string) => s.replace(/\s+/g, '')
  return norm(md) !== norm(plain)
}

/** Paste: formatted HTML is converted to markdown and inserted; everything else goes to CM (images go through imagePaste, which runs first). */
export const htmlPaste = EditorView.domEventHandlers({
  paste(event, view) {
    const cd = event.clipboardData
    if (!cd) return false
    if (Array.from(cd.items ?? []).some((i) => i.type.startsWith('image/'))) return false
    const html = cd.getData('text/html')
    const plain = cd.getData('text/plain')
    if (!shouldConvertHtml(html, plain)) return false
    const md = htmlToMarkdown(html)
    event.preventDefault()
    const { from, to } = view.state.selection.main
    // Pasting into the middle of a line: block content gets a blank line before and after, so it does not stick to this line's text
    const line = view.state.doc.lineAt(from)
    const multi = md.includes('\n') || /^(#|- |\d+\. |> |```|\|)/.test(md)
    const before = multi && line.text.slice(0, from - line.from).trim() ? '\n\n' : ''
    const after = multi && line.text.slice(to - line.from).trim() ? '\n\n' : ''
    const insert = before + md + after
    view.dispatch({ changes: { from, to, insert }, selection: { anchor: from + insert.length }, userEvent: 'input.paste', scrollIntoView: true })
    return true
  },
})
