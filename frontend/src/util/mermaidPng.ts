
import { getUser, type MermaidBlocks, type RendersOut } from '../api'
import { mermaidSvg } from '../editor/mermaid'
import { t } from '../i18n'

/** The init directive for export: light theme + pure SVG labels. Sources that already carry an init get no second one. */
export const EXPORT_INIT = '%%{init: {"theme":"default","flowchart":{"htmlLabels":false}}}%%\n'
/** 2x scale: Feishu / Notion show images at their original size, and 1x text is blurry */
export const EXPORT_SCALE = 2

export function withExportInit(code: string): string {
  return /^\s*%%\{\s*init/.test(code) ? code : EXPORT_INIT + code
}

/** mermaid SVG width and height: the `width="100%"` it gives cannot be measured, so read the viewBox (falling back to the width/height attributes if absent). */
export function svgSize(svg: string): { w: number; h: number } | null {
  const vb = svg.match(/viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)\s*"/)
  if (vb) {
    const w = Number(vb[1]); const h = Number(vb[2])
    if (w > 0 && h > 0) return { w, h }
  }
  const w = Number(svg.match(/\swidth="([\d.]+)(?:px)?"/)?.[1])
  const h = Number(svg.match(/\sheight="([\d.]+)(?:px)?"/)?.[1])
  return w > 0 && h > 0 ? { w, h } : null
}

/** Give `<svg>` explicit pixel width and height (removing things like `width="100%"`) so `<img>` can measure its size. */
export function sizedSvg(svg: string, size: { w: number; h: number }): string {
  return svg.replace(/<svg\b([^>]*)>/, (_m, attrs: string) => {
    const rest = attrs.replace(/\s(?:width|height)="[^"]*"/g, '')
    return `<svg${rest} width="${size.w}" height="${size.h}">`
  })
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(t('Could not render the SVG')))
    img.src = url
  })
}

/** SVG string -> a URL `<img>` can load. **Use data:, not blob:** -- in real Chromium (the desktop shell) the labels in mermaid's SVG are
 *  `<foreignObject>` (the init directive disabling htmlLabels did not take), and a blob: URL loaded into `<img>` and drawn on a canvas makes `toDataURL` throw
 *  "Tainted canvases may not be exported"; the same SVG via a data: URL drew at 1449x94 and exported a PNG. */
export function svgDataUrl(svg: string): string {
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
}

/** SVG string -> PNG data URL (white background, `scale` times). null without canvas (test environments) / when drawing fails. */
export async function svgToPng(svg: string, scale = EXPORT_SCALE): Promise<string | null> {
  const size = svgSize(svg)
  if (!size || typeof document === 'undefined') return null
  const url = svgDataUrl(sizedSvg(svg, size))
  try {
    const img = await loadImage(url)
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.ceil(size.w * scale))
    canvas.height = Math.max(1, Math.ceil(size.h * scale))
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    const out = canvas.toDataURL('image/png')
    return out.startsWith('data:image/png') ? out : null
  } catch {
    return null
  }
}

/** A mermaid source -> PNG data URL; null on syntax errors / render failures (the backend degrades it to a code block). */
export async function renderMermaidPng(code: string): Promise<string | null> {
  try {
    const svg = await mermaidSvg(withExportInit(code))
    return svg ? await svgToPng(svg) : null
  } catch {
    return null
  }
}

export type Renderer = (code: string) => Promise<string | null>

/** The backend's {hash: source} -> {hash: PNG}; failed renders are left out. Rendered one at a time (mermaid's render cannot run concurrently with the same id). */
export async function collectMermaidRenders(blocks: MermaidBlocks, render: Renderer = renderMermaidPng): Promise<Record<string, string>> {
  const out: Record<string, string> = {}
  for (const [key, code] of Object.entries(blocks)) {
    const png = await render(code)
    if (png) out[key] = png
  }
  return out
}

async function postJson<T>(path: string, body: unknown, fetcher: typeof fetch): Promise<T> {
  const res = await fetcher(path, { method: 'POST', headers: { 'X-User-Id': getUser(), 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`${res.status}`)
  return res.json() as Promise<T>
}

/**
 * The step before exporting back to Feishu: ask the backend for mermaid sources -> render -> hand them back. Returns how many were handed back; **every failure returns 0 without throwing** --
 * a diagram failing to render should not block the whole export (the backend degrades it to a code block + one line of explanation).
 */
export async function exportMermaidRenders(noteIds: string[], render: Renderer = renderMermaidPng, fetcher: typeof fetch = fetch): Promise<number> {
  try {
    const blocks = await postJson<MermaidBlocks>('/api/export/mermaid', { note_ids: noteIds }, fetcher)
    if (!Object.keys(blocks).length) return 0
    const renders = await collectMermaidRenders(blocks, render)
    if (!Object.keys(renders).length) return 0
    const r = await postJson<RendersOut>('/api/export/renders', { renders }, fetcher)
    return r.stored
  } catch {
    return 0
  }
}
