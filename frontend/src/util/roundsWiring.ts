


export const stripComments = (s: string): string => s
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/^[ \t]*\/\/.*$/gm, ' ')
  .replace(/([^:])\/\/.*$/gm, '$1')

export type RoundsWiring = {
  /** The name of the round cards on screen (`const <this name> = roundsFor(…)`). `null` if it cannot be parsed. */
  readName: string | null
  /** The second argument of `roundsFor(` verbatim ("by which note"). `null` if it cannot be parsed. */
  keyExpr: string | null
  /** Does the source still have **one-for-the-whole-App** round cards like `const [x, setX] = useState`. */
  globalState: string | null
  /** Every write: function name + first argument verbatim. */
  writes: { fn: string; firstArg: string }[]
  /** Every `planTabContent({ … rounds: <here> … })` verbatim. */
  planRounds: string[]
  /** `<AgentActivity … rounds={<here>}>` verbatim; `null` if it cannot be parsed. */
  activityRounds: string | null

  rawSetters: number
}

/** `App.tsx` -> the table above.
 *
 *  **Throws if not a single item can be parsed** (rather than returning an empty table): an empty table and "the parser is blind" look
 *  exactly the same on the gate side -- **"cannot select != does not exist"**. */
export function readRoundsWiring(appSrc: string): RoundsWiring {
  // **First strip the declarations of those two functions themselves**: `function patchRound(noteId: string, …)`
  // looks exactly like a call, and unstripped it would count as a write "whose first argument is `noteId: string`"
  // (the first version measured exactly that -- **the face of a criterion wider than the product**).
  const s = stripComments(appSrc)
    .replace(/\bfunction\s+(writeRounds|patchRound)\s*\([^)]*\)/g, ' ')

  const read = /const\s+([A-Za-z_$][\w$]*)\s*=\s*roundsFor\(([^)]*)\)/.exec(s)
  const global = /const\s*\[\s*([A-Za-z_$][\w$]*)\s*,\s*set[A-Za-z_$][\w$]*\s*\]\s*=\s*useState<\s*AgentRound\[\]/.exec(s)
  const writes = [...s.matchAll(/\b(writeRounds|patchRound)\(\s*([^,]+?)\s*,/g)]
    .map((m) => ({ fn: m[1], firstArg: m[2].trim() }))
  const planRounds = [...s.matchAll(/planTabContent\(\{[\s\S]{0,400}?\brounds:\s*([^,}]+)/g)]
    .map((m) => m[1].trim())
  const activity = /<AgentActivity[\s\S]{0,400}?\brounds=\{([^}]+)\}/.exec(s)
  const rawSetters = (s.match(/\bsetRoundsByNote\(/g) ?? []).length

  if (!read && !global) {
    throw new Error('Neither `const … = roundsFor(…)` nor `useState<AgentRound[]>` could be parsed from `App.tsx`'
      + ' — the round cards are written differently now. Read App.tsx first instead of changing this parser')
  }
  if (planRounds.length === 0) {
    throw new Error('`planTabContent({ … rounds: … })` could not be parsed from `App.tsx` — the Plan tab is written differently now')
  }
  return {
    readName: read?.[1] ?? null,
    keyExpr: read ? read[2].split(',').slice(1).join(',').trim() || null : null,
    globalState: global?.[1] ?? null,
    writes,
    planRounds,
    activityRounds: activity?.[1]?.trim() ?? null,
    rawSetters,
  }
}


export const isNoteIdVar = (arg: string): boolean =>
  /^[A-Za-z_$][\w$]*$/.test(arg) && !/^(current|note|notes)$/.test(arg)

/** Answers to the five questions. **Every item returned names the original text of that line**; empty array = all five pass. */
export function wiringComplaints(w: RoundsWiring): string[] {
  const bad: string[] = []
  if (w.globalState) {
    bad.push(`The round cards are a single App-wide list again: \`const [${w.globalState}, set…] = useState<AgentRound[]>\``
      + ' — it does not follow the note switch, so the right pane shows the previous note\'s run (P93 walkthrough "Plan 2")')
  }
  if (!w.readName) {
    bad.push('`const … = roundsFor(…)` not found: the round cards on screen are not read by note id')
  }
  if (!w.keyExpr || !/\bcurrent\b/.test(w.keyExpr)) {
    bad.push(`The second argument of \`roundsFor(…)\` is \`${w.keyExpr ?? '(unparsed)'}\`, which does not mention \`current\``
      + ' — "which note to read" must follow the note that is open now')
  }
  if (w.writes.length === 0) {
    bad.push('Not a single `writeRounds(` / `patchRound(` could be parsed — the write half is written differently now')
  }
  for (const x of w.writes) {
    if (!isNoteIdVar(x.firstArg)) {
      bad.push(`The first argument of \`${x.fn}(${x.firstArg}, …)\` is not the id of the note that started this run`
        + ' — writes must name their note, not "whatever note is shown now"')
    }
  }
  for (const r of w.planRounds) {
    if (w.readName && r !== `${w.readName}.length`) {
      bad.push(`\`planTabContent({ … rounds: ${r} … })\` does not use \`${w.readName}.length\``
        + ' — the badge and the body measure different things again (the shape of the P91 A regression)')
    }
  }
  if (w.rawSetters !== 1) {
    bad.push(`The table is written directly in ${w.rawSetters} places (\`setRoundsByNote(\`); there must be exactly 1`
      + ' — every extra one bypasses "writes must name their note", and one is enough to reopen the hole')
  }
  if (w.readName && w.activityRounds !== w.readName) {
    bad.push(`\`<AgentActivity rounds={${w.activityRounds ?? '(unparsed)'}}>\` does not show \`${w.readName}\``
      + ' — the card stack at the bottom of the right pane bypasses the "read by note id" step')
  }
  return bad
}
