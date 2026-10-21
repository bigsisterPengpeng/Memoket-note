import { EditorView } from '@codemirror/view'
import { toast } from '../toast'
import { uploadAsset } from '../api'
import { t } from '../i18n'

// Not a hard cap -- large images still get inlined, just with a heads-up,
// since the doc has no separate asset store to reject into. Base64 runs
// ~33% larger than the source file.
const WARN_BYTES = 3 * 1024 * 1024


function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}


async function insertImage(view: EditorView, file: File, pos: number) {
  const alt = file.name.replace(/\.[^.]+$/, '') || 'image'
  let src: string
  try {
    src = (await uploadAsset(file)).url
  } catch (e) {
    // Only "backend not connected" (fetch itself failed, TypeError) falls back to embedding. When the backend explicitly refused
    // (too large / unsupported type, 4xx) do as it says -- otherwise a 40MB image would be turned into 53MB of

    if (!(e instanceof TypeError)) {
      toast(t('Image not inserted: {err}', { err: e instanceof Error ? e.message.replace(/^\d{3} /, '') : String(e) }), 'error')
      return
    }
    if (file.size > WARN_BYTES) {
      toast(t('“{name}” is large ({mb}MB); the backend is unreachable so it was embedded inline — this note will get heavy', { name: file.name, mb: (file.size / 1024 / 1024).toFixed(1) }))
    }
    src = await fileToDataUrl(file)
  }
  const line = view.state.doc.lineAt(pos)
  const { at, text } = imageInsertion(line.text, line.to, pos, `![${alt}](${src})`)
  view.dispatch({
    changes: { from: at, to: at, insert: text },
    selection: { anchor: at + text.length },
  })
}


export function imageInsertion(lineText: string, lineTo: number, pos: number, md: string): { at: number; text: string } {
  if (!lineText.trim()) return { at: pos, text: md }
  return { at: lineTo, text: `\n\n${md}\n` }
}

export const imagePaste = EditorView.domEventHandlers({
  paste(event, view) {
    const items = event.clipboardData?.items
    if (!items) return false
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile()
        if (file) {
          event.preventDefault()
          void insertImage(view, file, view.state.selection.main.from)
          return true
        }
      }
    }
    return false
  },
  drop(event, view) {
    const files = event.dataTransfer?.files
    if (!files || files.length === 0) return false
    const imageFile = Array.from(files).find((f) => f.type.startsWith('image/'))
    if (!imageFile) return false
    event.preventDefault()
    const pos = view.posAtCoords({ x: event.clientX, y: event.clientY }) ?? view.state.selection.main.from
    void insertImage(view, imageFile, pos)
    return true
  },
})
