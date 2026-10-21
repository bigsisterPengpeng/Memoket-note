

export type Destination = {
  /** Virtual page id, the detail of the `open-virtual` event */
  id: string
  /** Tab title, also the readable name of the launch bar button */
  name: string
  icon: string
  /** The launch bar button's title (may be longer than the name, saying what this page is for) */
  hint: string
  /** The name shown in ⌘K. Empty means use `name` -- **⌘K is searched, so the name must contain words people will type**
   *  ("today" and "screen" should both find screen activity). */
  palette?: string
  /** Which section of the launch bar: `top` = above the divider, `foot` = below it ("special notes"
   *  like Settings / Skills), `palette` = **not on the launch bar, only in ⌘K** (Recently deleted).
   *  The reverse half does not exist: **no destination may be missing from ⌘K**, which is exactly why this list exists. */
  where: 'top' | 'foot' | 'palette'
}

export const DESTINATIONS: Destination[] = [
  { id: 'kb', name: 'Knowledge base', icon: 'bx-data', where: 'top',
    hint: 'Knowledge base: search facts, view the topic map and periodic digests' },
  { id: 'app:import', name: 'Import', icon: 'bx-import', where: 'top',
    hint: 'Import: .md files / Obsidian / Evernote / Notion / Apple Notes / batch files' },
  { id: 'app:journey', name: 'Screen activity', icon: 'bx-desktop', where: 'top',
    hint: 'Screen activity: what you did today', palette: 'Today\'s screen activity' },
  { id: 'app:skills', name: 'Writing Skills', icon: 'bx-extension', hint: 'Writing Skills', where: 'foot' },
  { id: 'app:settings', name: 'Settings', icon: 'bx-cog', hint: 'Settings: LLM provider', where: 'foot' },
  { id: 'app:trash', name: 'Trash', icon: 'bx-trash', where: 'palette',
    hint: 'Trash (recoverable for 30 days)', palette: 'Trash (recoverable for 30 days)' },
]

/** The name of that item in ⌘K. */
export const paletteLabel = (d: Destination): string => d.palette ?? d.name
