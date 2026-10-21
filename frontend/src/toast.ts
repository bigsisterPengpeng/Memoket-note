/** Minimal toast store -- external-store pattern (subscribe/getSnapshot) so
 * any module can call toast(...) without prop-drilling a setter through the
 * whole component tree, and <Toaster/> is the only thing that re-renders
 * when toasts change. Replaces the scattered alert() calls that used to
 * block the whole page for routine "failed, try again" messages. */

export type Toast = {
  id: number
  message: string
  kind: 'error' | 'info'
  action?: { label: string; onClick: () => void }
}

let toasts: Toast[] = []
let seq = 0
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((l) => l())
}

export function toast(message: string, kind: Toast['kind'] = 'info') {
  const id = seq++
  toasts = [...toasts, { id, message, kind }]
  emit()
  setTimeout(() => dismissToast(id), kind === 'error' ? 6000 : 3500)
}

/** Toast with an action button that auto-dismisses after `ms` -- the
 * "deleted a note, undo?" pattern. Deliberately not folded into toast()'s
 * signature: this one needs a longer, fixed lifetime tied to the caller's
 * own undo window, not the message-length-based defaults above. */
export function toastAction(message: string, actionLabel: string, onAction: () => void, ms = 5000, kind: Toast['kind'] = 'info') {
  const id = seq++
  toasts = [...toasts, {
    id, message, kind,
    action: { label: actionLabel, onClick: () => { onAction(); dismissToast(id) } },
  }]
  emit()
  setTimeout(() => dismissToast(id), ms)
}

export function dismissToast(id: number) {
  toasts = toasts.filter((t) => t.id !== id)
  emit()
}

export function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getSnapshot() {
  return toasts
}
