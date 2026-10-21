import { parseMini, type Block, type Inline } from './miniMarkdown'
import { slidePages } from './slidePages'

/** Slides markdown -> an HTML document that can be printed straight to PDF.
 *
 * **Zero new dependencies**: the Electron main process can already `printToPDF`, so everything "Export PDF"
 * needs is a laid-out HTML document. No Marp (600KB+), no python-pptx.
 *
 * One `<section>` per page, 16:9, `page-break-after: always` -- one page printed is one page.
 * Styles come from the app (the same greys and font sizes); **no theme picker**: picking themes is a slides app's job.
 */

const esc = (s: string) => s.replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string))

const ink = (parts: Inline[]) => parts.map((p) =>
  p.t === 'b' ? `<b>${esc(p.s)}</b>` : p.t === 'code' ? `<code>${esc(p.s)}</code>` : esc(p.s)).join('')

function blockHtml(b: Block, svgs: Map<string, string>): string {
  if (b.kind === 'h') return `<h2>${ink(b.parts)}</h2>`
  if (b.kind === 'ul') return `<ul>${b.items.map((it) => `<li>${ink(it)}</li>`).join('')}</ul>`
  if (b.kind === 'pre') {
    // **Diagrams must be diagrams**: the print step runs in an offscreen window with JS off, so the SVG must be rendered
    // by the caller and passed in (`svgs`). If it cannot be rendered (or the caller did not), print the source honestly --

    const svg = svgs.get(b.text.trim())
    if (svg) return `<figure class="diagram">${svg}</figure>`
    return `<pre>${esc(b.text)}</pre>`
  }
  return `<p>${ink(b.parts)}</p>`
}

/** `svgs`: mermaid source -> rendered SVG. The caller renders first (`editor/mermaid.mermaidSvg`),
 *  because the window doing the printing has JS off. */
export function slidesToHtml(title: string, md: string, svgs = new Map<string, string>()): string {
  const pages = slidePages(md)
  const body = pages.map((p, i) => {
    // Each page's title was already extracted by slidePages; do not show it again in the body
    const blocks = parseMini(p.body).filter((b) => b.kind !== 'h').map((b) => blockHtml(b, svgs)).join('\n')
    return `<section${i === 0 ? ' class="cover"' : ''}>
  <h1>${esc(p.title)}</h1>
  ${blocks}
  <footer>${i + 1} / ${pages.length}</footer>
</section>`
  }).join('\n')

  return `<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>${esc(title)}</title><style>
  @page { size: 1280px 720px; margin: 0; }
  * { box-sizing: border-box; }
  body { margin: 0; font: 16px/1.6 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; color: #1a1a19; }
  section { position: relative; width: 1280px; height: 720px; padding: 72px 88px 64px;
            page-break-after: always; break-after: page; background: #fff; overflow: hidden; }
  section:last-child { page-break-after: auto; break-after: auto; }
  h1 { margin: 0 0 28px; font-size: 40px; line-height: 1.25; font-weight: 700; }
  section.cover { display: flex; flex-direction: column; justify-content: center; }
  section.cover h1 { font-size: 56px; }
  p { margin: 0 0 14px; font-size: 22px; }
  ul { margin: 0; padding-inline-start: 28px; }
  li { margin: 0 0 12px; font-size: 22px; line-height: 1.5; }
  code { font-family: ui-monospace, Menlo, monospace; font-size: 18px;
         background: #f1f1ef; border-radius: 4px; padding: 1px 5px; }
  /* Citation ids one size smaller and greyed: they are **credentials**, not part of the body -- but must stay visible,
     otherwise this PDF would be no different from one made by a generic tool */
  li code, p code { color: #6b6b66; }
  pre { margin: 0 0 14px; font-family: ui-monospace, Menlo, monospace; font-size: 15px;
        line-height: 1.5; white-space: pre-wrap; background: #f7f7f5; border-radius: 6px; padding: 12px 14px; }
  figure.diagram { margin: 0; display: flex; justify-content: center; align-items: center; height: 480px; }
  figure.diagram svg { max-width: 100%; max-height: 100%; }
  footer { position: absolute; inset-inline-end: 88px; inset-block-end: 40px;
           font-size: 14px; color: #9a9a94; }
</style></head><body>
${body}
</body></html>`
}
