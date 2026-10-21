

export type TabFacts = {
  id: string
  title: string
  /** Does the source say `alwaysShown: true`. */
  alwaysShown: boolean
  /** Does this cell set the `hasContent:` field (**not its value** -- that is only known at runtime). */
  setsHasContent: boolean
  /** Does this cell have `emptyHint:`. */
  setsEmptyHint: boolean
  /** Does this cell have `badge:`. */
  setsBadge: boolean
  /** The **hard-coded sentence** in the falsy branch of `body:`'s ternary; `null` if there is no such path.
   *
   *  Only the shape "`: <lowercase tag …>plain text</lowercase tag>`" is recognized -- a lowercase tag = a real DOM element,
   *  plain text = no `{}` / nested tags in between. `: null` / `: <Foo/>` all return `null`:
   *  **the former really draws nothing; what the latter draws is only known by mounting that component** (that is the gate side's business). */
  bodyFallbackText: string | null
}


export const stripComments = (s: string): string => s
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/^[ \t]*\/\/.*$/gm, ' ')
  .replace(/([^:])\/\/.*$/gm, '$1')

/** The raw text of the whole `<RightPane … tabs={[ … ] as PaneTab[]}>` block in `App.tsx`.
 *  **Throws** if not found -- silently returning an empty string would leave the table below empty, and "not a single cell"
 *  looks exactly like "the parser is blind" on the gate side (**"cannot select != does not exist"**). */
export function rightPaneTabsBlock(appSrc: string): string {
  const at = appSrc.indexOf('<RightPane')
  if (at < 0) throw new Error('`<RightPane` not found in App.tsx — was the right pane moved? Read App.tsx first instead of changing this parser')
  const from = appSrc.indexOf('tabs={[', at)
  if (from < 0) throw new Error('`<RightPane` found, but no `tabs={[` after it — the tabs array is written differently now')
  const to = appSrc.indexOf('] as PaneTab[]}', from)
  if (to < 0 || to <= from) throw new Error('`tabs={[` found, but no closing `] as PaneTab[]}`')
  return appSrc.slice(from, to)
}

/** The whole block -> one fact per cell. **In source order**. */
export function parseRightPaneTabs(appSrc: string): TabFacts[] {
  const block = stripComments(rightPaneTabsBlock(appSrc))
  const heads = [...block.matchAll(/\{\s*id:\s*'([a-zA-Z][\w-]*)',\s*title:\s*(?:t\(\s*)?'([^']+)'/g)]
  if (heads.length === 0) throw new Error('No tab could be parsed from the tabs array — the `{ id: \'x\', title: \'y\'` shape has changed')
  return heads.map((h, i) => {
    const seg = block.slice(h.index!, i + 1 < heads.length ? heads[i + 1].index! : block.length)
    const bodyAt = seg.indexOf('body:')
    const body = bodyAt < 0 ? '' : seg.slice(bodyAt)
    const fall = /:\s*<([a-z][a-z0-9]*)\b[^>]*>(?:\{t\('([^']+)'\)\}|([^<>{}]+))<\/\1>/.exec(body)
    const text = (fall?.[2] ?? fall?.[3] ?? '').trim()
    return {
      id: h[1],
      title: h[2],
      alwaysShown: /\balwaysShown:\s*true\b/.test(seg),
      setsHasContent: /\bhasContent:/.test(seg),
      setsEmptyHint: /\bemptyHint:/.test(seg),
      setsBadge: /\bbadge:/.test(seg),
      bodyFallbackText: text ? text : null,
    }
  })
}
