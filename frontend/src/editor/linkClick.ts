import { syntaxTree } from '@codemirror/language'
import { EditorView } from '@codemirror/view'

/** Cmd/Ctrl+click a markdown link to open it -- plain click still just
 * places the cursor for editing, matching Obsidian/VSCode convention.
 * Doing nothing on plain click is deliberate: a text editor where clicking
 * a link navigates away instead of editing would make links impossible to
 * edit by clicking into them. */
export const linkClick = EditorView.domEventHandlers({
  click(event, view) {
    if (!(event.metaKey || event.ctrlKey)) return false
    const pos = view.posAtCoords({ x: event.clientX, y: event.clientY })
    if (pos == null) return false
    let url: string | null = null
    syntaxTree(view.state).iterate({
      from: pos,
      to: pos,
      enter: (node) => {
        if (node.name === 'URL') url = view.state.doc.sliceString(node.from, node.to)
      },
    })
    if (!url) return false
    // In-note links: `note://<id>` is handed to the shell to open that note, without leaving the window
    const m = /^note:\/\/([0-9a-f]{12})$/.exec(url)
    if (m) { window.dispatchEvent(new CustomEvent('open-note', { detail: m[1] })); return true }
    window.open(url, '_blank', 'noopener,noreferrer')
    return true
  },
})
