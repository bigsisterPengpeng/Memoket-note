/**
 * Split-pane drag handle — Trilium uses Split.js (`services/resizer.ts`); 8 lines of
 * pointermove are enough for us: 5px wide, transparent by default, visible only on hover (theme-next/shell.css:161-168).
 *
 * `side` says "which side's pane width the drag changes": the left pane's handle is on its right,
 * dragging right widens the left pane; the right pane's handle is on its left, dragging right narrows the right pane.
 */
import { useRef } from 'react'

export default function Gutter({ side, onResize, onResizeEnd }: {
  side: 'left' | 'right'
  onResize: (delta: number) => void
  onResizeEnd?: () => void
}) {
  const last = useRef(0)
  return (
    <div
      className="gutter"
      role="separator"
      aria-orientation="vertical"
      onPointerDown={(e) => {
        e.preventDefault()
        last.current = e.clientX
        const el = e.currentTarget
        el.setPointerCapture(e.pointerId)
        el.classList.add('dragging')
      }}
      onPointerMove={(e) => {
        if (!e.currentTarget.hasPointerCapture(e.pointerId)) return
        const dx = e.clientX - last.current
        last.current = e.clientX
        onResize(side === 'left' ? dx : -dx)
      }}
      onPointerUp={(e) => {
        e.currentTarget.releasePointerCapture(e.pointerId)
        e.currentTarget.classList.remove('dragging')
        onResizeEnd?.()
      }}
    />
  )
}
