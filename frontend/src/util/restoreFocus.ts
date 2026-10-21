/** After an overlay closes, return focus to the element that had it before opening.
 *
 *  Confirm dialogs / pickers / quick view / the shortcuts table are all "entered from some button or menu, return on close"; focus used to fall to body on close,
 *  and keyboard users had to Tab back to where they were. Record activeElement on mount, and on unmount focus it again if it is still on the page. */
import { useEffect } from 'react'

export function useRestoreFocus(): void {
  useEffect(() => {
    const prev = document.activeElement instanceof HTMLElement ? document.activeElement : null
    return () => {
      if (prev && prev.isConnected && typeof prev.focus === 'function') prev.focus()
    }
  }, [])
}
