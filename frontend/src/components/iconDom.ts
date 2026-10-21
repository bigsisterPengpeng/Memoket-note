
import { createElement } from 'react'
import { createRoot } from 'react-dom/client'

import Icon from './Icon'

export function mountIcon(el: HTMLElement, name: string): () => void {
  const root = createRoot(el)
  root.render(createElement(Icon, { n: name }))
  // Defer unmount by a tick: when CM6 destroys a widget it may be in the middle of React rendering,
  // and a synchronous unmount triggers the "Attempted to synchronously unmount" warning.
  return () => setTimeout(() => root.unmount(), 0)
}
