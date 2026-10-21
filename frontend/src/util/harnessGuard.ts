

/** A handler's situation under that cut. */
export type GuardVerdict = 'rounds' | 'blocked' | 'self'

export type GuardEntry = {
  verdict: GuardVerdict

  why: string
}

/** The 22 handlers, one by one. **The keys must match exactly the ones really defined in `const h: api.NoteHarnessHandlers = {…}` in `App.tsx`,
 *  not one more, not one fewer** (the gate checks set equality, not "everything in the table exists"
 *  -- that is the face of **"test data narrower than the criterion"**). */
export const HARNESS_GUARD: Record<string, GuardEntry> = {
  // -- Bookkeeping by noteId => passed (bookkeeping comes before its own guard) --
  onRoundStart: { verdict: 'rounds', why: '`patchRound(noteId, d.round, …)` creates this round\'s card; the half that touches the text sits after its own guard line' },
  onDelta: { verdict: 'rounds', why: '`writeRounds(noteId, … streamed …)` is exactly the piece the P99 walkthrough lost (2 → 1)' },
  onEvaluate: { verdict: 'rounds', why: '`writeRounds(noteId, …)` records this round\'s score / weakest dimension; the `setBeatCoverage` half sits after the guard' },
  onPhase: { verdict: 'rounds', why: 'the whole handler is one `patchRound(noteId, d.round, { phase, phaseLabel })` call' },
  onPhaseDelta: { verdict: 'rounds', why: 'the whole handler is one `writeRounds(noteId, …)` call (live phase output)' },
  onToolCalls: { verdict: 'rounds', why: '`patchRound(noteId, …)` records how many searches this round made; the status-line part sits after the guard' },
  onPolicy: { verdict: 'rounds', why: 'the whole handler is one `patchRound(noteId, …)` call (policy adjustment reason)' },
  onDropped: { verdict: 'rounds', why: 'the whole handler is one `writeRounds(noteId, …)` call (revisions dropped by the defenses)' },
  onSkills: { verdict: 'rounds', why: 'the whole handler is one `patchRound(noteId, …)` call (which skills this run carried)' },
  onCheckHit: { verdict: 'rounds', why: '`writeRounds(noteId, …)` accumulates check hits; `stuckCheckRef` is this run\'s ledger and `onDone` reads it' },
  onError: { verdict: 'rounds', why: '`writeRounds(noteId, … errors …)` records this round\'s errors; toast / status line sit after the guard' },

  onSkeleton: { verdict: 'rounds', why: '`persistSkeleton(s, b, noteId)` persists by noteId (P103 A walkthrough: after switching away for 60 s the stored spine stayed 0, still 0 after finishing / reopening); the `setSpine` / `setBeats` half sits after its own guard and is still blocked' },

  // -- No bookkeeping at all => still blocked --------------------------------
  onRevision: { verdict: 'blocked', why: 'touches the text: `setContent` after `applyRevision` — letting it through writes note A\'s content into note B' },
  onInsertAt: { verdict: 'blocked', why: 'touches the text and scrolls the editor: `prepareInsert` / `EditorView.scrollIntoView`' },
  onTextEnd: { verdict: 'blocked', why: 'touches the text: `setContent` after a whole-note `fixBoldPunct`' },
  onRoundEnd: { verdict: 'blocked', why: 'touches the text (with the server-side alignment) and `pushDiff` adds a change layer to the editor' },
  onScrub: { verdict: 'blocked', why: 'touches the text: the server dropped a whole sentence, so the same sentence is deleted locally' },
  onDedup: { verdict: 'blocked', why: 'touches the text: strips the duplicated paragraph / line' },

  //    `writeRounds(noteId, … warnings …)` records which capability this round lacked (this note's record, recorded even after switching away),
  //    while the red toast still comes **after** its own guard -- **not a word pops** after switching away.

  onWarning: { verdict: 'rounds', why: '`writeRounds(noteId, … warnings …)` records which capability this round lacked (P105 C: the slot on the round card); the red toast still sits after the guard and shows nothing after switching away (several per round — noise, not a notification)' },

  // -- Handles cross-note itself: switched away it does not go silent, it says a sentence **naming the note** --
  onDone: { verdict: 'self', why: 'it detects the cross-note case itself: after switching away it only says that X\'s result was saved in that note, and leaves the text alone' },
  onCost: { verdict: 'self', why: 'it is the **reason for stopping**, while the switched-away branch of onDone only says "finished" and drops the reason; the spent tokens are the user\'s money, so it must be named even after switching away' },
  onCrossRun: { verdict: 'self', why: 'its next-step action lands in the Versions panel, which is **per note**; not naming the note sends the user to the wrong one, so either name it or do not show it' },
}

/** Must this handler **not run** after switching away. The wrapper in `App.tsx` only asks this.
 *
 *  Keys not in the table => **blocked** (the conservative side). **Not silently passed**: if a new handler is added and
 *  forgotten in the table, blocking it at worst means "that cell does not update", while passing it may mean "A's content written into B".
 *  And "forgot to classify" itself has a gate that turns red on the spot (the set-equality one). */
export function guardBlocks(k: string): boolean {
  return (HARNESS_GUARD[k]?.verdict ?? 'blocked') === 'blocked'
}

/** The handlers in a given tier (the gate and the ledger both name them one by one). */
export function guardedKeys(v: GuardVerdict): string[] {
  return Object.keys(HARNESS_GUARD).filter((k) => HARNESS_GUARD[k].verdict === v).sort()
}
