import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import { Compartment, EditorState } from '@codemirror/state'
import type { TransactionSpec } from '@codemirror/state'
import { EditorView, keymap, placeholder as cmPlaceholder } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { autocompletion, completionKeymap } from '@codemirror/autocomplete'
import { search, searchKeymap } from '@codemirror/search'
import { markdown } from '@codemirror/lang-markdown'
import { languages } from '@codemirror/language-data'
import { GFM } from '@lezer/markdown'
import { factPeek } from '../api'
import type { Revision } from '../api'
import { imageEmbed } from '../editor/imageEmbed'
import { imagePaste } from '../editor/imagePaste'
import { htmlPaste } from '../editor/htmlPaste'
import { listExitKeymap } from '../editor/listExit'
import { aiSyncSpec } from '../editor/undoUnit'
import { syncedFromApp, isAppEcho } from '../editor/syncEcho'
import { linkClick } from '../editor/linkClick'
import { markdownKeymap } from '../editor/markdownCommands'
import { factCite } from '../editor/factCite'
import { mermaidPreview } from '../editor/mermaid'
import { runningBlocks } from '../editor/runningBlocks'
import { tablePreview } from '../editor/tablePreview'
import { recallSource } from '../editor/recallCompletion'
import { noteLinkSource } from '../editor/noteLinkCompletion'
import { noteLinkChips } from '../editor/noteLink'
import { minimalChange } from '../editor/minimalChange'
import { getNote } from '../api'
import { taskCheckbox } from '../editor/taskCheckbox'
import { revisionField, setRevisions, revisionClickHandler } from '../editor/revisions'
import { addLayer, pendingHunks, roundDiffField, roundDiff as roundDiffExt, type DiffPush }
  from '../editor/roundDiff'
import { marginMemory, setMarginMarks, type MarginMark, type MarginOpen } from '../editor/marginMemory'
import { altHover, type AltHoverOpen } from '../editor/altHover'
import { slashMenu, type SlashItem } from '../editor/slashMenu'
import { markdownHighlight, dimSyntaxMarks, editorTheme, scrollPadding, syntaxHighlighting } from '../editor/theme'
import { frontmatterDim } from '../editor/frontmatter'
import { t } from '../i18n'

/**
 * Markdown-native editor (CodeMirror 6): the document is always a single
 * plain string, same contract as the old plain <textarea aria-label="Note body"> -- so the
 * anchor-based revision system (LLM returns an exact substring of `content`
 * to highlight) needed zero backend changes. On top of that plain string,
 * CM6 adds real markdown syntax styling, dimmed (not hidden) delimiter
 * characters, live-rendered mermaid diagrams under fenced ```mermaid
 * blocks, and revision highlights as native decorations instead of the old
 * transparent-textarea-over-backdrop hack.
 */


type Props = {
  content: string
  onChange?: (v: string) => void
  revisions?: Revision[]
  onAcceptInline?: (r: Revision) => void
  placeholder?: string
  viewRef?: RefObject<EditorView | null>
  /** Read-only rendering (e.g. a generated digest) -- still gets markdown
   * styling and rendered mermaid blocks, just no typing/completion/revisions. */
  readOnly?: boolean
  /** 30vh of padding under the body (main editor only; read-only mini panes do not want it). */
  scrollPad?: boolean
  /** Read-only highlight of "what this harness round changed": insertions in green, deleted original text restored
   * in place with strikethrough. Not the same as revisions -- those are suggestions awaiting acceptance, these are changes already
   * auto-applied, and otherwise the user would have no idea where the body was touched. */
  /** Push a proposal layer into the editor (dispatched only when seq changes). null = leave it alone. */
  roundDiff?: DiffPush | null

  undoGroup?: number
  /** How many harness changes are still neither accepted nor reverted. Used to show "N changes ·
   * Accept all" above the editor -- per-change clicking is the main path, but with many changes there must be a one-shot way to finish. */
  onPendingDiff?: (n: number) => void

  onLayersChanged?: () => void
  /** Right-click on a selected passage. **The listener is installed here rather than in App**: App's version
   * read `editorViewRef.current` inside `useEffect(..., [current])` and then called addEventListener;
   * if the ref was not filled yet it returned without retrying, and once the editor remounted (EditorView destroyed and rebuilt)
   * the listener stayed on the destroyed old DOM, and right-click never responded again. Installed in the view's own mount
   * effect, the lifecycles line up naturally. */
  onSelectionContextMenu?: (x: number, y: number, text: string) => void
  /** Report when the paragraph at the cursor (between blank lines) changes -- the right pane's "Memory" queries relations by it, not by the last 500 characters */
  onCursorParagraph?: (text: string) => void
  /** Margin memory: which paragraphs relate to the knowledge base; a dot lights up right of the paragraph's first line */
  marginMarks?: MarginMark[]

  onMarginClick?: MarginOpen

  onAltHover?: AltHoverOpen
  /** An item was picked in the insert menu opened by `/`. The extension only reports "which item was picked, where `/` spans";
   * what to do (run the harness, upload an image, record) is decided by the layer above -- a CM6 extension should not contain network
   * requests and file uploads. */
  onSlash?: (item: SlashItem, from: number, to: number, preset?: boolean) => void
  /** The user clicked stop on a "running" placeholder block. */
  onStopRun?: (id: string) => void

  onRetryRun?: (id: string) => void
}

