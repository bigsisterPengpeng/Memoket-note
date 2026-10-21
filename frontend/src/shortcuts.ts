/** The keyboard shortcut list -- only keys actually wired up in App.tsx / the editor. When changing a key, remember to sync this. */
export const SHORTCUT_GROUPS: { title: string; items: { keys: string; what: string }[] }[] = [
  { title: 'Notes', items: [
    { keys: '⌘N / ⌘T', what: 'New note' },
    { keys: '⇧⌘D', what: 'Today\'s journal (Journal / year / month / day)' },
    { keys: '⌘S', what: 'Save (autosave is on; this is just for peace of mind)' },
    { keys: '⌘K / ⌘J', what: 'Search notes and the knowledge base, open tabs, jump, commands' },
    { keys: '⌘[ / ⌘]', what: 'Back / Forward' },
    { keys: 'F2', what: 'Rename in the tree' },
    { keys: '⌫', what: 'Delete the selected note in the tree' },
  ] },
  { title: 'Tabs and layout', items: [
    { keys: '⌘W', what: 'Close current tab' },
    { keys: '⇧⌘T', what: 'Reopen the last closed tab' },
    { keys: '⌘1 … ⌘9', what: 'Go to tab n (⌘9 is the last one)' },
    { keys: '⌃Tab / ⌃⇧Tab', what: 'Cycle tabs' },
    { keys: '⌘\\ / ⇧⌘\\', what: 'Collapse left / right pane' },
    { keys: '⌘.', what: 'Focus mode' },
  ] },
  { title: 'Writing', items: [
    { keys: '/', what: 'At line start opens the menu: AI writing / figures / tables / voice, plus headings, lists, quotes and code blocks' },
    { keys: '@', what: 'Cite a fact from the knowledge base' },
    { keys: '[[', what: 'Link another note (⌘-click the link to jump)' },
    // "More -> How to write the body" points to this table, so it must really cover mermaid,

    { keys: '```mermaid', what: 'Draw flowcharts / pie / bar charts; renders when the cursor leaves the block' },
    { keys: '⌘F', what: 'Find / replace in note' },
    { keys: '⇧⌘F', what: 'Format the whole Markdown note' },
    { keys: '⌘B / ⌘I / ⇧⌘K', what: 'Bold / italic / insert link' },
    { keys: '⌘E / ⇧⌘X', what: 'Inline code / strikethrough (press with a selection to add; press again to remove)' },
    { keys: '⌥⌘1 / ⌥⌘2 / ⌥⌘3', what: 'Heading 1 / 2 / 3 (⌘1…⌘9 switch tabs, hence ⌥)' },
    { keys: '⇧⌘7 / ⇧⌘8 / ⇧⌘9', what: 'Numbered / bulleted / task list' },
    { keys: 'Right-click a selection', what: 'Verify / Rewrite / Polish / Expand / Trace' },
    { keys: '⌥hover / ⌥↩', what: 'Shows the term’s trace from the knowledge base next to it: first / latest / two related (no model; click “Full trace” on the card for more)' },
    { keys: '⌥click', what: 'Quick view a note from the tree (without switching)' },
    { keys: '⌘/', what: 'This table' },
  ] },
]
