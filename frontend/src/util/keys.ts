/** How shortcuts are written for people: mac uses the ⌘⌥⇧⌃ symbols, Windows / Linux use Ctrl+ / Alt+ / Shift+.
 *  Key tables and menus are always written with mac symbols and translated per platform for display. */
export const isMac = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform)


function winChord(mods: string): string {
  const out: string[] = []
  if (/[⌘⌃]/.test(mods)) out.push('Ctrl')
  if (mods.includes('⌥')) out.push('Alt')
  if (mods.includes('⇧')) out.push('Shift')
  return out.length ? out.join('+') + '+' : ''
}

export function fmtShortcut(s: string, mac: boolean = isMac): string {
  if (mac) return s
  return s
    .replace(/[⌘⌥⇧⌃]+/g, winChord)
    .replace(/⌫/g, 'Del')
    .replace(/↩/g, 'Enter')
}
