import { syntaxTree } from '@codemirror/language'
import { StateField, type EditorState, type Range } from '@codemirror/state'
import { Decoration, EditorView, WidgetType, type DecorationSet } from '@codemirror/view'

class ImageWidget extends WidgetType {
  constructor(readonly src: string, readonly alt: string) { super() }
  eq(other: ImageWidget) { return other.src === this.src && other.alt === this.alt }
  toDOM() {
    const img = document.createElement('img')
    img.src = this.src
    img.alt = this.alt
    img.className = 'cm-image-embed'
    return img
  }
  // false lets CM6 compute cursor placement through/around the widget, so
  // clicking an image drops the cursor next to it instead of the click
  // being swallowed -- needed to get back into edit mode for that markdown.
  ignoreEvent() { return false }
}

const IMAGE_RE = /^!\[([^\]]*)\]\(([^)]+)\)$/

/** ![alt](src) renders as an actual <img>, replacing the raw markdown --
 * except on the line the cursor is currently on, where it falls back to
 * plain (dimmed, like other syntax) text so there's always a way to edit
 * the alt/src without a separate "edit mode" UI. Same reasoning as the
 * mermaid preview: this only makes sense as a StateField (see mermaid.ts's
 * comment on why a ViewPlugin providing decorations here would crash). */
function imageDecorations(state: EditorState): DecorationSet {
  const decos: Range<Decoration>[] = []
  const cursor = state.selection.main.head
  syntaxTree(state).iterate({
    enter: (node) => {
      if (node.name !== 'Image') return
      if (cursor >= node.from && cursor <= node.to) return
      const text = state.doc.sliceString(node.from, node.to)
      const m = IMAGE_RE.exec(text)
      if (!m) return
      const [, alt, src] = m
      decos.push(Decoration.replace({ widget: new ImageWidget(src, alt) }).range(node.from, node.to))
    },
  })
  return Decoration.set(decos, true)
}

export const imageEmbed = StateField.define<DecorationSet>({
  create(state) {
    return imageDecorations(state)
  },
  update(value, tr) {
    return tr.docChanged || tr.selection ? imageDecorations(tr.state) : value
  },
  provide: (f) => EditorView.decorations.from(f),
})
