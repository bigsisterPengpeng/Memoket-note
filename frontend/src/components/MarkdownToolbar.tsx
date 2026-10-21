import type { RefObject } from 'react'
import type { EditorView } from '@codemirror/view'
import {
  boldCmd, italicCmd, inlineCodeCmd, strikeCmd, heading1Cmd, heading2Cmd, heading3Cmd, quoteCmd,
  bulletListCmd, orderedListCmd, taskListCmd, linkCmd, codeBlockCmd, mermaidCmd,
  tableCmd,
} from '../editor/markdownCommands'
import { fmtShortcut } from '../util/keys'
import Icon from './Icon'
import { t } from '../i18n'

const BUTTONS: { label: string; icon?: string; title: string; cmd: (view: EditorView) => void }[] = [
  { label: 'B', title: 'Bold (⌘/Ctrl+B)', cmd: boldCmd },
  { label: 'I', title: 'Italic (⌘/Ctrl+I)', cmd: italicCmd },
  { label: 'H1', title: 'Heading 1', cmd: heading1Cmd },
  { label: 'H2', title: 'Heading 2', cmd: heading2Cmd },
  { label: 'H3', title: 'Heading 3', cmd: heading3Cmd },
  { label: '"', title: 'Quote', cmd: quoteCmd },
  { label: '•', title: 'Bulleted list', cmd: bulletListCmd },
  { label: '1.', title: 'Numbered list', cmd: orderedListCmd },
  { label: '☑', title: 'Task list', cmd: taskListCmd },
  // This row is **monochrome glyphs** (B / I / H1 / " / • / 1. / ☑ / <> / { } / ▦).
  // It used to be a colored emoji 🔗 here, glaring in a row of grey glyphs and not following the dark theme.
  { label: 'link', icon: 'bx-link', title: 'Link (⌘/Ctrl+K)', cmd: linkCmd },
  { label: '<>', title: 'Inline code (⌘/Ctrl+E)', cmd: inlineCodeCmd },
  { label: 'S̶', title: 'Strikethrough (⌘/Ctrl+Shift+X)', cmd: strikeCmd },
  { label: '{ }', title: 'Code block', cmd: codeBlockCmd },
  { label: '▦', title: 'Table: insert an empty 3-column table', cmd: tableCmd },

  // a glyph that looked like a warning triangle. Swapped for one that really exists in the icon font (the check-icons gate watches it).
  { label: '⟁', icon: 'bx-network-chart', title: 'Flowchart: insert a mermaid diagram template', cmd: mermaidCmd },
]

/**
 * Requested directly ("add markdown shortcuts to the edit bar") -- a compact button
 * row above the editor for the markdown syntax people don't remember by
 * hand (task lists, mermaid template) as well as the ones they do but
 * don't want to type (bold/italic/link). Buttons operate on the live CM6
 * EditorView via viewRef rather than the content string, so selection state
 * and undo history stay correct (same approach as the right-click
 * SelectionMenu actions).
 */
export default function MarkdownToolbar(
  { viewRef, onFormat, onRestructure, onStopRestructure, restructuring }: {
    viewRef: RefObject<EditorView | null>
    onFormat?: () => void
    onRestructure?: () => void

    onStopRestructure?: () => void
    restructuring?: boolean
  },
) {
  return (
    <div className="row md-toolbar">
      {onFormat && (
        <button
          title={t('Format the whole note ({key}): headings, lists, table alignment, CJK/Latin spacing. Pure rules, no model; every change can be accepted or reverted.', { key: fmtShortcut('⇧⌘F') })}
          style={{ marginRight: 6 }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={onFormat}
        >
          ⌗ {t('Format')}
        </button>
      )}
      {onRestructure && (restructuring && onStopRestructure
        ? <button title={t('Cancel this layout pass; the text stays as is')} style={{ marginRight: 6 }} onMouseDown={(e) => e.preventDefault()} onClick={onStopRestructure}>
            <span className="spinner" /> {t('Stop')}
          </button>
        : <button
          title={t('Smart layout: decides which lines are headings and which are lists — semantic judgment rules cannot make. The model only decides structure; the code moves your original text, so the content cannot change.')}
          disabled={restructuring}
          style={{ marginRight: 6 }}
          onMouseDown={(e) => e.preventDefault()}
          onClick={onRestructure}
        >
          {restructuring ? <span className="spinner" /> : <><Icon n="bx-brush-alt" /> {t('Smart layout')}</>}
        </button>
      )}
      {(onFormat || onRestructure) && <span className="tb-sep" />}
      {BUTTONS.map((b) => (
        <button
          key={b.label}
          title={t(b.title)}
          // Without this, the mousedown-then-click sequence steals focus
          // from the editor first, which collapses the very selection the
          // command is supposed to wrap.
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => {
            const view = viewRef.current
            if (view) b.cmd(view)
          }}
        >
          {b.icon ? <Icon n={b.icon} /> : b.label}
        </button>
      ))}
    </div>
  )
}
