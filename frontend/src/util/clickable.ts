
import type { KeyboardEvent, MouseEvent } from 'react'

export function clickable<T extends HTMLElement>(onClick: (e: MouseEvent<T> | KeyboardEvent<T>) => void) {
  return {
    role: 'button' as const,
    tabIndex: 0,
    onClick,
    onKeyDown: (e: KeyboardEvent<T>) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(e) }
    },
  }
}
