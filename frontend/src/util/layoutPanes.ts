
export const LAUNCHER_W = 80
export const MIN_EDITOR_W = 520

export interface PaneLayoutIn {
  winW: number
  panes: { leftW: number; rightW: number; leftOn: boolean; rightOn: boolean }
  /** The split width set by the user; null when the split is not open */
  splitW: number | null
  focusMode: boolean
}

export function layoutPanes({ winW, panes, splitW: wantSplit, focusMode }: PaneLayoutIn) {
  const compact = winW < 640
  const leftW = Math.min(panes.leftW, Math.floor(winW * 0.3))
  const splitW = wantSplit != null ? Math.min(wantSplit, Math.floor(winW * 0.45)) : 0
  const tooNarrowForRight = panes.leftOn && winW - LAUNCHER_W - leftW - panes.rightW - splitW < MIN_EDITOR_W
  const tooNarrowForLeft = wantSplit != null && winW - LAUNCHER_W - leftW - splitW < MIN_EDITOR_W
  return {
    leftW, splitW,
    leftShown: !focusMode && !compact && panes.leftOn && !tooNarrowForLeft,
    rightShown: !focusMode && !compact && panes.rightOn && !tooNarrowForRight,
  }
}


/** The minimum the left pane can shrink to (same number as Gutter's minimum). */
export const MIN_LEFT_W = 150


export function makeRoomForRight(
  panes: PaneLayoutIn['panes'], winW: number, splitW = 0,
): PaneLayoutIn['panes'] {
  const next = { ...panes, rightOn: true }
  if (!next.leftOn) return next
  const leftW = Math.min(next.leftW, Math.floor(winW * 0.3))
  const short = MIN_EDITOR_W - (winW - LAUNCHER_W - leftW - next.rightW - splitW)
  if (short <= 0) return next
  const shrunk = leftW - short
  return shrunk >= MIN_LEFT_W ? { ...next, leftW: shrunk } : { ...next, leftOn: false }
}