/** The paragraph at the cursor: search up and down to the nearest blank line. A heading line counts as its own paragraph. */
export function paragraphAt(doc: { lineAt(pos: number): { number: number; text: string }; lines: number; line(n: number): { text: string } }, pos: number): string {
  const cur = doc.lineAt(pos)
  if (!cur.text.trim()) return ''
  if (/^#{1,6}\s/.test(cur.text)) return cur.text.trim()
  let a = cur.number
  let b = cur.number
  while (a > 1 && doc.line(a - 1).text.trim() && !/^#{1,6}\s/.test(doc.line(a - 1).text)) a--
  while (b < doc.lines && doc.line(b + 1).text.trim() && !/^#{1,6}\s/.test(doc.line(b + 1).text)) b++
  const out: string[] = []
  for (let i = a; i <= b; i++) out.push(doc.line(i).text)
  return out.join('\n').trim()
}

export default function MarkdownEditor({
  content, onChange, revisions = [], onAcceptInline, placeholder, viewRef, readOnly = false, scrollPad = false,
  roundDiff = null, undoGroup = 0, onPendingDiff, onLayersChanged, onSelectionContextMenu, onSlash, onStopRun, onRetryRun, onCursorParagraph, marginMarks, onMarginClick, onAltHover,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const lastPending = useRef(-1)
  const lastLayers = useRef<unknown>(undefined)
  const fallbackViewRef = useRef<EditorView | null>(null)
  const actualViewRef = viewRef ?? fallbackViewRef
  // The EditorView is long-lived and reads through this ref instead of
  // being torn down/recreated on every prop change -- only `content` and
  // `revisions` need an actual dispatch into CM6 state, callbacks don't.
  const liveRef = useRef({ onChange, onAcceptInline, revisions, onPendingDiff, onLayersChanged,
                          onSelectionContextMenu, onSlash, onStopRun, onRetryRun, onCursorParagraph, onMarginClick, onAltHover })
  useEffect(() => {
    liveRef.current = { onChange, onAcceptInline, revisions, onPendingDiff, onLayersChanged,
                        onSelectionContextMenu, onSlash, onStopRun, onRetryRun, onCursorParagraph, onMarginClick, onAltHover }
  })
  const lastPara = useRef('')

  // Tracks the last doc text CM6 itself emitted via onChange, so the
  // content-sync effect below can tell "this update is React echoing our
  // own edit back" apart from "this is a genuinely external change" (note
  // switch, magic-tap streaming, revision accepted) without a feedback loop.
  const lastEmitted = useRef(content)
  const readOnlyComp = useRef(new Compartment())

  useEffect(() => {
    if (!hostRef.current) return
    const state = EditorState.create({
      doc: content,
      extensions: [

        // old record costs that train of thought; a popover costs moving the mouse.
        factCite(async (id) => {
          const f = await factPeek(id)
          return f && { text: f.text, when: f.when, sources: f.sources }
        }),
        history(),
        // ⌘[ / ⌘] are the shell's back / forward; defaultKeymap binds them to indent, so intercept them first
        keymap.of([
          { key: 'Mod-[', run: () => { window.dispatchEvent(new CustomEvent('nav-history', { detail: -1 })); return true } },
          { key: 'Mod-]', run: () => { window.dispatchEvent(new CustomEvent('nav-history', { detail: 1 })); return true } },
          // ⌘/ is the shortcuts table; defaultKeymap binds it to toggleComment, and markdown has HTML comment markers, so it would really insert <!-- -->
          { key: 'Mod-/', run: () => { window.dispatchEvent(new CustomEvent('show-shortcuts')); return true } },
        ]),

        altHover((phrase, anchor, reason, range) => liveRef.current.onAltHover?.(phrase, anchor, reason, range)),

        listExitKeymap,
        keymap.of([...markdownKeymap, ...defaultKeymap, ...historyKeymap, ...completionKeymap, ...searchKeymap, indentWithTab]),
        // ⌘F in-page find (Trilium's FindWidget). Without it, long documents are crippled.
        search({ top: true }),

        // CM's phrases facet exists exactly for this.
        EditorState.phrases.of({
          Find: t('Find'), Replace: t('Replace'), next: t('next'), previous: t('previous'), all: t('all'),
          'match case': t('match case'), regexp: t('regexp'), 'by word': t('by word'), replace: t('Replace'), 'replace all': t('replace all'),
          close: t('Close'), 'current match': t('current match'), 'replaced $ matches': t('replaced $ matches'), 'replaced match on line $': t('replaced match on line $'),
          'on line': t('on line'), 'Go to line': t('Go to line'), go: t('go'), 'replace input': t('Replacement text'), 'search input': t('Search text'),
        }),
        autocompletion({ override: [recallSource, noteLinkSource], activateOnTyping: true }),
        markdown({ codeLanguages: languages, extensions: [GFM] }),
        syntaxHighlighting(markdownHighlight),
        dimSyntaxMarks,
        noteLinkChips(async (id) => { try { return await getNote(id) } catch { return null } }),
        mermaidPreview,
        tablePreview,
        runningBlocks((id) => liveRef.current.onStopRun?.(id), (id) => liveRef.current.onRetryRun?.(id)),
        imageEmbed,
        imagePaste,
        htmlPaste,                     // after imagePaste: images on the clipboard go the image path first
        taskCheckbox,
        linkClick,
        revisionField,
        roundDiffExt,
        slashMenu((item, from, to, preset) => liveRef.current.onSlash?.(item, from, to, preset)),
        revisionClickHandler((id) => {
          const r = liveRef.current.revisions.find((x) => x.id === id)
          if (r) liveRef.current.onAcceptInline?.(r)
        }),
        frontmatterDim,
        editorTheme,
        scrollPad ? scrollPadding : [],
        marginMemory((m, anchor, reason) => liveRef.current.onMarginClick?.(m, anchor, reason)),
        cmPlaceholder(placeholder ?? ''),
        EditorView.lineWrapping,
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            const text = update.state.doc.toString()
            lastEmitted.current = text

            // that it lost 320 characters): the echo is for "text the user typed" and "CM changed it once more";
            // bouncing it back as-is only overwrites the newly arrived chunk with the previous one during streaming.
            if (!isAppEcho(update, text)) liveRef.current.onChange?.(text)
          }
          // Number of pending changes: accept/revert, the user's own edits, and the next round's writes all change it.
          // Report upward only on change, to avoid a React render on every keystroke.
          const n = pendingHunks(update.view)
          if (n !== lastPending.current) {
            lastPending.current = n
            liveRef.current.onPendingDiff?.(n)
          }

          // CM6's StateField returns the same object when unchanged, so this costs nothing on transactions that do not touch layers.
          const st = update.state.field(roundDiffField, false)
          if (st !== lastLayers.current) {
            lastLayers.current = st
            liveRef.current.onLayersChanged?.()
          }
          if ((update.selectionSet || update.docChanged) && liveRef.current.onCursorParagraph) {
            const para = paragraphAt(update.state.doc, update.state.selection.main.head)
            if (para !== lastPara.current) { lastPara.current = para; liveRef.current.onCursorParagraph(para) }
          }
        }),
        // Read-only lives in a Compartment: lock the editor while the AI writes (edits would be overwritten by the end-of-round alignment),
        // unlock when it stops -- so it must be switchable mid-run
        readOnlyComp.current.of(readOnly ? [EditorState.readOnly.of(true), EditorView.editable.of(false)] : []),
      ],
    })
    const view = new EditorView({ state, parent: hostRef.current })
    actualViewRef.current = view

    // **The selection the context menu uses must be captured on mousedown.**
    //
    // The order is mousedown(button 2) -> contextmenu, and when right-clicking **outside the selection** the browser
    // first collapses the selection and moves the cursor there. By the time contextmenu reads state.selection
    // it is almost always empty -- which showed up as "sometimes right-click gives no menu": clicking right on the selected text
    // worked, clicking one or two characters off did not.
    let pending: string | null = null
    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 2) return
      const sel = view.state.selection.main
      pending = sel.empty ? null : view.state.sliceDoc(sel.from, sel.to)
    }
    const onContextMenu = (e: MouseEvent) => {
      // No selection at mousedown: leave it to the browser's native menu (copy/paste/spell check).
      const text = pending
      pending = null
      if (!text) return
      e.preventDefault()
      liveRef.current.onSelectionContextMenu?.(e.clientX, e.clientY, text)
    }
    view.dom.addEventListener('mousedown', onMouseDown)
    view.dom.addEventListener('contextmenu', onContextMenu)

    return () => {
      view.dom.removeEventListener('mousedown', onMouseDown)
      view.dom.removeEventListener('contextmenu', onContextMenu)
      view.destroy()
      actualViewRef.current = null
    }
    // mount once; content/revisions after this are pushed via dispatch below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])


  const freshRef = useRef(true)
  const lastGroup = useRef(undoGroup)

  // lands in the same render as `setLoading(null)` -- this frame's `readOnly` is already false, but that edit is still AI-written text,
  // and must merge into the same undo event, otherwise ⌘Z needs two presses. The readOnly effect below runs after this one to update it,
  // so what is read here is the previous frame's value.
  const aiRef = useRef(readOnly)
  useEffect(() => {
    const view = actualViewRef.current
    if (!view) return
    if (content === lastEmitted.current) return
    const current = view.state.doc.toString()
    if (content === current) { lastEmitted.current = content; return }
    // Only change the part that really changed (editor/minimalChange.ts). Replacing the whole note would drag the cursor and viewport
    // to the end, and when streaming inserts a passage in the middle the user could not see where it is written; the selection is mapped by CM.
    const change = minimalChange(current, content)
    if (change) {

      // the first chunk after read-only starts, or after `undoGroup` changes (a new Smart Continue round), starts a new event; later ones merge in.
      const ai = readOnly || aiRef.current
      const fresh = freshRef.current || undoGroup !== lastGroup.current

      // pin it character for character (undo grouping is the load-bearing wall of "one round = one ⌘Z"). This batch only **appends**
      // one annotation after it -- and does so by **spreading its own annotations and adding one**, not building a second set (a second set would give
      // two sets of annotations, and `isolateHistory` would be silently squeezed out).
      const spec: TransactionSpec = { ...(ai ? aiSyncSpec(fresh) : {}) }
      view.dispatch({
        ...spec,
        changes: change,
        // Carry **the body that was synced over**, so the echo side compares it character for character (see `editor/syncEcho.ts`)
        annotations: [...(spec.annotations ? [spec.annotations].flat() : []), syncedFromApp.of(content)],
      })
      if (ai) { freshRef.current = false; lastGroup.current = undoGroup }
    }
    lastEmitted.current = content
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content])

  useEffect(() => {
    actualViewRef.current?.dispatch({ effects: setRevisions.of(revisions) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revisions])

  useEffect(() => {
    // When the AI starts writing (readOnly becomes true), the next synced chunk starts a new undo event -- never merged into what the user just typed
    if (readOnly) freshRef.current = true
    aiRef.current = readOnly
    actualViewRef.current?.dispatch({
      effects: readOnlyComp.current.reconfigure(readOnly ? [EditorState.readOnly.of(true), EditorView.editable.of(false)] : []),
    })
    // actualViewRef is a ref, not a dependency
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly])

  useEffect(() => {
    // Must come after the content effect: diff positions are computed against the new body,
    // and dispatching before the document is swapped would mark the old positions (and roundDiffField drops the highlights
    // as soon as it sees docChanged). React runs effects in declaration order, so the order here is guaranteed by
    // declaration position.
    if (roundDiff) actualViewRef.current?.dispatch({ effects: addLayer.of({ label: roundDiff.label, parts: roundDiff.parts, replace: roundDiff.replace }) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roundDiff])

  useEffect(() => {
    actualViewRef.current?.dispatch({ effects: setMarginMarks.of(marginMarks ?? []) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marginMarks])

  return <div ref={hostRef} className="editor md-editor" />
}
