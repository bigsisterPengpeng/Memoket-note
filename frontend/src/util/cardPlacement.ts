
export type Rect = { left: number; top: number; right: number; bottom: number; width: number; height: number }

export const CARD_WIDTH = 340
const GAP = 10
const EDGE = 8

/** A gap between the card and the body: in `below` / `above` the card sits on the body, and without this gap it looks "glued to the text". */
const SEAM = 6

export function placeCard(anchor: Rect, bounds: Rect, cardH: number, winH: number, want = CARD_WIDTH): { left: number; top: number; width: number; side: 'right' | 'below' | 'above' } {

  // `anchor.left - width + 4` gave a left edge 16px past the column's left, and `Math.min` only took the smaller --

  // Clamp both ends: first cap by the column's right edge, then floor by its left edge (reversed, the left would still leak).
  const width = Math.max(200, Math.min(want, bounds.width - EDGE * 2))
  const clampTop = (t: number) => Math.max(EDGE, Math.min(t, winH - EDGE - cardH))
  const clampLeft = (l: number) => Math.max(bounds.left + EDGE, Math.min(l, bounds.right - EDGE - width))
  if (anchor.right + GAP + width <= bounds.right - EDGE) {
    return { left: anchor.right + GAP, top: clampTop(anchor.top - 8), width, side: 'right' }
  }
  const left = clampLeft(anchor.left - width + 4)
  if (anchor.bottom + SEAM + cardH <= winH - EDGE) return { left, top: anchor.bottom + SEAM, width, side: 'below' }
  return { left, top: clampTop(anchor.top - SEAM - cardH), width, side: 'above' }
}


export function seamPush(side: 'right' | 'below' | 'above', cardH: number): number {
  return side === 'below' ? cardH + SEAM * 2 : 0
}



export function pushLineBelow(at: { left: number; top: number; bottom: number }, px: number): () => void {
  if (px <= 0 || typeof document === 'undefined') return () => {}
  // The anchor may fall in the margin gutter (the dot), which is not a .cm-line: move a little into the body and take it there
  const probeX = at.left + 40
  const probeY = (at.top + at.bottom) / 2
  const el = (document.elementFromPoint(probeX, probeY) as HTMLElement | null)?.closest('.cm-line') as HTMLElement | null
  if (!el) return () => {}
  const before = el.style.paddingBottom
  el.style.paddingBottom = `${px}px`
  el.dataset.cardSeam = '1'
  return () => {
    el.style.paddingBottom = before
    delete el.dataset.cardSeam
  }
}
