import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, lazy, Suspense } from 'react'
import { clickable } from './util/clickable'
import { DESTINATIONS } from './util/destinations'
import { journalDateOf } from './util/journalDate'
import JourneyRibbonPanel from './components/JourneyRibbonPanel'
import { openSearchPanel } from '@codemirror/search'
import { micError } from './util/micError'
import ChangeLayersPanel from './components/ChangeLayersPanel'
import TrashPanel from './components/TrashPanel'
import { chunked, dotWorthy, MARGIN_BATCH, MARGIN_CACHE_MAX, marginParagraphs, markKey, splitCached, type MarginMark, type MarginVerdict } from './editor/marginMemory'
import { ignoredSet } from './util/relationActions'
import { matchSnippet } from './util/snippet'
import { readingMinutes, stripForRecall, wordCount, citationRanges, noteLinkRanges, citedFactIds, linkedNoteIds } from './util/wordCount'
import { isSpeakerTag } from './util/kbNoise'
import { friendlyError, isBackendDown, isLlmUnreachable } from './util/friendlyError'
import { NOT_CONFIGURED, healthMessage, llmGateMessage, notePrecondition } from './editor/preconditions'
import { EditorView } from '@codemirror/view'
import * as api from './api'
import type { Note, Revision, TapMeta, TreeRow, VerifyResult, WritingPlan, WritingSection } from './api'
import AudioRecorder from './components/AudioRecorder'
import CommandPalette from './components/CommandPalette'
import DocumentOutline from './components/DocumentOutline'
import MarkdownEditor from './components/MarkdownEditor'
import SplitEditor from './components/SplitEditor'
import { insertStreamed, tidyBlankLines, applyScrub, prepareInsert } from './editor/streamJoin'
// One round can hit several criteria in turn; accumulate them instead of overwriting (batch 24 / plan 12.1)
import { withCheckHit } from './editor/agentRound'
import { isStaleShrink, type Served } from './editor/saveGuard'
import IconPicker from './components/IconPicker'
import SlashPrompt from './components/SlashPrompt'
import { formatMarkdown, fixBoldPunct, stripCommonIndent } from './editor/format'
import { blockPrecondition, SLASH_ITEMS, type SlashItem } from './editor/slashMenu'
import { missingTemplateScaffold, templateTextAt, writingTemplate, type WritingTemplateId } from './editor/writingTemplates'
import { blockShapeProblem, splitBadRevisions, badRevisionNote, unparsedEditNote } from './editor/blockShape'
import type { NoteLinkMenuDetail } from './editor/noteLink'
import { landNotesInTray, noteExcerpt, requestTrayAdd, trayPrecondition } from './util/tray'
import { diffBaseForBlock, textToLand } from './editor/blockLanding'
import { trayByDefault } from './util/trayDefaults'
import {
  appendPreview, endRun, logRun, patchRun, runsField, startRun,
} from './editor/runningBlocks'
import type { StateEffect } from '@codemirror/state'
import MarkdownToolbar from './components/MarkdownToolbar'
import WritingPlanPanel from './components/WritingPlanPanel'
import MemoryPanel from './components/MemoryPanel'
import RelatedMemory from './components/RelatedMemory'
import TrayPanel from './components/TrayPanel'
import RevisionPanel, { applyRevision } from './components/RevisionPanel'
import SelectionMenu from './components/SelectionMenu'
import type { SelectionAction } from './components/SelectionMenu'
import AgentActivity, { type AgentRound, warningLine } from './components/AgentActivity'
import { acceptAllHunks, diffParts, dropHunk, layersOf, pendingHunks, restoreLayers as restoreLayersEffect, roundDiffField, settledOf, type DiffPush }
  from './editor/roundDiff'
import ContextMenu, { type MenuAt, type MenuItem } from './components/ContextMenu'
import Gutter from './components/Gutter'
import Logo from './components/Logo'
import PreferencesPanel from './components/PreferencesPanel'
import LanguageRow from './components/LanguageRow'
import { t } from './i18n'

const KbNoteView = lazy(() => import('./components/KbNoteView'))
const SlidesPanel = lazy(() => import('./components/SlidesPanel'))
const JourneyPage = lazy(() => import('./components/JourneyPage'))
import { displayTitle, isPlaceholderTitle } from './util/displayTitle'
import ExportNotePanel from './components/ExportNotePanel'
import { setPendingKbQuery } from './util/pendingKbQuery'
import { VIRTUAL_LABELS, isKnownVirtual, factsLabel, previewLine, isKbVirtual, syncVirtualTab } from './util/virtual'
import { buildCrumbs } from './util/crumbs'
import { layoutPanes, makeRoomForRight } from './util/layoutPanes'
import { readDraft, writeDraft, clearDraft, resolveDraft } from './util/draft'
import { loadSpots, putSpot, saveSpots } from './util/spots'
import { sectionEnd } from './util/sectionEnd'
import { minimalChange } from './editor/minimalChange'
import { undoRound } from './editor/undoRound'
import { groupRuns, type RunRound } from './util/runRounds'
import { changesTabHasContent, reopenedLayersNotice, restoreLayers, sameLayers, serializeLayers, type SavedLayer } from './util/changeLayers'
import { PLAN_EMPTY_HINT, planTabContent } from './util/planTab'

import { roundsFor, writeRoundsIn, type RoundsByNote } from './util/roundsByNote'
import { guardBlocks } from './util/harnessGuard'
import { mergeRestored, restoredRounds, restoredStopStatus } from './util/roundsRestore'
import { checkLabel, stuckTail } from './editor/dimLabel'
import { dimLabel } from './editor/dimLabel'
import { setIngestActive } from './util/ingestActive'
import { ConfirmDialog, NotePicker, TextPrompt, type ConfirmRequest, type PickerRequest, type PromptRequest } from './components/Dialogs'
import { NoteInfoPanel, NotePathsPanel } from './components/NoteInfoPanels'
import NoteLinksPanel from './components/NoteLinksPanel'
import RevisionHistoryPanel from './components/RevisionHistoryPanel'
import QuickView from './components/QuickView'
import WelcomePane from './components/WelcomePane'
import { downloadMarkdown } from './util/markdownExport'
import ShortcutsPanel from './components/ShortcutsPanel'
import type { DropWhere } from './components/NoteTree'
import NoteKbPanel from './components/NoteKbPanel'
import NoteTree from './components/NoteTree'
import TabBar, { type Tab } from './components/TabBar'
import Ribbon, { type RibbonTab } from './components/Ribbon'
import RightPane, { type PaneTab } from './components/RightPane'
import SkeletonPanel from './components/SkeletonPanel'
import WritingWorkflowPicker from './components/WritingWorkflowPicker'
import PlanChecks from './components/PlanChecks'
import MarginCard from './components/MarginCard'
import TraceCard, { type TraceCardState } from './components/TraceCard'
import TraceAnswer from './components/TraceAnswer'
import { intentText, needsHarnessGoal, resolveIntent, WORKFLOW_LABEL, type DocIntent } from './util/docIntent'
import SettingsPanel, { AboutLine } from './components/SettingsPanel'
import SkillsPanel from './components/SkillsPanel'
import TapProvenance from './components/TapProvenance'
import Toaster from './components/Toaster'
import UserSwitcher from './components/UserSwitcher'
import VerifyPanel, { passageLine, verifyScopeLine } from './components/VerifyPanel'
import { toast, toastAction } from './toast'
import { dupSuffixes } from './util/dupTitles'
import { traceRecallHint } from './util/recallContext'
import { mermaidSvg } from './editor/mermaid'
import { parseMini } from './util/miniMarkdown'
import { slidesToHtml } from './util/slideHtml'
import { isSlides, slidePages } from './util/slidePages'
import { fmtDate, whenLabel } from './util/time'
import { notifyIfHidden } from './util/notify'
import { fmtShortcut } from './util/keys'
import Icon from './components/Icon'

// Throttling for background auto-generation. Outline/edits are real LLM calls (~8-15s on a local model),
// so they can't fire on every keystroke — two gates, "stopped typing for N seconds + enough content changed",
// keep it from being purely manual without hammering the model while the user types.
const SKELETON_IDLE_MS = 8000
const SKELETON_MIN_CHARS = 30
const SKELETON_MIN_DELTA = 20


const CHANGE_LAYER_SAVE_MS = 1600

/** Run state of the infinite-continue harness — lives at App level rather than inside WritingPlanPanel,
 * a direct answer to "do I really need the writing-plan page open? can't it run in the background?": the state
 * lifecycle used to follow the dialog component's mount/unmount, so closing the dialog (or never opening it) meant
 * stopping. Lifted to App level, the run itself no longer depends on whether the dialog is open — the panel is just
 * a view that "watches and controls this state", not its owner. Exported to WritingPlanPanel as a prop type
 * (type-only import, erased at compile time, so not a real runtime circular
 * dependency). */
export type HarnessState = {
  folderId: string
  folderName: string
  plan: WritingPlan
  sections: WritingSection[]
  running: boolean
  currentSectionTitle: string
  currentNoteId: string
  preview: string
  waitingFirstToken: boolean
  follow: boolean
}




/** Tab name in menus: hard cut + ellipsis (not clipTitle — that cuts at sentence punctuation, so "Product plan meeting: APP/hardware…" keeps only the first half) */
const ellipsize = (t: string, max: number) => (t.length > max ? t.slice(0, max - 1) + '…' : t)


const BUSY_LABEL: Record<string, string> = {   // data table: displayed via t(BUSY_LABEL[loading]), each row marked i18n-ignore
  ingest: 'Saving to knowledge base…',
  slides: 'Making slides…',
  restructure: 'Smart layout…',
  skeleton: 'Generating outline…',

  rounds: 'Applying that round’s snapshot…',
}

export default function App() {
  const [notes, setNotes] = useState<Note[]>([])
  // Fetch the whole tree at once (see the api.getTree comment: per-level fetching turns every expand into a network round trip).
  const [tree, setTree] = useState<TreeRow[]>([])
  // The **virtual** knowledge-base subtree (docs/kb-fusion-design.md §3.2). Category levels are fetched in full,
  // facts expand on demand; expansion state isn't on the server (virtual nodes have no branch), so it's stored locally.
  const [kbRows, setKbRows] = useState<TreeRow[]>([])
  // The virtual node the middle pane is showing (a fact / a category). Mutually exclusive with current: current set
  // means writing a note, virtualId set means browsing the knowledge base.
  const [virtualId, setVirtualId] = useState<string | null>(null)
  useLayoutEffect(() => {
    if (virtualId) document.querySelector('.note-scroll')?.scrollTo({ top: 0 })
  }, [virtualId])
  // In-app dialogs (replacing window.prompt — in Electron that is a system-level modal the theme can't reach)
  const [picker, setPicker] = useState<PickerRequest | null>(null)
  /** The "export this note back" popover. Whole-library export lives on the import page; this only changes the scope —
   *  **it shares the same component**, no separate export UI (otherwise it's again "two doors for one action, each drifting"). */
  const [exportOne, setExportOne] = useState<Note | null>(null)
  /** How the sidebar is ordered: `tree` is the user's own hierarchy, `recent` is a flat list by last modified.
   *
   * The tree has only one ordering (manual `position`), so notes **had no notion of "recent"**
   * — the knowledge base has "recently ingested", the journal goes by date, only notes had nothing (docs/sidebar-ia-plan.md §3).
   * "Where is the one I wrote yesterday" can't be answered in a 300-note library.
   * Times show only in this mode, because they're its point; tree mode doesn't show them. */
  const [recentMode, setRecentMode] = useState(() => {
    try { return localStorage.getItem('memoket-note-list-mode:' + api.getUser()) === 'recent' } catch { return false }
  })
  useEffect(() => {
    try { localStorage.setItem('memoket-note-list-mode:' + api.getUser(), recentMode ? 'recent' : 'tree') } catch { /* if it can't be stored, fall back to tree next time; not fatal */ }
  }, [recentMode])
  const [prompt, setPrompt] = useState<PromptRequest | null>(null)
  const [confirmReq, setConfirmReq] = useState<ConfirmRequest | null>(null)
  const [iconPicker, setIconPicker] = useState(false)
  const iconBtnRef = useRef<HTMLButtonElement>(null)   // focus returns to this button after the picker closes (keyboard users don't drop onto body)
  const [locateTick, setLocateTick] = useState(0)
  const [paneFocus, setPaneFocus] = useState<{ id: string; n: number } | undefined>(undefined)
  /** The "page N" while making slides. Only this needs progress finer than BUSY_LABEL. */
  const [slidePhase, setSlidePhase] = useState('')
  const slidesText = useRef('')
  const [fbMenu, setFbMenu] = useState<{ kind: 'harness' | 'more'; at: MenuAt } | null>(null)
  // Hidden file input for the tree menu's "Import here…"; remembers which node to attach under
  const importInput = useRef<HTMLInputElement>(null)
  const importUnder = useRef<string>(api.ROOT_ID)
  // Notes created this session that are still empty. Quietly delete them when leaving: otherwise every + adds another

  const freshEmpty = useRef(new Set<string>())
  async function dropIfStillEmpty(n: Note | null) {
    if (!n || !freshEmpty.current.has(n.id)) return
    // A title / body written, or an icon picked (picking an icon also says "I want this one"), means it's not an untouched empty note
    if (title.trim() || content.trim() || n.icon) { freshEmpty.current.delete(n.id); return }
    freshEmpty.current.delete(n.id)
    try {
      await api.deleteNote(n.id)
      setTabs((prev) => prev.filter((t) => t.noteId !== n.id))
      void Promise.all([reload(), reloadTree()])
    } catch { /* if it can't be deleted, keep it; not worth an error */ }
  }
  // Split view: open another note in a column to the right of the middle pane (Trilium's SplitNoteContainer).

  // proposal layers live only on the main editor; the note open in the main pane is read-only in the split.
  const splitFlush = useRef<(() => Promise<void>) | null>(null)
  const [split, setSplit] = useState<{ id: string; w: number } | null>(() => {
    try {
      const raw = localStorage.getItem('memoket-note-split:' + api.getUser())
      return raw ? (JSON.parse(raw) as { id: string; w: number }) : null
    } catch { return null }
  })
  useEffect(() => {
    try {
      if (split) localStorage.setItem('memoket-note-split:' + api.getUser(), JSON.stringify(split))
      else localStorage.removeItem('memoket-note-split:' + api.getUser())
    } catch { /* doesn't matter */ }
  }, [split])
  const openInSplit = (id: string) => setSplit((s) => ({ id, w: s?.w ?? 420 }))
  const [tabMenu, setTabMenu] = useState<{ tab: Tab; at: MenuAt } | null>(null)
  const [tabListAt, setTabListAt] = useState<MenuAt | null>(null)
  const tabsRef = useRef<Tab[]>([])
  const closeTabRef = useRef<(id: string) => void>(() => {})
  const tabActionRef = useRef<(action: string) => void>(() => {})
  const [quick, setQuick] = useState<Note | null>(null)
  // Save-status badge (Trilium's save-status-badge): announce a save, fade after 5s;
  // errors turn red and don't fade. In an autosaving product a "Save" button would only imply "not saved unless clicked".
  const [saveStatus, setSaveStatus] = useState<{ at: number; error?: string } | null>(null)
  // Keep a stack of closed tabs so ⌘⇧T brings them back (reopenLastTab). Closing the wrong tab shouldn't be irreversible.
  // Remember the original position too: a reopened tab goes back where it was (like Chrome's ⌘⇧T), not appended at the right —
  // otherwise closing and reopening a middle tab scrambles the order.
  const closedTabs = useRef<{ tab: Tab; at: number }[]>([])
  // Back/forward: after jumping to an old note you need one click to return (pain point 12 of criterion 2).
  // Records note ids / virtual node ids; while navigating is true, open doesn't push onto the stack.
  const hist = useRef<{ list: string[]; idx: number; navigating: boolean }>({ list: [], idx: -1, navigating: false })
  const [histState, setHistState] = useState({ back: false, fwd: false })
  const [treeMenu, setTreeMenu] = useState<{ row: TreeRow; at: MenuAt } | null>(null)
  /** Open tabs. **Persisted in localStorage, per user** — closing and reopening the app should leave the desk
   *  as it was, a basic desktop-app expectation; without it every launch means hunting down the notes you were
   *  writing, and "hunting down" is exactly the attention criterion 2 is meant to save. */
  const [tabs, setTabs] = useState<Tab[]>(() => {
    try {
      const raw = localStorage.getItem('memoket-note-tabs:' + api.getUser())
      const loaded = raw ? (JSON.parse(raw) as Tab[]) : []
      const kb = loaded.find((t) => isKbVirtual(t.noteId))
      return kb ? syncVirtualTab(loaded, kb, null) : loaded
    } catch { return [] }
  })
  const [activeTabId, setActiveTabId] = useState<string | null>(null)
  // Expansion state no longer lives here — it's stored on the server with the branch (see toggleTreeNode).
  const [noteQuery, setNoteQuery] = useState('')
  // null = not searching (show `notes` unfiltered); kept separate from
  // `notes`/`reload()` so typing a search term can never accidentally
  // trigger the mount effect's "open the first result" behavior.
  const [searchResults, setSearchResults] = useState<Note[] | null>(null)
  const [current, setCurrent] = useState<Note | null>(null)

  const [trayTarget, setTrayTarget] = useState('')
  const trayTargetRef = useRef('')
  useEffect(() => { if (current?.id) { setTrayTarget(current.id); trayTargetRef.current = current.id } }, [current?.id])
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')

  const [spine, setSpine] = useState('')
  const [beats, setBeats] = useState<string[]>([])
  /** Deterministic check of the outline (backend `harness/checks/skeleton.py`, plan 4.3).
   * Cleared on note switch — it's the verdict of "this generation", not a property of the note, and wasn't
   * persisted along with spine/beats. */
  const [skeletonNotes, setSkeletonNotes] = useState<string[]>([])

  // [10]) — null means "not run yet / unknown", in which case the outline panel just shows what the beats are;
  // once it has a value the outline panel marks the covered beats, instead of a static checklist
  // that shows no progress.
  const [beatCoverage, setBeatCoverage] = useState<{ level: number; note: string } | null>(null)
  const [revisions, setRevisions] = useState<Revision[]>([])
  const [loading, setLoading] = useState<'' | 'skeleton' | 'restructure' | 'edit' | 'tap' | 'ingest' | 'note-harness' | 'slides' | 'rounds'>('')

  const [noteHarnessNoteId, setNoteHarnessNoteId] = useState<string | null>(null)
  // Where you were in each note: remember cursor and scroll on leaving, restore on return (pain point 12: after checking an old note
  // you can't remember which paragraph you were writing). Kept across restarts, see util/spots.
  const spots = useRef(loadSpots(api.getUser()))

  const [roundsByNote, setRoundsByNote] = useState<RoundsByNote>({})
  /** The wrap-up sentence must count the rounds of **the note that ran**, not **the note now shown** —
   *  if the user switched away the latter is empty. Writing the ref is idempotent (same reason as `liveContentRef`). */
  const roundsByNoteRef = useRef<RoundsByNote>({})
  /** Round cards of the note currently shown. Virtual page / no note open ⇒ empty. */
  const agentRounds = roundsFor(roundsByNote, current?.id)
  /** Write onto **a specific note's** round cards. **The note id is required** — "write to the current note" was exactly the hole. */
  const writeRounds = useCallback((noteId: string, fn: (rs: AgentRound[]) => AgentRound[]) => {
    setRoundsByNote((m) => {
      const next = writeRoundsIn(m, noteId, fn)
      roundsByNoteRef.current = next
      return next
    })
  }, [])
  /** What this harness round changed (added/removed), passed to the editor for read-only highlighting.
   * Otherwise the user can't see at all where auto-applied changes touched. */
  const [roundDiff, setRoundDiff] = useState<DiffPush | null>(null)
  const diffSeq = useRef(0)
  /** Mark the changes of one AI action as a proposal layer (agent-native-editor §3.2: accept / revert per layer). */
  function pushDiff(label: string, before: string, after: string, replace = false) {
    if (before === after) return
    setRoundDiff({ label, parts: diffParts(before, after), seq: ++diffSeq.current, replace })
  }
  // How many harness changes remain undisposed. Reported by the editor — per-change accept/revert, the user's own
  // edits and the next round's writes all change it; React only uses it to decide whether to show that toolbar.
  const [pendingDiff, setPendingDiff] = useState(0)

  const layersSaved = useRef<{ noteId: string; payload: SavedLayer[] }>({ noteId: '', payload: [] })
  // An in-flight old PUT must not, after a newer PUT, write the "already saved" fingerprint back to the old version.
  const layersSaveSeq = useRef(0)
  const layersTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Which note the layers have been restored into. **This slot is empty between a note switch and the restore** —
   *  any debounced persist in that window would write the previous note's layers under the new note. */
  const layersReady = useRef('')
  const lastSettled = useRef<unknown>(undefined)
  /** Re-render the panel when the disposition ledger changes (the "Disposed 2 accepted · 1 reverted" line) */
  const [layersTick, setLayersTick] = useState(0)
  /** Long-term ledger of per-change accept / revert: survives after change layers are burned; the next Harness reads it too. */
  const [writingFeedback, setWritingFeedback] = useState<api.WritingFeedback | null>(null)

  const [layerStuck, setLayerStuck] = useState<{ id: string; label: string; why: string[]; saved: SavedLayer }[]>([])
  const layerStuckRef = useRef<typeof layerStuck>([])
  useEffect(() => { layerStuckRef.current = layerStuck }, [layerStuck])


  // so one ⌘Z undoes one round (mechanism in `editor/undoUnit.aiSyncSpec` / `MarkdownEditor`'s content sync)
  const [undoGroup, setUndoGroup] = useState(0)
  // The item selected in the `/` menu. needsPrompt items show an input box first; the rest run directly.
  // Run state is **not here**: once running, state lives in the placeholder block at the cursor
  // (editor/runningBlocks.ts) — closest to the output, and several can run at once.
  // Only "which item is selected, and whether to show the prompt input" stays here.
  const [slash, setSlash] = useState<
    { item: SlashItem; from: number; to: number; x: number; y: number; resumeHarness?: boolean } | null>(null)
  /** Writing scenarios are separate from `/` edit commands: chosen in the editor, and can go on to start the Harness when the goal is unclear. */
  const [workflowPicker, setWorkflowPicker] = useState<{ resume: boolean; focus?: 'goal' | 'done' } | null>(null)
  const workflowButtonRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { setWorkflowPicker(null) }, [current?.id])

  const [noteLinkMenu, setNoteLinkMenu] = useState<NoteLinkMenuDetail | null>(null)
  useEffect(() => {
    const on = (e: Event) => setNoteLinkMenu((e as CustomEvent<NoteLinkMenuDetail>).detail)
    window.addEventListener('note-link-menu', on)
    return () => window.removeEventListener('note-link-menu', on)
  }, [])
  // **One AbortController per run**, indexed by id. It used to be a single ref,
  // so only one `/` could run at a time — the second one bumped the first's controller as soon as it started.
  const runAborts = useRef(new Map<string, AbortController>())

  const retryArgs = useRef(new Map<string, { item: SlashItem; prompt: string }>())
  const filePick = useRef<HTMLInputElement>(null)
  const pickKind = useRef<'image' | 'audio'>('image')
  // Recording stop functions stored by id: stopping goes through MediaRecorder.stop() (only after stopping is there audio
  // to transcribe), which is a different thing from aborting a network request.
  const voiceStopById = useRef(new Map<string, () => void>())
  // Body snapshot taken **when the whole run starts**. Deliberately not per round: per-round marks would let round N+1's
  // first revision clear round N's highlight (roundDiffField drops old decorations as soon as it sees docChanged),
  // and the last round's would be cleared by the final reload(), so the user would only ever glimpse the first.

  const runBaseRef = useRef<string>('')
  // Synchronous mirror of the body. **Don't call setRoundDiff inside setContent's updater** —
  // updaters must be pure; triggering another setState inside is invalid, and React 19
  // StrictMode double-invokes updaters — in practice it crashed the whole Agent panel.
  // So the updater only writes this ref on the side (writing a ref is idempotent, double calls are harmless),
  // and the end of each round reads the current body straight from the ref.
  //

  const liveContentRef = useMemo(() => {
    let v = ''
    return {
      get current() { return v },
      set current(next: string) {
        v = next

        // changed the default rather than 92 call sites — miss one and that site silently reads wrong). Missing one here
        // is worse: the guard would hold a stale anchor and block a save that **should** happen.
        servedRef.current = { id: servedRef.current.id, text: next, edits: 0 }
      },
    }
  }, [])

  const servedRef = useRef<Served>({ id: '', text: '', edits: 0 })
  /** Edits reported by the editor (**echoes don't count**; `editor/syncEcho.ts` already filters them out):
   *  user typing, the hover toolbar's "Accept / Revert", `/` blocks, paste — all go through this one path. */
  const onEditorChange = useCallback((next: string) => {
    servedRef.current.edits++
    setContent(next)
  }, [])
  // Insertion cursor for targeted continue: null = append to the end; reset at the start of each round
  const insertCursorRef = useRef<number | null>(null)


  const actionsRef = useRef({ runNoteHarness: (_m: 'write' | 'polish') => Promise.resolve(), runMagicTap: () => Promise.resolve(), handleSelectionAction: (_a: SelectionAction) => Promise.resolve(), runHarness: (_r: TreeRow) => Promise.resolve(), ingestCurrentNote: () => Promise.resolve(), runBlock: (_i: SlashItem, _f: number, _t: number, _p: string) => Promise.resolve(), dropIfStillEmpty: (_n: Note | null) => Promise.resolve(), collapseAll: () => Promise.resolve(), pushDiff: (_l: string, _b: string, _a: string, _r?: boolean) => {}, runSlides: (_s: 'points' | 'talk') => Promise.resolve(), onPickFile: (_f: FileList | null) => Promise.resolve(), restructureNote: () => Promise.resolve(), runSkeleton: (_b?: boolean) => Promise.resolve(), newNoteUnder: (_p: string) => Promise.resolve(), importMarkdown: (_f: FileList | null, _u?: string, _k?: boolean) => Promise.resolve(), runVoice: (_f: number, _t: number) => Promise.resolve(), flushChangeLayers: (_k?: boolean) => Promise.resolve() })
  const [noteHarnessStatus, setNoteHarnessStatus] = useState('')
  // The result line after a run (how many rounds, how many chars added, why it stopped) stays until the user closes it / switches notes /
  // runs again. It used to be just a toast, gone in seconds, leaving the user only a "1 change" toolbar to look back at.
  const [harnessDone, setHarnessDone] = useState(false)
  const [showShortcuts, setShowShortcuts] = useState(false)
  // After ingest, make "Memory" recall once more: it won't re-query by itself if the body hasn't changed, yet the freshly ingested facts are exactly what the user wants to see
  const [ingestTick, setIngestTick] = useState(0)
  const harnessDoneRef = useRef(false)

  const stuckCheckRef = useRef<{ check: string; rounds: number } | null>(null)
  // Per-round disposition: when on, each round stops after writing and waits for you to accept/revert each change in the editor,
  // then you click "Keep writing". Off is the old behavior — run straight through, then dispose, which means
  // any disposition you make during the run gets overwritten by the next round.
  const [reviewEachRound, setReviewEachRound] = useState(false)
  const [pausedRun, setPausedRun] = useState<
    { id: string; noteId: string; mode: 'write' | 'polish' } | null>(null)
  // Whether this round stopped at "waiting for your disposition". **Must be a ref, not state**: it's read in
  // runNoteHarness's finally, which is a closure where state is forever the stale value from when this run
  // started.
  const pausedRef = useRef(false)
  const [tapMeta, setTapMeta] = useState<TapMeta | null>(null)
  /** Deterministic check of the passage just written (backend `harness/checks/tap.py`, plan 8.1).
   *  **Judged, not blocked** — shown with the output under the source line above the body; the user decides whether to redo. */
  const [tapNotes, setTapNotes] = useState<string[]>([])
  const [writingPlanParent, setWritingPlanParent] = useState<TreeRow | null>(null)
  const [harness, setHarness] = useState<HarnessState | null>(null)
  const [job, setJob] = useState('')

  // When the harness starts, switch the right pane to "Plan": the plan + what each round judged, right in front of you (criterion 3)
  useEffect(() => {
    if (loading === 'note-harness') setPaneFocus((f) => ({ id: 'plan', n: (f?.n ?? 0) + 1 }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading === 'note-harness'])

  /** Which facts the body cites (regex in util/wordCount). */
  const citedIds = useMemo(() => citedFactIds(content), [content])

  const [healthMsg, setHealthMsg] = useState('')
  const [asrOffline, setAsrOffline] = useState('')
  async function checkHealth() {
    try {
      const h = await api.health()
      // LLM unreachable is a hard failure, so red text stays; voice is an optional service (most users haven't configured ASR),
      // so it only gets a grey "Voice offline", address on hover — a permanent ⚠ line used to look like an outage.

      setHealthMsg(healthMessage(h.llm ?? {}))
      setAsrOffline(!h.asr?.ok ? (h.asr?.base_url ?? '') : '')
    } catch { setHealthMsg(t('Backend unreachable')) }
  }

  function llmGate(): boolean {
    const why = llmGateMessage(healthMsg)
    if (!why) return true
    toastAction(why, t('Open Settings'), () => void openVirtual('app:settings', t('Settings')), 8000)
    void checkHealth()
    return false
  }
  const [focusMode, setFocusMode] = useState(false)
  // Left and right panes are each resizable and independently collapsible, stored locally per user (Trilium stores leftPaneWidth /
  // rightPaneWidth / leftPaneVisible; same idea). focusMode remains as the
  // "collapse both" shortcut.
  const [panes, setPanes] = useState(() => {

    // with the 16px padding (also their value), 260 truncates tree titles earlier.
    const d = { leftW: 280, rightW: 340, leftOn: true, rightOn: true }
    try {
      const raw = localStorage.getItem('memoket-note-panes:' + api.getUser())
      return raw ? { ...d, ...(JSON.parse(raw) as Partial<typeof d>) } : d
    } catch { return d }
  })
  useEffect(() => {
    try { localStorage.setItem('memoket-note-panes:' + api.getUser(), JSON.stringify(panes)) } catch { /* doesn't matter */ }
  }, [panes])
  // When the window is narrow the body wins: keeping both side panes at the user's widths squeezes the editor to 300px (900×600

  // widening the window brings it back); the left pane takes at most 30% of the window.
  const [winW, setWinW] = useState(() => window.innerWidth)
  useEffect(() => {
    const on = () => setWinW(window.innerWidth)
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  const { leftW, splitW, leftShown, rightShown: rightFits } = layoutPanes({ winW, panes, splitW: split?.w ?? null, focusMode })
  const rightShown = rightFits && !!current
  const [selectionMenu, setSelectionMenu] = useState<{ x: number; y: number; text: string } | null>(null)
  // Paragraph at the cursor: the right pane's "Memory" queries its relation to the knowledge base by it (conflict / continuation / corroboration / unsupported)
  const [cursorPara, setCursorPara] = useState('')
  // Margin memory: 1.5s after editing stops, batch-judge paragraphs containing numbers; a dot lights up at the right of the paragraph's first line (zero LLM)
  const [marginMarks, setMarginMarks] = useState<MarginMark[]>([])

  const [noRecordDots, setNoRecordDots] = useState(0)

  const [marginCard, setMarginCard] = useState<{ m: MarginMark; anchor: DOMRect; reason: 'hover' | 'click' | 'cursor' } | null>(null)

  const [traceCard, setTraceCard] = useState<TraceCardState | null>(null)

  const [runRevs, setRunRevs] = useState<api.NoteRevision[]>([])
  const [runsTick, setRunsTick] = useState(0)
  const runs = useMemo(() => groupRuns(runRevs), [runRevs])
  useEffect(() => {
    const id = current?.id
    if (!id) { setRunRevs([]); return }
    let alive = true
    api.listRevisions(id).then((r) => { if (alive) setRunRevs(r) }).catch(() => { if (alive) setRunRevs([]) })
    return () => { alive = false }
  }, [current?.id, current?.updated_at, harnessDone, runsTick])

  const [intent, setIntent] = useState<DocIntent>(() => resolveIntent(null, ''))
  // Dev hot reload may keep a title prefill already put into state by an old version; withdraw it on the spot
  // instead of waiting for the user to reopen the note, so "Plan" doesn't keep showing and executing a requirement the user never chose.
  useEffect(() => {
    if (intent.source === 'prefill') setIntent(resolveIntent(intent, ''))
  }, [intent])
  /** Intent changed (a field, or a "done criterion" ticked): update locally first, persist, and the tree's copy follows. Editing a field and ticking go the same way. */
  const saveIntent = useCallback((next: DocIntent) => {
    setIntent(next)
    if (next.goal.trim()) setNoteHarnessStatus('')
    const id = current?.id
    if (!id) return
    api.saveIntent(id, next)
      .then((n) => setNotes((prev) => prev.map((x) => (x.id === n.id ? { ...x, intent: n.intent } : x))))
      .catch((e) => toast(t('Could not save intent: {err}', { err: friendlyError(e) }), 'error'))
  }, [current?.id])


  const skeletonAbortRef = useRef<AbortController | null>(null)
  const restructureAbortRef = useRef<AbortController | null>(null)
  const [scopeTick, setScopeTick] = useState(0)
  useEffect(() => {
    const on = () => setScopeTick((t) => t + 1)
    window.addEventListener('memory-scope-changed', on)
    // "Ignore" clicked on the card: that dot goes out immediately, without waiting for the next recompute
    const gone = (e: Event) => setMarginMarks((prev) => prev.filter((m) => markKey(m) !== (e as CustomEvent<string>).detail))
    window.addEventListener('relation-ignored', gone)
    return () => { window.removeEventListener('memory-scope-changed', on); window.removeEventListener('relation-ignored', gone) }
  }, [])

  const marginCache = useRef(new Map<string, MarginVerdict>())
  useEffect(() => { marginCache.current.clear() }, [ingestTick, scopeTick])
  useEffect(() => {
    if (!current) { setMarginMarks([]); setNoRecordDots(0); return }
    // Strip images / link URLs / citation ids first: the digits in a line like `![x](/api/assets/52dd….png)` would push it over the threshold into recall.

    // "some paragraphs have dots, some don't"; now it's sent in batches of 80, tens of milliseconds each.
    const paras = marginParagraphs(content, stripForRecall)
    if (paras.length === 0) { setMarginMarks([]); setNoRecordDots(0); return }
    let stale = false
    const t = setTimeout(async () => {

      // Batches go in order and **each batch is drawn as soon as it returns** (parallel wasn't faster: the backend is serial; 2 batches in parallel measured 21.6s).
      if (marginCache.current.size > MARGIN_CACHE_MAX) marginCache.current.clear()
      const { hits, misses } = splitCached(paras, marginCache.current)
      const marks: MarginMark[] = [...hits]
      const ignored = ignoredSet()                 // pairs that were "ignored" no longer light up (same list as the right pane's cards)

      // rationale is on `editor/marginMemory.dotWorthy`; here we only "don't draw" and "count how many paragraphs",
      // and the sentence on the panel is said by `noRecordNote`.
      const show = () => {
        const keep = [...marks].sort((a, b) => a.line - b.line).filter((m) => !ignored.has(markKey(m)))
        setNoRecordDots(keep.filter((m) => !dotWorthy(m)).length)
        setMarginMarks(keep.filter(dotWorthy))
      }
      if (misses.length === 0 || hits.length) show()
      for (const chunk of chunked(misses, MARGIN_BATCH)) {
        try {
          const r = await api.memoryRelationsBatch(chunk.map((p) => p.text))
          r.marks.forEach((m, i) => {
            const v: MarginVerdict = m ? { relation: m.relation, say: m.say, kinds: m.kinds, fact_ids: m.fact_ids, facts: m.facts, why: m.why } : null
            marginCache.current.set(chunk[i].text, v)   // cache first: even if this round is discarded, the next one needn't ask about these paragraphs again
            if (v) marks.push({ ...v, line: chunk[i].line })
          })
          if (stale) return                        // body changed again; this batch is void, wait for the next round
        } catch { return }
        show()
      }
    }, 1500)
    return () => { stale = true; clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, current?.id, ingestTick, scopeTick])
  const [selectionBusy, setSelectionBusy] = useState<false | SelectionAction>(false)

  const selectionAbortRef = useRef<AbortController | null>(null)


  const [verifyResult, setVerifyResult] = useState<(VerifyResult & { passage: string }) | null>(null)

  useEffect(() => { setVerifyResult(null) }, [current?.id])

  // `roundDiff` is an "add a layer" message to the editor; the layer itself lives in the editor's field; once sent the message should be void,
  // otherwise every editor remount (close/reopen / note switch) re-adds the layer at the old coordinates, marking other text
  useEffect(() => { setRoundDiff(null) }, [current?.id])
  /** "Backstory" results. They land in a right-pane tab rather than a popover — criterion 2: looking at an old record
   *  shouldn't leave this page; a popover either covers the body or is gone once closed. */
  const [trace, setTrace] = useState<
    { noteId: string; answer: string; facts: api.Fact[]; recalled?: number | null; at: string; passage?: string } | null>(null)
  /** A backstory belongs to the note that issued the query. Hidden from the right pane on note switch; still checkable on switching back. */
  const currentTrace = trace?.noteId === current?.id ? trace : null

  const editorViewRef = useRef<EditorView | null>(null)

  const jumpToLine = useCallback((line: number) => {
    const v = editorViewRef.current
    if (!v) return
    const l = v.state.doc.line(Math.max(1, Math.min(line, v.state.doc.lines)))
    v.dispatch({ selection: { anchor: l.from }, effects: EditorView.scrollIntoView(l.from, { y: 'center' }) })
    v.focus()
  }, [])

  const jumpToPassage = useCallback((passage?: string) => {
    const line = passageLine(content, passage ?? '')
    return line === null ? undefined : () => jumpToLine(line)
  }, [content, jumpToLine])
  const abortRef = useRef<AbortController | null>(null)

  // setTimeout callbacks close over whatever `loading` was at schedule time,
  // which is stale by the time they fire seconds later -- a ref mirror gives
  // them the live value so a background run doesn't stack on top of another
  // one (manual or auto) that's already in flight.
  const loadingRef = useRef(loading)
  useEffect(() => { loadingRef.current = loading }, [loading])
  const lastSkeletonContent = useRef('')

  // Ref mirrors for the infinite-continue harness — the same "stale closure" problem:
  // the handlers object of api.runWritingPlan() is created once when runHarness() is called,
  // and every SSE event reuses that closure afterwards; if onDelta read
  // `current`/`harness.follow` directly, it would always see the values from "the moment Keep writing was clicked",
  // and a later manual note switch by the user would go unnoticed.
  const harnessAbortRef = useRef<AbortController | null>(null)
  const currentRef = useRef<Note | null>(current)
  useEffect(() => { currentRef.current = current }, [current])

  const notesRef = useRef<Note[]>(notes)
  useEffect(() => { notesRef.current = notes }, [notes])
  const harnessFollowRef = useRef(true)
  useEffect(() => { harnessFollowRef.current = harness?.follow ?? true }, [harness?.follow])

  // ---------------------------------------------------------------- loading

  const reload = useCallback(async () => {
    const list = await api.listNotes()
    setNotes(list)
    // Tabs of notes no longer in the library (deleted elsewhere, import rolled back) are closed too — clicking them would only say "not found"
    const ids = new Set(list.map((n) => n.id))
    // Virtual tabs get the same pass: unknown kb:* ids (kb:overview left by an old version) are closed as well
    const knownVirtual = isKnownVirtual
    setTabs((prev) => {
      const kept = prev
        .filter((t) => (api.isVirtualId(t.noteId) ? knownVirtual(t.noteId) : ids.has(t.noteId)))

        .map((tab) => (tab.title === tab.noteId && tab.noteId.startsWith('kb:fact:') ? { ...tab, title: t('Fact {id}', { id: tab.noteId.slice(8) }) }
          : tab.noteId.startsWith('kb:unit:') && tab.title === tab.noteId.slice(8) ? { ...tab, title: t('Meeting notes') } : tab))
      const kb = kept.find((t) => isKbVirtual(t.noteId))
      return kb ? syncVirtualTab(kept, kb, null) : kept
    })
    return list
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem('memoket-note-tabs:' + api.getUser(), JSON.stringify(tabs))
    } catch { /* can't write in private mode; not worth an error */ }
  }, [tabs])
  useEffect(() => {
    if (!current) return
    try { localStorage.setItem('memoket-note-active:' + api.getUser(), current.id) } catch { /* same as above */ }
  }, [current])
  // Window title follows the current note (recognizable in Mission Control / window switcher / taskbar)
  useEffect(() => {
    const what = current ? displayTitle({ title, content }) : (virtualId ? (VIRTUAL_LABELS[virtualId] ?? tabs.find((t) => t.noteId === virtualId)?.title ?? '') : '')
    document.title = what ? `${what} · MEMOKET NOTE` : 'MEMOKET NOTE'
  }, [current, title, content, virtualId, tabs])

  /** Sync tabs when opening a note: switch to it if already open, otherwise open a new one.
   *
   *  **Not an endless pile of tabs, one per opened note** — the tab row would be full in minutes. Reusing
   *  open ones is what both browsers and Trilium do. */
  const syncTab = useCallback((note: Note) => {
    // **Updaters must be pure.** The first version put setActiveTabId inside setTabs's
    // updater — this file already warns about the same thing elsewhere (see the block above
    // liveContentRef): React 19 StrictMode double-invokes updaters. In practice opening three notes in a row
    // produced only one tab.
    //
    // Now this only handles "does this tab exist"; **which one is current** is derived from
    // current by the effect below — one source of truth, nothing to sync in two places.
    const label = displayTitle(note)
    setTabs((prev) => {
      const found = prev.find((x) => x.noteId === note.id)
      if (found) {
        return found.title === label
          ? prev
          : prev.map((x) => (x.id === found.id ? { ...x, title: label } : x))
      }
      return [...prev, { id: 't' + Math.random().toString(36).slice(2, 9),
                         noteId: note.id, title: label }]
    })
  }, [])

  // Tab names follow the title / first line: if the user renames and the tab keeps the old name, they'd think it didn't take.
  useEffect(() => {
    if (!current) return
    const label = displayTitle({ title, content })
    setTabs((prev) => {
      const found = prev.find((x) => x.noteId === current.id)
      return found && found.title !== label
        ? prev.map((x) => (x.id === found.id ? { ...x, title: label } : x))
        : prev
    })
  }, [title, content, current])

  // The current tab is derived from current. So "open a note" has only one thing to do (syncTab),
  // and which tab is highlighted is its result, not yet another state to remember to sync.
  useEffect(() => {
    const key = current?.id ?? virtualId
    if (!key) return
    const tab = tabs.find((x) => x.noteId === key)
    if (tab && tab.id !== activeTabId) setActiveTabId(tab.id)
  }, [current, virtualId, tabs, activeTabId])

  function reopenLastTab() {
    const c = closedTabs.current.pop()
    if (!c) return
    const t = c.tab
    setTabs((prev) => {
      if (prev.find((x) => x.noteId === t.noteId)) return prev
      const at = Math.min(c.at, prev.length)
      return [...prev.slice(0, at), t, ...prev.slice(at)]
    })
    activateTab(tabs.find((x) => x.noteId === t.noteId) ?? t)
  }
  function closeTabsWhere(pred: (t: Tab, i: number) => boolean) {
    const gone = tabs.filter(pred)
    if (gone.length === 0) return
    closedTabs.current = [...closedTabs.current, ...gone.map((tab) => ({ tab, at: tabs.indexOf(tab) }))].slice(-20)
    const next = tabs.filter((t, i) => !pred(t, i))
    setTabs(next)
    if (activeTabId && gone.some((t) => t.id === activeTabId)) {
      if (next[0]) activateTab(next[0])
      else { setActiveTabId(null); setCurrent(null); setVirtualId(null); setTitle(''); setContent('') }
    }
  }
  /** Tab context menu (the items relevant to us among the 9 in tab_row.ts:377-416). Disabled items carry a reason. */
  function tabMenuItems(tab: Tab): MenuItem[] {
    const i = tabs.findIndex((x) => x.id === tab.id)
    const only = tabs.length <= 1
    const last = i === tabs.length - 1
    const none = closedTabs.current.length === 0
    return [
      { label: t('Open in split view'), icon: 'bx-columns', onSelect: () => openInSplit(tab.noteId) },
      { kind: 'sep' },
      { label: t('Close'), icon: 'bx-x', shortcut: '⌘W', onSelect: () => closeTab(tab.id) },
      { label: t('Close others'), disabled: only, hint: only ? t('This is the only one') : undefined,
        onSelect: () => closeTabsWhere((x) => x.id !== tab.id) },
      { label: t('Close tabs to the right'), disabled: last, hint: last ? t('Already the rightmost') : undefined,
        onSelect: () => closeTabsWhere((_t, k) => k > i) },
      { label: t('Close all'), onSelect: () => closeTabsWhere(() => true) },
      { kind: 'sep' },
      { label: t('Reopen closed tab'), shortcut: '⇧⌘T', disabled: none, hint: none ? t('Nothing recently closed') : undefined,
        onSelect: reopenLastTab },
    ]
  }
  function reorderTab(id: string, index: number) {
    setTabs((prev) => {
      const from = prev.findIndex((t) => t.id === id)
      if (from < 0) return prev
      const next = prev.filter((t) => t.id !== id)
      next.splice(index > from ? index - 1 : index, 0, prev[from])
      return next
    })
  }

  /** Close a tab. Closing the current one switches to **the one on the right** (or the left if none) — same as
   *  browsers. Jumping back to the first note in the list would lose the user's sense of place. */
  tabsRef.current = tabs
  closeTabRef.current = closeTab
  // App menu "Tabs" (main.tsx forwards menu events as window 'tab-action'): refresh the latest closure on every render
  tabActionRef.current = (action) => {
    const i = tabs.findIndex((t) => t.id === activeTabId)
    if (action === 'close') { if (activeTabId) closeTab(activeTabId) }
    else if (action === 'reopen') reopenLastTab()
    else if (action === 'next' || action === 'prev') { if (tabs.length > 1) activateTab(tabs[(i + (action === 'next' ? 1 : -1) + tabs.length) % tabs.length]) }
    else if (action === 'list') setTabListAt({ x: Math.max(8, window.innerWidth - 420), y: 44 })
    else if (action === 'close-others') closeTabsWhere((t) => t.id !== activeTabId)
  }
  function closeTab(id: string) {
    const i = tabs.findIndex((x) => x.id === id)
    if (i < 0) return
    if (current && tabs[i].noteId === current.id && freshEmpty.current.has(current.id) && !title.trim() && !content.trim()) {
      void dropIfStillEmpty(current)
    }
    closedTabs.current = [...closedTabs.current, { tab: tabs[i], at: i }].slice(-20)
    const next = tabs.filter((x) => x.id !== id)
    setTabs(next)
    if (id !== activeTabId) return
    const fallback = next[i] ?? next[i - 1] ?? null
    if (fallback) activateTab(fallback)
    else {
      setActiveTabId(null); setCurrent(null); setVirtualId(null); setTitle(''); setContent('')
    }
  }

  const reloadTree = useCallback(async (kb = true) => {
    const t0 = performance.now()
    const rows = await api.getTree()
    const fetched = performance.now() - t0
    setTree(rows)

    if (rows.length >= 200) requestAnimationFrame(() => void api.clientLog('info', `tree ${rows.length} rows: fetch ${Math.round(fetched)} ms, paint ${Math.round(performance.now() - t0)} ms`, '', 'perf'))
    // Refresh the knowledge-base subtree too: after ingesting new facts, topic/month counts must keep up.
    // If it can't be fetched (KITE has no library yet), treat it as absent; real notes aren't affected.
    // Saving the body doesn't touch the knowledge base (citation counts live on the notes tree side): save() passes false, so the KB tree isn't refetched on every paragraph.
    if (kb) api.kbTree().then((rows) => setKbRows(rows.filter(notSpeakerEntity))).catch(() => setKbRows([]))
    return rows
  }, [])


  const notSpeakerEntity = (r: TreeRow) => !(r.note_id.startsWith('kb:entity:') && isSpeakerTag(r.title))

  // bare ids — fill in the real names once the data arrives.
  useEffect(() => {
    if (kbRows.length === 0) return
    setTabs((prev) => {
      let changed = false
      const next = prev.map((t) => {
        if (!api.isVirtualId(t.noteId) || t.title !== t.noteId) return t
        const r = kbRows.find((x) => x.note_id === t.noteId)
        if (!r) return t
        changed = true
        return { ...t, title: r.title }
      })
      return changed ? next : prev
    })

    // so watching only kbRows would never get another chance. The changed guard prevents loops.
  }, [kbRows, tabs])

  /** The knowledge base used to be a whole subtree hung at the bottom of the tree (topics / entities / timeline… expanding level by level).
   * That didn't fit; the reasons are in docs/sidebar-ia-plan.md §1. In one sentence: **the tree is "what I wrote, how I arranged
   * it", the knowledge base is "what the machine extracted, how the machine arranged it"** — two hierarchies with opposite rules: notes can be renamed, dragged
   * and deleted, topics can't; and the sizes are inverted: in this library real notes were 26 rows, the KB subtree 180 rows,
   * so the node at the bottom held an order of magnitude more than everything above it combined.
   *
   * `allRows` still merges the KB root in, only for breadcrumbs, page titles and KB-page lookups;
   * it's no longer fed to NoteTree. The KB entry is in the leftmost launcher; the note tree only expresses the user's own
   * note hierarchy. */
  const allRows = useMemo(() => {
    const entry = kbRows.find((r) => r.note_id === 'kb')
    return entry ? [...tree, { ...entry, child_count: 0, is_expanded: false }] : tree
  }, [tree, kbRows])

  /** Open a virtual node. The knowledge base always reuses one workspace tab; special pages such as settings and import
   *  still keep their own tabs. Persist the note being written before leaving it — same discipline as switchTo. */
  async function openVirtual(id: string, title?: string) {


    if (!api.isVirtualId(id)) {
      const n = notes.find((x) => x.id === id)
      if (n) { await switchTo(n); return }
    }
    // Unknown kb:* ids (like the early kb:overview) land on the overview instead of an empty page with just the bare id

    if (id.startsWith('kb:') && !isKnownVirtual(id)) id = 'kb'
    if (virtualId === id && !current) return
    rememberSpot()
    await save()
    const leaving = current
    pushHistory(id)
    void dropIfStillEmpty(leaving)
    setCurrent(null); setTitle(''); setContent('')
    setVirtualId(id)

    // Filtered fact table: the tab is called "Fact table · work", not the tree row "N more · view in fact table" (that's the entry's wording, not the page's name)
    const label = title ?? factsLabel(id) ?? allRows.find((r) => r.note_id === id)?.title ?? VIRTUAL_LABELS[id]
      ?? (id.startsWith('kb:unit:') ? t('Meeting notes') : /^kb:(topic|entity):/.test(id) ? id.split(':').slice(2).join(':')
        : id.startsWith('kb:fact:') ? t('Fact {id}', { id: id.slice(8) }) : id)
    setTabs((prev) => syncVirtualTab(prev, {
      id: 't' + Math.random().toString(36).slice(2, 9), noteId: id, title: label,
    }, activeTabId))
  }

  // The right-pane panels have no handle on openVirtual, so a window event carries "open some virtual node"
  // over here (same pattern as open-command-palette).
  useEffect(() => {
    const on = (e: Event) => { const id = (e as CustomEvent<string>).detail; if (id) void openVirtual(id) }
    const onNew = () => void newNote()
    const onToday = () => void openToday()
    window.addEventListener('open-today', onToday)
    const onKeys = () => setShowShortcuts(true)
    // ⌘[ / ⌘] in the editor are eaten by CodeMirror's indent; the editor converts them into this event itself
    const onNav = (e: Event) => goHistory((e as CustomEvent<number>).detail < 0 ? -1 : 1)
    window.addEventListener('nav-history', onNav)
    // The two buttons at the bottom of the tree now appear only when the mouse enters the left pane; give them a keyboard entry in ⌘K
    const onLocate = () => setLocateTick((v) => v + 1)
    const onCollapse = () => void actionsRef.current.collapseAll()
    window.addEventListener('tree-locate', onLocate)
    window.addEventListener('tree-collapse', onCollapse)
    // Whole-library export: navigating to the endpoint URL is the download (Electron goes through the system save dialog)
    const onExport = () => { void save(); window.location.href = `/api/export/markdown?user=${encodeURIComponent(api.getUser())}` }
    window.addEventListener('export-all', onExport)
    // Ask before the desktop shell quits: reply flushed once saved (also on save failure, don't block quitting — the draft is already stored locally)
    // Also clean up just-created, still-empty "Untitled" notes on quit — they were cleaned on switching away but not on quit, and the demo library

    const onFlush = () => {
      rememberSpot()
      save().catch(() => {})
        .then(() => actionsRef.current.dropIfStillEmpty(currentRef.current)).catch(() => {})
        .finally(() => window.memoketDesktop?.flushed?.())
    }
    window.addEventListener('flush-save', onFlush)
    // Refresh / close window: desktop's ⌘Q goes through flush-save; the web version and reload come here
    const onUnload = () => rememberSpot()
    window.addEventListener('beforeunload', onUnload)
    const onOpenNote = (e: Event) => {
      const id = (e as CustomEvent<string>).detail
      const n = notes.find((x) => x.id === id)
      if (n) { void switchTo(n); return }
      // Just created (e.g. "Save as note") and not in the list yet: fetch once and open, don't rush to say it doesn't exist
      void api.getNote(id).then((fresh) => { void reload(); void reloadTree(); void switchTo(fresh) }).catch(() => toast(t('The linked note no longer exists'), 'error'))
    }
    // A virtual page learns its real name only after loading (a meeting page's title): update the tab
    const onTitle = (e: Event) => {
      const { id, title } = (e as CustomEvent<{ id: string; title: string }>).detail
      setTabs((prev) => prev.map((t) => (t.noteId === id && t.title !== title ? { ...t, title } : t)))
    }
    window.addEventListener('virtual-title', onTitle)
    // The virtual page itself says "what I point to is gone" (fact 404): close its tab. Go through closeTabRef for the latest closure
    const onGone = (e: Event) => { const id = (e as CustomEvent<string>).detail; const t = tabsRef.current.find((x) => x.noteId === id); if (t) closeTabRef.current(t.id) }
    window.addEventListener('virtual-gone', onGone)
    const onTabAction = (e: Event) => tabActionRef.current((e as CustomEvent<string>).detail)
    window.addEventListener('tab-action', onTabAction)
    window.addEventListener('open-note', onOpenNote)
    window.addEventListener('open-virtual', on)
    window.addEventListener('new-note', onNew)
    window.addEventListener('show-shortcuts', onKeys)
    // ⌘K "Change icon" / tree menu "Change icon…": only for the note open in the main pane; hint if no note is open
    const onIconPicker = () => { if (current) setIconPicker(true); else toast(t('Open a note first to change its icon')) }
    window.addEventListener('open-icon-picker', onIconPicker)
    return () => { window.removeEventListener('open-icon-picker', onIconPicker); window.removeEventListener('open-today', onToday); window.removeEventListener('virtual-title', onTitle); window.removeEventListener('virtual-gone', onGone); window.removeEventListener('tab-action', onTabAction); window.removeEventListener('open-virtual', on); window.removeEventListener('new-note', onNew); window.removeEventListener('show-shortcuts', onKeys); window.removeEventListener('open-note', onOpenNote); window.removeEventListener('nav-history', onNav); window.removeEventListener('tree-locate', onLocate); window.removeEventListener('tree-collapse', onCollapse); window.removeEventListener('export-all', onExport); window.removeEventListener('flush-save', onFlush); window.removeEventListener('beforeunload', onUnload) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, virtualId, allRows, notes])

  /** The fallback after clicking a tab / ⌘digit / closing a tab all goes through here: real notes go to switchTo,
   *  virtual nodes to openVirtual. */
  function activateTab(tab: Tab | undefined) {
    if (!tab) return
    if (api.isVirtualId(tab.noteId)) { void openVirtual(tab.noteId, tab.title); return }
    const note = notes.find((n) => n.id === tab.noteId)
    if (note) void switchTo(note)
    else setActiveTabId(tab.id)
  }

  /** A node was clicked in the tree. */
  function openFromTree(id: string, mods?: { alt: boolean }) {
    if (api.isVirtualId(id)) { void openVirtual(id); return }
    const n = notes.find((x) => x.id === id)
    if (!n) return
    if (mods?.alt) setQuick(n)     // take a peek without leaving the current note (PopupEditor)
    else void switchTo(n)
  }

  /** Path of what's being viewed in the tree (breadcrumbs). Takes the first one for clones. */
  const noteIdSet = useMemo(() => new Set(notes.map((n) => n.id)), [notes])
  const crumbs = useMemo(
    () => buildCrumbs(current?.id ?? virtualId, allRows, (id) => tabs.find((t) => t.noteId === id)?.title, api.isVirtualId),
    [current, virtualId, allRows, tabs])
  /** Whether this note is a day in the journal (if so the ribbon gets an extra "Screen activity" block, plan §8.4).
   *  Memoized: it flattens the whole tree into a table, so recomputing on every render is wasted money. */
  const journalDay = useMemo(
    () => (current ? journalDateOf(allRows, current.id) : null), [current, allRows])

  /** Context menu for virtual nodes — no "Delete" / "Move": they aren't notes, they're a view of the
   *  knowledge base. What they do have are actions that bring them into a note. */
  function kbMenuItems(row: TreeRow): MenuItem[] {
    const isFact = api.isFactId(row.note_id)
    const factId = row.note_id.slice('kb:fact:'.length)
    const items: MenuItem[] = [
      { label: t('Open'), icon: 'bx-link-external', onSelect: () => void openVirtual(row.note_id, factsLabel(row.note_id) ?? row.title) },   // if the tail row's name is an entry's wording, the tab uses the page name
      { label: t('Open in split view'), icon: 'bx-columns', onSelect: () => openInSplit(row.note_id) },
    ]
    if (isFact) {
      items.push(
        { kind: 'sep' },
        { label: t('Copy citation'), icon: 'bx-copy', hint: `[${factId}]`,
          onSelect: () => { void navigator.clipboard.writeText(`[${factId}]`) } },
      )
      if (current) items.push({ label: t('Cite in current note'), icon: 'bx-link', hint: current.title || t('Untitled'),
                                onSelect: () => insertAtCursor(`[${factId}]`) })
    }
    return items
  }

  /** Tree context menu. **Harness actions grow directly on the node** — Smart Continue / Polish act on one note,
   *  infinite continue acts on a subtree, and the tree already has exactly these two levels, "a note" and "a subtree".
   *  Make them capabilities of the node, instead of opening another panel to pick a target.
   *
   *  Grouping follows Trilium's tree menu: open → insert → structure → clipboard/clone → dangerous actions.
   */
  function treeMenuItems(row: TreeRow): MenuItem[] {
    const note = notes.find((n) => n.id === row.note_id)
    const isClone = row.branch_count > 1
    return [
      { label: t('Open'), icon: 'bx-link-external', shortcut: '↩', onSelect: () => { if (note) void switchTo(note) } },
      { label: t('Open in new tab'), icon: 'bx-window-open', onSelect: () => { if (note) { syncTab(note); void switchTo(note) } } },
      { label: t('Quick look'), icon: 'bx-show', hint: t('⌥-click'), onSelect: () => { if (note) setQuick(note) } },
      { label: t('Open in split view'), icon: 'bx-columns', hint: t('Write side by side'), onSelect: () => openInSplit(row.note_id) },
      { kind: 'sep' },
      { kind: 'header', label: t('New') },
      { label: t('Insert child note'), icon: 'bx-plus', hint: t('Becomes its child'),
        onSelect: () => void newNoteUnder(row.note_id) },
      { label: t('Insert note after'), icon: 'bx-subdirectory-right',
        onSelect: () => void newNoteUnder(row.parent_note_id) },
      { label: t('Rename'), icon: 'bx-rename', shortcut: 'F2', onSelect: () => void renameNode(row) },
      { label: t('Change icon…'), icon: 'bx-smile', hint: t('Same icon in tree, tab and title'),
        onSelect: () => { const n = notes.find((x) => x.id === row.note_id); if (n) void switchTo(n).then(() => setTimeout(() => window.dispatchEvent(new CustomEvent('open-icon-picker')), 50)) } },
      { label: t('Import .md here…'), icon: 'bx-import', hint: t('Multiple files become a subtree'),
        onSelect: () => { importUnder.current = row.note_id; importInput.current?.click() } },
      { kind: 'sep' },
      { kind: 'header', label: 'AI' },
      // ---- Our own: the harness lives here, on par with structure operations
      { label: t('Smart Continue this note'), icon: 'bx-bot', disabled: !note,
        onSelect: () => { if (note) void openAndRun(note, 'write') } },
      { label: t('Polish this note'), icon: 'bx-brush', disabled: !note || !(note.content ?? '').trim(),
        onSelect: () => { if (note) void openAndRun(note, 'polish') } },
      { label: t('Endless writing on this subtree'), icon: 'bx-rocket', disabled: row.child_count === 0,
        hint: row.child_count === 0 ? t('No notes under it yet') : undefined,
        onSelect: () => setWritingPlanParent(row) },
      { kind: 'sep' },
      { label: t('Clone to…'), icon: 'bx-duplicate', hint: t('Same note, visible in both places'),
        onSelect: () => void cloneNodeTo(row) },
      { label: t('Move to…'), icon: 'bx-transfer', onSelect: () => void moveNodeTo(row) },
      { label: t('Remove from this position'), icon: 'bx-unlink', disabled: !isClone,
        hint: isClone ? undefined : t('It only exists here'),
        onSelect: () => void detachNode(row) },
      { label: t('Copy note path'), icon: 'bx-copy-alt', onSelect: () => void copyNotePath(row) },
      { kind: 'sep' },
      { label: row.child_count > 0 ? t('Delete (with subtree)') : t('Delete'), icon: 'bx-trash', danger: true, shortcut: '⌫',
        hint: row.child_count > 0 ? t('Deletes {n} notes with it', { n: row.child_count }) : undefined,
        onSelect: () => { if (note) void removeWithSubtree(note, row) } },
    ]
  }

  /** List what will be deleted before deleting a subtree — it takes invisible things with it, and before clicking the user
   *  doesn't know how many notes will go (Trilium's delete_notes dialog). A single note still uses optimistic delete + undo. */
  async function removeWithSubtree(note: Note, row: TreeRow) {
    const kids = [...subtreeIds(row.note_id)].filter((id) => id !== row.note_id)
    if (kids.length === 0) { remove(note); return }
    const names = kids.slice(0, 8).map((id) => '· ' + displayTitle(tree.find((r) => r.note_id === id) ?? { title: id }))
    const ok = await askConfirm({
      title: t('Delete “{title}” and the {n} notes under it?', { title: displayTitle(row), n: kids.length }),
      detail: names.join('\n') + (kids.length > 8 ? '\n' + t('· …{n} more', { n: kids.length - 8 }) : ''),
      okLabel: t('Delete'), danger: true,
    })
    if (ok) remove(note, new Set([row.note_id, ...kids]))
  }


  async function collapseAll() {
    const open = tree.filter((r) => r.is_expanded)
    setTree((prev) => prev.map((r) => ({ ...r, is_expanded: false })))
    await Promise.all(open.map((r) => api.setBranchExpanded(r.note_id, r.parent_note_id, false).catch(() => {})))
  }

  async function newNoteUnder(parentId: string) {
    let n: Note
    try { n = await api.createNote('', '', parentId) } catch (e) { toast(t('Could not create note: {err}', { err: friendlyError(e) }), 'error'); return }
    freshEmpty.current.add(n.id)
    await Promise.all([reload(), reloadTree()])
    void switchTo(n)
  }

  /** In-app input box, Promise-based — call sites stay as direct as the old window.prompt. */
  const composeAsk = (title: string, initial: string) =>
    new Promise<string | null>((resolve) => setPrompt({ title, initial, resolve: (v) => { setPrompt(null); resolve(v) } }))
  const askConfirm = (req: Omit<ConfirmRequest, 'resolve'>) =>
    new Promise<boolean>((resolve) => setConfirmReq({ ...req, resolve: (ok) => { setConfirmReq(null); resolve(ok) } }))
  const askNode = (title: string, exclude: Set<string>, first: string[] = []) =>
    new Promise<string | null>((resolve) => setPicker({ title, exclude, first, resolve: (v) => { setPicker(null); resolve(v) } }))

  async function renameNode(row: TreeRow) {
    const title = (await composeAsk(t('New name'), row.title))?.trim()
    if (title === undefined || title === row.title) return
    setTree((prev) => prev.map((r) => (r.note_id === row.note_id ? { ...r, title } : r)))
    try {
      const note = notes.find((n) => n.id === row.note_id)
      await api.saveNote(row.note_id, title, note?.content ?? '')
      await reload()
      if (current?.id === row.note_id) setTitle(title)
    } catch (e) {
      toast(t('Rename failed: {err}', { err: friendlyError(e) }), 'error')
      await reloadTree()
    }
  }

  /** Who is in this node's subtree (including itself) — these can't be chosen when moving/cloning, or it would form a cycle. */
  function subtreeIds(noteId: string): Set<string> {
    const out = new Set([noteId])
    const stack = [noteId]
    while (stack.length) {
      const p = stack.pop()!
      for (const r of tree) if (r.parent_note_id === p && !out.has(r.note_id)) { out.add(r.note_id); stack.push(r.note_id) }
    }
    return out
  }

  /** Pick a target node: a picker with search (counterpart of Trilium's move_to / clone_to). */
  function pickTarget(row: TreeRow, verb: string): Promise<string | null> {
    return askNode(t('{verb} “{title}” to where?', { verb, title: displayTitle(row) }), subtreeIds(row.note_id))
  }

  /** Drag and drop in the tree. before/after first move to the same parent and then reorder; over means move inside. */
  async function dropNode(drag: TreeRow, target: TreeRow, where: DropWhere) {
    if (api.isVirtualId(drag.note_id) || api.isVirtualId(target.note_id)) return
    if (subtreeIds(drag.note_id).has(target.note_id)) { toast(t('Cannot move into its own subtree')); return }
    try {
      if (where === 'over') {
        await api.moveBranch(drag.note_id, drag.parent_note_id, target.note_id)
      } else {
        if (drag.parent_note_id !== target.parent_note_id)
          await api.moveBranch(drag.note_id, drag.parent_note_id, target.parent_note_id)
        const sibs = tree.filter((r) => r.parent_note_id === target.parent_note_id && r.note_id !== drag.note_id)
          .sort((x, y) => x.position - y.position).map((r) => r.note_id)
        const k = sibs.indexOf(target.note_id) + (where === 'after' ? 1 : 0)
        sibs.splice(k, 0, drag.note_id)
        await api.reorderBranches(target.parent_note_id, sibs)
      }
      await reloadTree()
    } catch (e) { toast(t('Could not move: {err}', { err: String(e) }), 'error'); await reloadTree() }
  }

  async function cloneNodeTo(row: TreeRow) {
    const to = await pickTarget(row, t('Clone'))
    if (!to) return
    try {
      await api.cloneNoteTo(row.note_id, to)
      await reloadTree()
      toast(t('Cloned — both places are the same note; edit one and both change'))
    } catch (e) { toast(t('Clone failed: {err}', { err: friendlyError(e) }), 'error') }
  }

  async function moveNodeTo(row: TreeRow) {
    const to = await pickTarget(row, t('Move'))
    if (!to) return
    try {
      await api.moveBranch(row.note_id, row.parent_note_id, to)
      await reloadTree()
    } catch (e) { toast(t('Could not move: {err}', { err: String(e) }), 'error') }
  }

  async function detachNode(row: TreeRow) {
    try {
      await api.detachBranch(row.note_id, row.parent_note_id)
      await reloadTree()
    } catch (e) { toast(t('Remove failed: {err}', { err: friendlyError(e) }), 'error') }
  }

  async function copyNotePath(row: TreeRow) {
    let paths: string[][]

    try { paths = await api.notePaths(row.note_id) } catch (e) { toast(t('Could not copy path: {err}', { err: friendlyError(e) }), 'error'); return }
    const byId = new Map(tree.map((r) => [r.note_id, r.title || t('Untitled')]))
    // After cloning there's more than one path; give them all — the user knows which one they want
    const text = paths.map((p) => p.map((id) => byId.get(id) ?? id).join(' / ')).join('\n')
    try {
      await navigator.clipboard.writeText(text)
      toast(t('Path copied'))
    } catch { toast(text) }
  }

  /** Run the harness straight from the tree: switch to that note first, then run. **Running without switching would stream the output
   *  into a note the user can't see**; they'd only see the status bar spinning. */
  async function openAndRun(note: Note, mode: 'write' | 'polish') {
    await switchTo(note)
    await runNoteHarness(mode)
  }

  /** Expand/collapse a node. **State is written back to the server**, not just changed locally — a tree that fully collapses
   *  on every refresh becomes unusable after a few dozen nodes. Changing locally first gives instant
   *  feedback on click; roll back if the request fails. */
  async function toggleTreeNode(row: TreeRow) {
    const next = !row.is_expanded
    setTree((prev) => prev.map((r) => (r.id === row.id ? { ...r, is_expanded: next } : r)))
    try {
      await api.setBranchExpanded(row.note_id, row.parent_note_id, next)
    } catch {
      setTree((prev) => prev.map((r) => (r.id === row.id ? { ...r, is_expanded: !next } : r)))
    }
  }

  /** Infinite continue now runs against **a subtree of the tree** (it used to be a "folder" — the tree no longer has
   * folders; a note with children is the folder).
   *
   * The entry is still an always-visible sidebar button that decides which subtree to open on by itself: the current note's
   * parent comes first. The original feedback was "I can't find that button" — back then it was hidden in an icon on the folder
   * title bar and didn't appear at all when there were no folders. */

  /** Run the harness — lives at App level, independent of whether WritingPlanPanel is mounted (see
   * the comment above HarnessState). With follow on, every time a new section starts it switches the
   * main editor to that note and streams the body into content (exactly like how magic tap handles incremental
   * arrivals), a direct answer to "can't I see the streamed output in the actual note?". */
  async function runHarness(parent: TreeRow) {
    if (harness?.running && harness.folderId === parent.note_id) {
      harnessAbortRef.current?.abort()
      return
    }
    // A local model handling several generation requests at once only slows them all down, it isn't real parallelism — only one
    // harness may run at a time; stop the current one before running another folder.
    if (harness?.running) {
      toast(t('Endless writing on “{name}” is running; stop it before starting another', { name: harness.folderName }), 'error')
      return
    }
    const got = await api.getWritingPlan(parent.note_id)
    if (!got.plan) { toast(t('This folder has no writing plan yet; generate one in the panel first')); return }
    setHarness({
      folderId: parent.note_id, folderName: parent.title, plan: got.plan, sections: got.sections,
      running: true, currentSectionTitle: '', currentNoteId: '', preview: '', waitingFirstToken: true, follow: true,
    })
    const ctrl = new AbortController()
    harnessAbortRef.current = ctrl
    try {
      await api.runWritingPlan(parent.note_id, {
        onPlanLoaded: (p, s) => setHarness((h) => (h ? { ...h, plan: p, sections: s } : h)),
        onSectionStart: async (d) => {
          setHarness((h) => (h ? {
            ...h, waitingFirstToken: false, currentSectionTitle: d.title, currentNoteId: d.note_id, preview: '',
            sections: h.sections.map((s) => (s.id === d.section_id ? { ...s, status: 'in_progress', note_id: d.note_id } : s)),
          } : h))
          const alreadyViewing = currentRef.current?.id === d.note_id
          if (harnessFollowRef.current && !alreadyViewing) {
            try {
              const note = await api.getNote(d.note_id)
              await switchTo(note, true)
            } catch { /* the note was just created and occasionally isn't readable yet; skip this follow, the next section will try again */ }
          } else if (alreadyViewing) {
            // Next round of the same note (section unchanged, just continuing) — the locally accumulated
            // content must be separated by a blank line before this round's increments arrive, same principle as the backend's
            // prompts.join_round_text(): the previous round may have stopped right on the closing ``` of a
            // mermaid code block, and concatenating directly would glue it to the next round's content on the same

            // locally accumulated content won't match the version the backend persisted.
            setContent((c) => (c ? c.replace(/\n*$/, '') + '\n\n' : c))
          }
        },
        onDelta: (noteId, text) => {
          setHarness((h) => (h ? { ...h, waitingFirstToken: false, preview: h.preview + text } : h))
          if (currentRef.current?.id === noteId) setContent((c) => c + text)
        },
        onNoteContent: (noteId, serverContent) => {
          // At end of round / section align with the server's body (revisions are applied server-side; locally we only accumulated the continuation increments)
          if (currentRef.current?.id === noteId) { liveContentRef.current = serverContent; setContent(serverContent) }
        },
        onSectionDone: (d) => {
          setHarness((h) => (h ? {
            ...h, waitingFirstToken: true,
            sections: h.sections.map((s) => (s.id === d.section_id ? { ...s, status: 'done', summary: d.summary } : s)),
          } : h))
          if (d.blocked) toast(t('This section is stuck and needs your attention: {why}', { why: d.blocked_reason || t('unknown reason') }), 'error')
          void reload(); void reloadTree()
        },
        onPlanExtended: (newSections) => setHarness((h) => (h ? { ...h, sections: [...h.sections, ...newSections] } : h)),
        onPlanDone: (p) => {
          setHarness((h) => (h ? { ...h, plan: p } : h))
          toast(t('Writing plan for “{title}” is complete', { title: parent.title }))
          notifyIfHidden(t('MEMOKET NOTE · Sectioned writing'), t('Writing plan for “{title}” is complete', { title: parent.title }))
        },
      }, ctrl.signal)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') toast(t('Writing run failed: {err}', { err: friendlyError(e) }), 'error')
    } finally {
      setHarness((h) => (h ? { ...h, running: false, waitingFirstToken: false } : h))
      harnessAbortRef.current = null
      void reload(); void reloadTree()
    }
  }



  /** Shared between the flat search-results list and the per-folder grouped
   * list -- same note-item markup either way, only what array it's mapped
   * over differs. */
  function renderNoteItem(n: Note) {
    return (
      <div
        key={n.id}
        className={'note-item ' + (current?.id === n.id ? 'active' : '')}
        {...clickable(() => void switchTo(n))}
      >
        <div className="t">{displayTitle(n)}</div>
        {n.content.trim() && (
          <div className="muted" style={{ fontSize: 'var(--t-xs)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {(() => {
              // When the title itself is the hit (three "One year of startup" notes searched for "startup"), repeating the H1 in the snippet is redundant;
              // use the first body line instead — same-named notes are told apart by this line (same idea as ⌘K's first_body)
              const titleHit = noteQuery.trim() && displayTitle(n).toLowerCase().includes(noteQuery.trim().toLowerCase())
              const s = searchResults !== null && !titleHit ? matchSnippet(n.content, noteQuery, 40, 8) : null
              return s ? <>{s.before}<mark>{s.hit}</mark>{s.after}</> : previewLine(n.content, displayTitle(n))
            })()}
          </div>
        )}
        {/* flex instead of several float: right stacked together — three controls (folder picker /
           pin / delete) share one row with the timestamp in a 220px sidebar, and a float layout easily pushes them
           off the row and wraps wrongly when the folder name is a bit long or the timestamp format changes,
           which is hard to predict. The timestamp uses min-width: 0 + ellipsis as the "shrink first"
           one (same reasoning as the earlier .col overflow bug fix); the three controls keep a fixed
           size and aren't squeezed. */}
        <div className="muted" style={{ fontSize: 'var(--t-xs)', display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {/* Which folder it's under: with dozens of search hits, this is the only clue to tell same-named notes apart */}
            {(() => { const row = tree.find((r) => r.note_id === n.id); const parent = row && row.parent_note_id !== api.ROOT_ID ? tree.find((r) => r.note_id === row.parent_note_id) : undefined; return parent ? displayTitle(parent) + ' · ' : '' })()}
            {/* Two rows with the same name on the same day need minute precision to be told apart; others show the usual
                "Today / Yesterday / MM-DD" (`dupSuffixes` gives just enough granularity to separate them;
                ones with a space are minute-level — only those are worth overriding fmtWhen). */}
            {whenLabel(listDups.get(n.id), n.updated_at)}
          </span>
          {/* The "Move to folder" dropdown is gone: the tree moves things by drag and context menu; a dropdown
              that can only pick one level can't express a tree of arbitrary depth. */}
          <span
            className={'row-act' + (n.pinned ? ' pinned' : '')}
            title={n.pinned ? t('Unpin') : t('Pin')}
            {...clickable((e) => { e.stopPropagation(); void togglePin(n) })}
          >
            <Icon n={(n.pinned ? 'bxs-pin' : 'bx-pin')} />
          </span>
          <span
            className="row-act danger"
            title={t('Delete (undo from the toast within 5 seconds)')}
            {...clickable((e) => { e.stopPropagation(); remove(n) })}
          >
            <Icon n="bx-x" />
          </span>
        </div>
      </div>
    )
  }

  /** Record a history step. The same id twice in a row isn't recorded; after walking back and opening something new,
   *  the forward part is dropped — that's what browsers do. */
  function pushHistory(id: string) {
    const h = hist.current
    if (h.navigating) { h.navigating = false; return }
    if (h.list[h.idx] === id) return
    h.list = [...h.list.slice(0, h.idx + 1), id].slice(-100)
    h.idx = h.list.length - 1
    setHistState({ back: h.idx > 0, fwd: false })
  }
  function goHistory(step: -1 | 1) {
    const h = hist.current
    const k = h.idx + step
    if (k < 0 || k >= h.list.length) return
    h.idx = k; h.navigating = true
    setHistState({ back: k > 0, fwd: k < h.list.length - 1 })
    const id = h.list[k]
    if (api.isVirtualId(id)) void openVirtual(id)
    else { const n = notes.find((x) => x.id === id); if (n) void switchTo(n); else h.navigating = false }
  }

  function open(n: Note) {
    pushHistory(n.id)
    setVirtualId(null)
    setCurrent(n)
    // Draft that failed to save last time (see save()'s catch): if newer than the library's, put it back with a hint
    const d = resolveDraft(n, readDraft(n.id), false)
    setTitle(d.title)
    setContent(d.content)

    // opening a shorter note B would have the guard use A's length to block B's save (gauge B5 is exactly this cell).
    servedRef.current = { id: n.id, text: d.content, edits: 0 }
    if (d.restored) toast(t('Unsaved content from last time has been restored and will be saved on the next autosave'))
    if (d.clear) clearDraft(n.id)
    // The outline is read back with the note, **not cleared**. The cleared version's consequence was "it's gone after a while":
    // switch notes, refresh the page, or even infinite continue's "follow" auto-switching to the next section, and the outline was gone,
    // while the next harness round had to spend another model call regenerating it.
    setSpine(n.spine ?? '')
    setBeats(n.beats ?? [])
    setSkeletonNotes([])
    setIntent(resolveIntent(n.intent, d.title))
    setMarginCard(null)
    setTraceCard(null)
    // For a note that already has an outline, don't regenerate 8 seconds after opening — it used to be one model

    // recompute only after 20 changed chars.
    lastSkeletonContent.current = n.spine ? n.content : ''
    setRevisions([])
    setTapMeta(null)
    setTapNotes([])
    if (loading !== 'note-harness') { setHarnessDone(false); harnessDoneRef.current = false; if (!pausedRef.current) setNoteHarnessStatus('') }
    setPausedRun(null)
    syncTab(n)
    // Recover a run that stopped midway waiting for disposition.
    //
    // **Once the SSE stream breaks it can never be found again** — close the tab, restart the backend, a network blip:
    // the snapshot stays in the library, but the run_id only existed in that broken stream. What the user sees is "I
    // definitely clicked Smart Continue, and now there's nothing". This endpoint is its only way back in.
    pendingSpot.current = n.id
    void api.listPausedRuns()
      .then((runs) => {
        const mine = runs.find((r) => r.note_id === n.id)
        if (mine) {
          // The endpoint always returned mode, but it used to be hardcoded to 'write' here — a pause from a "Polish" run
          // had every hint after resuming call it "Smart Continue".
          const mode = mine.mode === 'polish' ? 'polish' : 'write'
          setPausedRun({ id: mine.id, noteId: n.id, mode })
          // Include the date: reopening days later, you need to know which day this pause is from (ones undisposed for 7 days are cleared at startup)
          setNoteHarnessStatus(
            t('{date}: {mode} paused at round {n}, waiting for your review', { date: fmtDate(mine.created_at), mode: mode === 'polish' ? t('Polish') : t('Smart Continue'), n: mine.round }))
        }
      })
      .catch(() => {})
  }

  useEffect(() => {
    const onNotesChanged = () => {
      void Promise.all([reload(), reloadTree()])
        .catch((error) => toast(t('Could not refresh notes: {err}', { err: friendlyError(error) }), 'error'))
    }
    window.addEventListener('notes-changed', onNotesChanged)
    return () => window.removeEventListener('notes-changed', onNotesChanged)
  }, [reload, reloadTree])

  useEffect(() => {
    void reload().then((list) => {
      if (!list.length) return
      // Go back to the note last viewed (tabs already survive restarts, so the body should return to the same note too);

      let last: string | null = null
      try { last = localStorage.getItem('memoket-note-active:' + api.getUser()) } catch { /* doesn't matter */ }
      open(list.find((n) => n.id === last) ?? list[0])
    })
    void reloadTree()
    void checkHealth()
    // When the provider is changed in Settings / the service recovers, the red status-bar line must follow: it used to check only at startup,
    // so "LLM unreachable" stayed up after fixing the settings until restart. Check immediately on settings change; re-check every 30 seconds while red.
    const onProvider = () => void checkHealth()
    window.addEventListener('provider-changed', onProvider)
    return () => window.removeEventListener('provider-changed', onProvider)
    // open is used only once at startup; putting it in the deps would rerun this startup logic on every note switch
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload, reloadTree])

  useEffect(() => {
    if (!healthMsg) return
    const t = setInterval(() => void checkHealth(), 30000)
    return () => clearInterval(t)
  }, [healthMsg])

  useEffect(() => {
    if (!noteQuery.trim()) { setSearchResults(null); return }
    // Sidebar search filters locally: the full-text list is already in memory at startup (notes); refetching the full-text list on every keystroke
    // (413 notes, 580KB) makes no sense. Same rules as the server: title or body contains, case-insensitive; order follows notes (pinned first, newest first).
    const needle = noteQuery.trim().toLowerCase()
    setSearchResults(notes.filter((n) => (n.title ?? '').toLowerCase().includes(needle) || (n.content ?? '').toLowerCase().includes(needle)))
  }, [noteQuery, notes])

  // Ingest is a background task. Refresh the tree when it finishes — otherwise the "ingested" ⇡ wouldn't appear until the next
  // app launch, and the user would think saving failed and save again.

  // citations page), and afterwards just an extra ⇡ on the tree. The status bar shows "Saving to knowledge base… N extracted", and the end
  // gives a toast (errors too).
  type JobInfo = { status: string; facts: number; detail: string; done: number; total: number; eta: number }
  const [jobInfo, setJobInfo] = useState<JobInfo | null>(null)
  useEffect(() => {
    setIngestActive(!!job)
    if (!job) { setJobInfo(null); return }
    const ctrl = new AbortController()
    let last: JobInfo = { status: 'queued', facts: 0, detail: '', done: 0, total: 0, eta: 0 }
    setJobInfo(last)
    api.watchJob(job, (j) => {
      last = { status: String(j.status ?? ''), facts: Number(j.facts ?? 0), detail: String(j.detail ?? ''),
               done: Number(j.chunks_done ?? 0), total: Number(j.chunks_total ?? 0), eta: Number(j.eta_s ?? 0) }
      setJobInfo(last)
    }, () => {
      void reloadTree(); void reload(); setIngestTick((t) => t + 1); setIngestActive(false); setJobInfo(null); setJob('')
      if (last.status === 'error') toast(t('Could not save to knowledge base: {err}', { err: last.detail || t('unknown error') }), 'error')
      else if (last.status === 'cancelled') toast(t('Saving to knowledge base cancelled'))
      else if (last.facts > 0) toastAction(t('Saved to knowledge base: {n} records extracted', { n: last.facts }), t('View'), () => window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:recent' })), 8000)
      else toast(t('Saved to knowledge base, but no facts worth keeping were extracted'))
      notifyIfHidden(t('MEMOKET NOTE · Knowledge base'), last.status === 'error' ? t('Ingest failed') : t('Ingest complete, {n} records', { n: last.facts }))
    }, ctrl.signal)
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job])

  const visibleNotes = searchResults ?? notes


  const listDups = useMemo(
    () => dupSuffixes(visibleNotes.map((n) => ({ key: n.id, title: displayTitle(n), at: n.updated_at }))),
    [visibleNotes])


  async function openToday(day = '') {
    await save()
    try {
      const n = await api.todayNote(day)
      await Promise.all([reload(), reloadTree()])
      await switchTo(n)
    } catch (e) { toast(t('Could not open the journal for{day}: {err}', { day: day ? ` ${day} ` : t('Today'), err: friendlyError(e) }), 'error') }
  }

  async function newNote() {
    await save()

    let n: Note
    try { n = await api.createNote('', '') } catch (e) { toast(t('Could not create note: {err}', { err: friendlyError(e) }), 'error'); return }
    freshEmpty.current.add(n.id)
    // Refresh the tree too: otherwise the new note isn't on the tree and the user thinks it "wasn't saved" (real feedback)
    await Promise.all([reload(), reloadTree()])
    open(n)
  }

  async function save() {
    if (!current) return
    if (title === current.title && content === current.content) return

    //
    // The criterion is deliberately narrow; all three must hold: ① the anchor belongs to **this note**; ② since that version was delivered
    // the editor has **reported no edits at all** (`edits === 0`); ③ what's about to be saved is **shorter than it**.
    // The user deleting text, "Revert" on the hover toolbar, "Revert all", `/` blocks — all of these break ②,
    // so none are blocked (gauges B1 / B2); the server delivering a shorter version itself (cleanup, dedup) swaps the anchor
    // too, so it isn't blocked either (B6). Only one case remains: **the user didn't touch it, yet it got shorter** (B3).
    //
    // Blocking doesn't mean "don't save" — then even the title wouldn't save; it means **save the version the server delivered**,

    const served = servedRef.current
    let body = content
    if (isStaleShrink(served, current.id, content)) {
      void api.clientLog('warn',
        `Blocked a regressing save: about to save ${content.length} chars, the server just delivered ${served.text.length} chars, `
        + `and the editor has reported no edits since — saving the server's version instead`, '', 'save-guard')
      body = served.text
      if (content !== served.text) setContent(served.text)
    }
    try {
      const n = await api.saveNote(current.id, title, body)
      setCurrent(n)
      setSaveStatus({ at: Date.now() })
      clearDraft(current.id)

      // is too wasteful — a save changes only this note, so replace it in place with the returned one; add/delete/move paths still reload()
      setNotes((prev) => (prev.some((x) => x.id === n.id) ? prev.map((x) => (x.id === n.id ? n : x)) : [n, ...prev]))
      await reloadTree(false)
    } catch (e) {
      setSaveStatus({ at: Date.now(), error: String(e) })
      // **Body that failed to save lands on this machine first**: in the seconds the backend has crashed / the network is down the user keeps writing,
      // and closing the app then would lose it all. Next time this note opens, if the library version is older, put the draft back.
      // The draft is also **the version actually to be saved** (`body`): writing `content` after the guard rewrote it

      writeDraft(current.id, title, body)
      throw e
    }
  }


  const flushChangeLayers = useCallback(async (keepalive = false) => {
    if (layersTimer.current) { clearTimeout(layersTimer.current); layersTimer.current = null }
    const view = editorViewRef.current
    const id = currentRef.current?.id
    if (!view || !id || layersReady.current !== id) return

    // so `serializeLayers` can't see them — without adding them back, this flush would amount to pressing "Drop this layer" for the user,
    // and the whole theme of this batch is "never quietly decide for him". `seq` is renumbered by array index

    const payload = [...serializeLayers(view.state), ...layerStuckRef.current.map((s) => s.saved)]
      .map((l, i) => (l.seq === i ? l : { ...l, seq: i }))
    if (layersSaved.current.noteId === id && sameLayers(layersSaved.current.payload, payload)) return
    const seq = ++layersSaveSeq.current
    try {
      const r = await api.saveChangeLayers(id, payload, keepalive)
      if (seq === layersSaveSeq.current) layersSaved.current = { noteId: id, payload }
        // **Eviction must be loud**: which layer was left out and why, say it on the spot. Silently dropping one,
        // next open becomes "the layer I kept is gone" — the same bug this batch is fixing.
        const gone = [...r.evicted, ...r.rejected]
        if (gone.length) {
          toast(t('{n} change layers could not be kept for next time: {label} — {why}{tail}', { n: gone.length, label: gone[0].label || t('this layer'), why: gone[0].why,
            tail: gone.length > 1 ? t(' ({n} more layers were lost too)', { n: gone.length - 1 }) : '' }), 'error')
        }
      void api.getWritingFeedback(id).then((x) => {
        if (currentRef.current?.id === id) setWritingFeedback(x)
      }).catch(() => undefined)
    } catch {
      if (seq === layersSaveSeq.current) layersSaved.current = { noteId: '', payload: [] } // not saved, so don't record it as saved
    }
  }, [])

  /** The editor reports "a layer moved": persist after debounce.
   *
   * **Every path that changes layers goes through here** (the hover toolbar's "Accept / Revert" doesn't pass through React at all),
   * so we don't count which kind of disposition it was — any change of `roundDiffField`'s value counts. */
  const onLayersChanged = useCallback(() => {
    const st = editorViewRef.current?.state.field(roundDiffField, false)
    // Re-render the panel only when the "disposed" ledger changes: positions drifting with typing shouldn't redraw the right pane on every keystroke
    if (st && st.settled !== lastSettled.current) { lastSettled.current = st.settled; setLayersTick((n) => n + 1) }
    if (layersTimer.current) clearTimeout(layersTimer.current)
    layersTimer.current = setTimeout(() => { layersTimer.current = null; void flushChangeLayers() }, CHANGE_LAYER_SAVE_MS)
  }, [flushChangeLayers])

  // Flush once before closing the window / tab. `keepalive` is load-bearing: without it, as soon as the page starts unloading
  // the browser kills this request — "save once before closing the app" would save nothing.
  useEffect(() => {
    const on = () => { void flushChangeLayers(true) }
    window.addEventListener('beforeunload', on)
    window.addEventListener('pagehide', on)
    return () => { window.removeEventListener('beforeunload', on); window.removeEventListener('pagehide', on) }
  }, [flushChangeLayers])


  useEffect(() => {
    const id = current?.id
    setWritingFeedback(null)
    layersReady.current = ''                       // until restored, no debounced persist may act
    layersSaved.current = { noteId: '', payload: [] }
    setLayerStuck([]); layerStuckRef.current = []  // the previous note's unrestorable layers must not follow into this one
    lastSettled.current = undefined
    if (layersTimer.current) { clearTimeout(layersTimer.current); layersTimer.current = null }
    // The EditorView is reused across notes, and roundDiffField stays alive with it. When the target note has no saved layers,
    // the old code dispatched nothing, so the previous note's highlights and "N changes" hung onto this note as-is,
    // looking like global changes. On note switch clear explicitly first, then restore only the target note's own layers.
    const openingView = editorViewRef.current
    if (openingView) {
      openingView.dispatch({ effects: restoreLayersEffect.of({ layers: [], hunks: [], settled: [] }) })
      setPendingDiff(0)
      setLayersTick((n) => n + 1)
    }
    if (!id) return
    let alive = true
    void api.getWritingFeedback(id).then((x) => {
      if (alive && currentRef.current?.id === id) setWritingFeedback(x)
    }).catch(() => undefined)
    void api.listChangeLayers(id)
      .then((saved) => new Promise<SavedLayer[]>((res) => setTimeout(() => res(saved), 320)))
      .then((saved) => {
        // Syncing the body into the editor is done by a child component's effect; wait a moment before restoring,
        // so coordinates aren't computed against the previous note's body. After waiting, check again that the same note is still open.
        const view = editorViewRef.current
        if (!alive || !view || currentRef.current?.id !== id) return
        if (saved.length) {
          const r = restoreLayers(saved, view.state.doc.toString())
          view.dispatch({ effects: restoreLayersEffect.of({ layers: r.layers, hunks: r.hunks, settled: r.settled }) })
          setPendingDiff(pendingHunks(view))
          setLayersTick((n) => n + 1)
          if (r.conflicts.length) {

            // each with two ways out: "recompute against the current text / drop this layer".
            const byId = new Map(saved.map((l) => [l.id, l]))
            const stuck = r.stuck.filter((s) => byId.has(s.id)).map((s) => ({ ...s, saved: byId.get(s.id)! }))
            // Write the ref on the spot too: the baseline line below must count them, and setState is async
            layerStuckRef.current = stuck
            setLayerStuck(stuck)
          }

          // it used to count `hunks ∪ settled`, so layers with **nothing live left** were also counted as
          // "1 layer left undisposed last time", while the "Changes" tab it pointed to didn't even appear then.
          const notice = reopenedLayersNotice(r)
          if (notice) toast(notice.text, notice.kind)
        }
        layersReady.current = id
        const view2 = editorViewRef.current
        if (view2) {
          layersSaved.current = {
            noteId: id,
            payload: [...serializeLayers(view2.state), ...layerStuckRef.current.map((s) => s.saved)]
              .map((l, i) => (l.seq === i ? l : { ...l, seq: i })),
          }
        }
        lastSettled.current = view2?.state.field(roundDiffField, false)?.settled
      })
      .catch(() => { layersReady.current = id })
    return () => { alive = false }
  }, [current?.id])


  //

  // yet **after closing and reopening the right pane had 0 cards** — round cards lived only in memory; the frontend read not one row.
  // The decision was **no new table, no persisting whole cards**; what's added is **the read-back path**
  // (zero migration / zero new tables / zero size growth), and **the missing details are honestly labeled on the card**
  // (listed item by item in the header of `util/roundsRestore`).
  //
  // ⚠️ **No live card may be covered** (the `mergeRestored` rule): the copy from this session's run,

  //    while what's read back is only a skeleton — **a skeleton must not cover the full version**.
  useEffect(() => {
    const id = current?.id
    if (!id) return
    let alive = true
    void api.listNoteRounds(id)
      .then((p) => {
        // After it returns, **check again that the same note is still open**: in these few hundred ms the user may have switched away
        // (same reason as the `listChangeLayers` path).
        if (!alive || currentRef.current?.id !== id) return
        const restored = restoredRounds(p)
        // An abnormal interruption has no RUN_FINISHED, so the live onDone never comes. Now the backend writes
        // the real stop reason into harness_runs.stopped; opening this note restores it under the Agent run
        // header. Shown only when there's no live card in memory, so an old request doesn't cover a freshly started run.
        const stopped = restoredStopStatus(p)
        if (stopped && !(roundsByNoteRef.current[id]?.length)) {
          setNoteHarnessStatus(stopped)
          setHarnessDone(true)
          harnessDoneRef.current = true
        }
        // When the first round's retrieval is interrupted there's only a run, no round: the reason is still stated above, but we must not
        // invent a nonexistent round card just to make the panel appear.
        if (!restored.length) return
        // **Goes through `writeRounds`** (not `setRoundsByNote` directly): there should be exactly 1 place touching that table
        // directly; one more would bypass "every write must name which note it's for" —
        // question ⑤ of `util/roundsWiring` pins exactly this, gated in `npm test`.
        writeRounds(id, (cur) => mergeRestored(cur, restored))
      })
      .catch(() => { /* couldn't read back means no cards, exactly as before — don't pop a message to bother the user */ })
    return () => { alive = false }
  }, [current?.id, writeRounds])


  const recomputeStuckLayer = useCallback((key: string) => {
    const view = editorViewRef.current
    const entry = layerStuckRef.current.find((s) => s.id === key)
    if (!view || !entry) return
    const doc = view.state.doc.toString()
    const all = [...serializeLayers(view.state), entry.saved]
    const r = restoreLayers(all, doc)
    view.dispatch({ effects: restoreLayersEffect.of({ layers: r.layers, hunks: r.hunks, settled: r.settled }) })
    setPendingDiff(pendingHunks(view))
    setLayersTick((n) => n + 1)
    const left = r.stuck.find((s) => s.id === key)
    if (left) {
      // **If it still doesn't match, say it still doesn't match**; don't pretend it worked — that's exactly the kind of false statement this batch fixes elsewhere.
      const next = layerStuckRef.current.map((s) => (s.id === key ? { ...s, why: left.why } : s))
      layerStuckRef.current = next
      setLayerStuck(next)
      toast(t('“{label}” still has {n} places that don’t match the current text: {why}', { label: entry.label, n: left.why.length, why: left.why.slice(0, 2).join('; ') }), 'error')
    } else {
      const next = layerStuckRef.current.filter((s) => s.id !== key)
      layerStuckRef.current = next
      setLayerStuck(next)
      toast(t('“{label}” was recomputed against the current text and is back in Changes', { label: entry.label }))
    }
    void flushChangeLayers()
  }, [flushChangeLayers])


  const dropStuckLayer = useCallback((key: string) => {
    const entry = layerStuckRef.current.find((s) => s.id === key)
    const next = layerStuckRef.current.filter((s) => s.id !== key)
    layerStuckRef.current = next
    setLayerStuck(next)
    setLayersTick((n) => n + 1)
    void flushChangeLayers()
    if (entry) toast(t('Dropped the layer “{label}” — the text was not touched', { label: entry.label }))
  }, [flushChangeLayers])

  // Cmd/Ctrl+S saves explicitly instead of falling through to the browser's
  // save-page dialog; Cmd/Ctrl+N starts a new note instead of opening a new
  // browser window -- power users expect both, autosave already makes S a
  // no-op when nothing's dirty so this can't double-save anything.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) return
      const key = e.key.toLowerCase()
      if (key === 's') { e.preventDefault(); void save() }
      else if (key === 'd' && e.shiftKey) { e.preventDefault(); void openToday() }   // ⌘⇧D today's journal (Trilium uses this key too)
      else if (key === 'n') { e.preventDefault(); void newNote() }
      else if (key === '.') { e.preventDefault(); setFocusMode((v) => !v) }
      // ⌘/ in the editor: CM's keymap already sent show-shortcuts (set true) and preventDefault, and the event keeps bubbling up here;

      else if (key === '/') { if (e.defaultPrevented) return; e.preventDefault(); setShowShortcuts((v) => !v) }
      // Collapse left/right pane. Trilium has no default keys; we use ⌘\ and ⌘⇧\
      else if (key === '\\' && e.shiftKey) { e.preventDefault(); setPanes((p) => (p.rightOn ? { ...p, rightOn: false } : makeRoomForRight(p, winW, split?.w ?? 0))) }
      else if (key === '\\') { e.preventDefault(); setPanes((p) => ({ ...p, leftOn: !p.leftOn })) }
      // ⌘/Ctrl+⇧+F one-key format. Shift is added so it doesn't clash with the browser's/editor's "Find"
      else if (key === 'f' && e.shiftKey) { e.preventDefault(); formatNote() }
      // ⌘F: when focus isn't in the editor (e.g. the tree was just clicked) CM's searchKeymap doesn't get it, so catch it here
      else if (key === 'f') { const v = editorViewRef.current; if (v && !v.hasFocus && current) { e.preventDefault(); openSearchPanel(v); v.focus() } }
      // Tabs: ⌘T new, ⌘W close current, ⌘1..9 jump to the n-th. Same as browsers,
      // nothing to learn. ⌘9 is **the last one** (not the ninth) — also a browser convention.
      else if (key === 't' && e.shiftKey) { e.preventDefault(); reopenLastTab() }
      else if (key === 't') { e.preventDefault(); void newNote() }
      // Back/forward: on macOS Trilium uses ⌘[ / ⌘] (Alt+←/→ are taken by tree promote/demote)
      else if (key === '[') { e.preventDefault(); goHistory(-1) }
      else if (key === ']') { e.preventDefault(); goHistory(1) }
      // ⌃Tab / ⌃⇧Tab cycle tabs (⌘Tab belongs to the system)
      else if (key === 'tab' && e.ctrlKey && tabs.length > 1) {
        e.preventDefault()
        const i = tabs.findIndex((t) => t.id === activeTabId)
        activateTab(tabs[(i + (e.shiftKey ? -1 : 1) + tabs.length) % tabs.length])
      }
      else if (key === 'w') {
        e.preventDefault()
        if (activeTabId) closeTab(activeTabId)
      } else if (/^[1-9]$/.test(key) && !e.altKey) {                  // ⌥⌘1/2/3 are headings (in the editor), not tab switches
        e.preventDefault()
        const i = key === '9' ? tabs.length - 1 : Number(key) - 1
        activateTab(tabs[i])
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, title, content, tabs, activeTabId, notes])

  /** Apply a batch of suggestions **directly to the body**, then mark them by diff for "Accept / Revert".
   *
   * These actions (polish/rewrite/expand) used to produce Revisions hung on the body as colored
   * highlights; **one click accepted directly, with no confirmation and no revert** — the only way to reject was not clicking, and it
   * would hang there forever; what it would change to was only visible in the native title tooltip; the RevisionPanel
   * component was never even rendered.
   *
   * Now it goes the same way as harness auto changes: apply first, mark green/red in the body, hover to
   * accept or revert, or tweak a few chars before accepting. Two interactions merged into one; users needn't remember two. */
  function applyAsDiff(list: Revision[], label = t('Revision')): number {
    if (!list.length) return 0
    // Read from the editor's live document, not liveContentRef — that one is maintained only while the harness
    // runs, and otherwise sits at the content from the end of the last round; using it as the base would treat everything the user typed
    // since as "changed by this suggestion". Don't read the content state either: this function runs after an await,
    // so content in the closure may be stale.
    const before = editorViewRef.current?.state.doc.toString() ?? content
    let next = before
    for (const r of list) next = applyRevision(next, r)
    if (next === before) return 0
    setContent(next)
    pushDiff(label, before, next)
    return list.length
  }


  function landRevisions(list: Revision[], note: string | undefined,
                         label: string, emptyNote: string, unparsed = false): void {
    if (list.length === 0) {
      toast(note || (unparsed ? unparsedEditNote(label) : emptyNote),
            (note || unparsed) ? 'error' : undefined)
      return
    }
    const { keep, bad } = splitBadRevisions(list)
    if (bad.length) toast(badRevisionNote(label, bad.length), 'error')
    if (keep.length === 0) return
    if (!applyAsDiff(keep, label)) toast(t('Suggestions don’t match the text (anchors not found); nothing changed.'))
  }

  async function handleSelectionAction(action: SelectionAction) {
    if (!selectionMenu) return
    const selection = selectionMenu.text
    if (action === 'custom') {
      // Shares the same input box and the same harness with `/`'s "Write with AI"; only the scope differs:
      // that one is "insert a block at the cursor", this one is "replace the selected passage with something else".
      // **Not via /api/rewrite** — that route only accepts the two fixed intents rewrite/polish.
      const view = editorViewRef.current
      const sel = view?.state.selection.main
      const at = { x: selectionMenu.x, y: selectionMenu.y }
      setSelectionMenu(null)
      if (!view || !sel || sel.empty) { toast(t('Nothing selected — select some text first, then right-click “Custom prompt”')); return }
      setSlash({
        item: { group: 'AI', key: 'custom', label: t('Custom prompt'), icon: 'bx-message-dots',
                hint: t('Do something with the selection'), needsPrompt: true,
                placeholder: t('e.g. rewrite for investors / split into three bullet points') },
        from: sel.from, to: sel.to, ...at,
      })
      return
    }
    if (!llmGate()) { setSelectionMenu(null); return }
    // Keep the menu open (showing a spinner via selectionBusy) instead of
    // closing it immediately -- otherwise a slow LLM call leaves no
    // indication anything is happening at the spot the user right-clicked.
    setSelectionBusy(action)

    const ctrl = new AbortController()
    selectionAbortRef.current = ctrl
    const signal = ctrl.signal
    try {
      if (action === 'verify') {
        const r = await api.verifySelection(content, selection, signal, intentText(intent), current?.id ?? '')

        // outside the tab system — it stays on tab switches and when the cursor moves to another paragraph, reading as if about the current one.
        setVerifyResult({ ...r, passage: selection })
      } else if (action === 'trace') {
        // Backstory: how the things in this passage evolved over time. **The user writes no question** —
        // the backend assembles the question (criterion 1). The result lands in the right pane's "Backstory" tab,
        // not a popover: criterion 2, looking at an old record shouldn't leave this page.
        await traceFull(selection, signal)
      } else if (action === 'expand') {
        const r = await api.expandSelection(content, selection, signal, intentText(intent), current?.id ?? '')
        landRevisions(r.revisions, r.note, t('Expand context'), t('The model saw no need for more context.'), r.unparsed)
      } else if (action === 'rewrite' || action === 'polish') {
        const r = await api.rewriteSelection(content, selection, action, spine, beats, signal, intentText(intent))
        landRevisions(r.revisions, r.note, action === 'polish' ? t('Polish selection') : t('Rewrite'), t('The model made no suggestions.'), r.unparsed)
      } else {

        const missed: never = action
        toast(t('The action “{action}” is not wired up yet', { action: String(missed) }), 'error')
      }
    } catch (e) {
      if ((e as Error).name === 'AbortError') toast(t('Stopped'))
      else if (isBackendDown(e)) toast(t('Action failed: {err}', { err: friendlyError(e) }), 'error')
      else if (isLlmUnreachable(e)) toastAction(t('Action failed: {err}', { err: friendlyError(e) }), t('Open Settings'), () => void openVirtual('app:settings', t('Settings')), 8000)
      else toast(t('Action failed: {err}', { err: friendlyError(e) }), 'error')
    } finally {
      selectionAbortRef.current = null
      setSelectionBusy(false)
      setSelectionMenu(null)
    }
  }

  /** Plain-text .md download -- markdown source is already the storage
   * format (see MarkdownEditor), so this is a straight file save, not an
   * export/conversion step. Deliberately no backend round-trip: portability
   * shouldn't depend on the server being reachable. */
  function exportMarkdown() {
    if (!current) return
    downloadMarkdown(title || t('Untitled'), content)
  }

  async function copyMarkdown() {
    if (!current) return
    try {
      await navigator.clipboard.writeText(content)
    } catch {
      toast(t('Copy failed; the browser may have denied clipboard access'), 'error')
    }
  }

  /** Leaving the current note (switching to another, creating a new one)
   * used to just call open()/createNote() directly -- if you did that within
   * the 1.5s autosave window, the debounce effect's cleanup cancelled the
   * pending save on its way out, and open() immediately overwrote
   * title/content with the new note's values. The edits were never sent to
   * the backend and never came back: silent data loss, no error, nothing to
   * undo. Every path that leaves the current note must flush first. */
  /** Where the current note was being viewed. Also recorded when the harness switches notes itself: the cursor then is where it wrote to,
   *  so coming back lands right where it last wrote. */
  function rememberSpot() {
    const v = editorViewRef.current
    const id = currentRef.current?.id
    if (!v || !id) return
    const scroller = document.querySelector('.note-scroll') as HTMLElement | null
    putSpot(spots.current, id, { head: v.state.selection.main.head, top: scroller?.scrollTop ?? 0 })
    saveSpots(api.getUser(), spots.current)
  }

  /** Restore cursor and scroll only after this note's body has actually entered the editor.
   *  An rAF directly in `open()` is too early: setContent hasn't been through React rendering yet and CM's doc is still the previous note's,
   *  so the dispatched selection gets pushed out by the new content arriving afterwards (measured: cursor back at 0). */
  const pendingSpot = useRef<string | null>(null)
  useEffect(() => {
    const id = pendingSpot.current
    const v = editorViewRef.current
    if (!id || current?.id !== id || !v || v.state.doc.length !== content.length) return
    pendingSpot.current = null
    const spot = spots.current.get(id)
    if (!spot) return
    v.dispatch({ selection: { anchor: Math.min(spot.head, v.state.doc.length) } })
    const scroller = document.querySelector('.note-scroll') as HTMLElement | null
    if (scroller && spot.top) requestAnimationFrame(() => { scroller.scrollTop = spot.top })
  }, [current?.id, content])

  async function switchTo(n: Note, viaHarness = false) {
    if (current?.id === n.id) return
    await save()
    await flushChangeLayers()
    // The note about to open is being edited in the split: flush the split's unsaved changes to the library first, then open with the latest body.
    // Otherwise the main pane opens with the old body, and 1.5 seconds later autosave overwrites the split's edits.
    if (split?.id === n.id && splitFlush.current) {
      await splitFlush.current()
      const fresh = await api.getNote(n.id).catch(() => null)
      if (fresh) n = fresh
    }
    const leaving = current
    rememberSpot()
    // Auto sync: a note changed but not yet synced is synced immediately on switching away (no waiting for the 2-minute debounce)
    if (leaving && autoSync && dirtySinceIngest.current === leaving.id && !job) {
      dirtySinceIngest.current = ''
      api.syncNoteToKb(leaving.id).then((r) => setJob(r.job_id)).catch(() => {})
    }
    open(n)
    void dropIfStillEmpty(leaving)
    // Manually clicking another note = clearly wanting to look at something else now; infinite continue keeps running in the background,
    // but no longer drags the editor back to the note being written — switches triggered by the harness itself aren't "manual",
    // and shouldn't turn follow off (otherwise every switch it makes would turn follow off, following only once).
    if (!viaHarness && harness?.running) setHarness((h) => (h ? { ...h, follow: false } : h))
  }

  // Autosave: persist 1.5 seconds after typing stops
  useEffect(() => {
    if (!current) return
    if (title === current.title && content === current.content) return
    const t = setTimeout(save, 1500)
    return () => clearTimeout(t)
  }, [title, content])  // eslint-disable-line react-hooks/exhaustive-deps

  // Background outline generation: regenerate only after an 8-second pause and at least 20 more chars changed since last generation —
  // the outline itself is required to "fill in parts obviously not yet written but that should be" (see prompts.py); running in
  // the background makes it a living outline that keeps predicting what to write next, no manual clicks.
  useEffect(() => {
    if (!current) return
    if (content.trim().length < SKELETON_MIN_CHARS) return
    if (content === lastSkeletonContent.current) return
    if (lastSkeletonContent.current
        && Math.abs(content.length - lastSkeletonContent.current.length) < SKELETON_MIN_DELTA) return
    const t = setTimeout(() => {
      if (loadingRef.current) return
      lastSkeletonContent.current = content
      void runSkeleton(true)
    }, SKELETON_IDLE_MS)
    return () => clearTimeout(t)
    // `loading` isn't read in the body, but it's a dep on purpose: if the
    // timer fires while something else is running, it backs off and does
    // nothing -- without `loading` here, nothing would ever re-run this
    // effect to give it another chance once that something else finishes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, current, loading])

  // "Smart edit" has been removed. It used to **automatically** run a revision suggestion whenever the user paused typing —
  // later it gained scoring diagnostics, so one auto trigger was two model calls, i.e. quietly burning money
  // in typing gaps. And its purpose is fully covered by "✨ Polish": the same revision loop, but with an explicit
  // stopping rule (until what's written meets the bar itself or can't be improved), and triggered by the user.
  // The "human in the loop picking item by item" entry exists now, but not via /api/edit — it's
  // "I decide each round": the harness stops after each round, you accept/revert each change in the editor,
  // and "Keep writing" sends the disposed body back to continue. So that one-shot call no longer needs
  // a frontend wrapper; the backend /api/edit still exists (with diagnostics and weakest-item rework); wiring it back
  // is three lines.


  /** Optimistic delete with an undo window instead of a confirm() dialog --
   * deletion used to be instant and permanent past a dialog people click
   * through by habit. The note is only actually deleted from the backend
   * after `ms` unless the toast's "Undo" is clicked first. */
  function remove(n: Note, ids: Set<string> = new Set([n.id])) {
    const wasCurrent = current?.id === n.id
    setNotes((prev) => prev.filter((x) => !ids.has(x.id)))
    setSearchResults((prev) => (prev ? prev.filter((x) => !ids.has(x.id)) : prev))
    // Remove it from the tree first (optimistic); undo makes reloadTree grow it back; without removing it we'd have to wait for the real delete
    // before refreshing the tree, leaving an already "deleted" note standing on the tree for 5 seconds.
    setTree((prev) => prev.filter((r) => !ids.has(r.note_id)))
    // Close its (and its subtree's) tabs and split too; don't leave a tab that does nothing when clicked
    closeTabsWhere((t) => ids.has(t.noteId))
    setSplit((sp) => (sp && ids.has(sp.id) ? null : sp))
    if (wasCurrent) {
      const remaining = notes.filter((x) => !ids.has(x.id))
      if (remaining.length) open(remaining[0])
      else { setCurrent(null); setTitle(''); setContent('') }
    }
    let undone = false
    const timer = setTimeout(() => {

      if (!undone) api.deleteNote(n.id).then(() => { void reloadTree(); void reload() }).catch((e) => { toast(t('Could not delete “{title}” — it is still in the database and will reappear after refresh: {err}', { title: displayTitle(n), err: friendlyError(e) }), 'error'); void reloadTree(); void reload() })
    }, 5000)
    toastAction(t('Deleted “{title}”{tail} (recoverable from Trash for 30 days)', { title: displayTitle(n), tail: ids.size > 1 ? t(' and the {n} notes under it', { n: ids.size - 1 }) : '' }), t('Undo'), () => {
      undone = true
      clearTimeout(timer)
      void reload(); void reloadTree()
      if (wasCurrent) open(n)
    })
  }

  async function togglePin(n: Note) {
    const updated = await api.togglePin(n.id)
    if (current?.id === n.id) setCurrent(updated)
    await reload()
  }

  // ---------------------------------------------------------------- AI actions

  /** Save the outline onto this note. A failed save doesn't interrupt the user — the outline is still fine in memory,
   * it just has to be regenerated next open; not worth an error popup. */
  async function persistSkeleton(s: string, b: string[], noteId?: string) {
    const id = noteId ?? current?.id
    if (!id) return
    try {
      await api.saveSkeleton(id, s, b)
      setNotes((prev) => prev.map((x) => (x.id === id ? { ...x, spine: s, beats: b } : x)))
    } catch { /* never mind if it can't be saved; it's still in memory */ }
  }

  async function runSkeleton(background = false) {
    // **Only `background === true` is background**: `onClick={onRun}` used to pass the mouse event as background,

    const quiet = background === true
    const why = notePrecondition('skeleton', content, title)
    if (why) { if (!quiet) toast(why); return }             // no request: same sentence as the backend
    if (!quiet && !llmGate()) return
    setLoading('skeleton')
    const ctrl = new AbortController()
    skeletonAbortRef.current = ctrl
    try {
      const r = await api.genSkeleton(title, content, intentText(intent), ctrl.signal)
      setSpine(r.spine)
      setBeats(r.beats)
      setSkeletonNotes(r.notes ?? [])
      await persistSkeleton(r.spine, r.beats)
    } catch (e) {
      // Failures of background auto-runs don't bother anyone (the user clicked nothing); only a failed "Generate outline" click shows a hint
      if ((e as Error).name === 'AbortError') { if (!quiet) toast(t('Outline generation stopped')); return }
      if (quiet) void api.clientLog('warn', 'Background outline generation failed: ' + friendlyError(e), '', 'skeleton')
      else if (isLlmUnreachable(e)) toastAction(t('Outline generation failed: {err}', { err: friendlyError(e) }), t('Open Settings'), () => void openVirtual('app:settings', t('Settings')), 8000)
      else toast(t('Outline generation failed: {err}', { err: friendlyError(e) }), 'error')
    } finally {
      skeletonAbortRef.current = null
      setLoading('')
    }
  }
  /** "Stop" outline generation: drop the request, reset the button. The backend call still runs to its timeout, but the UI is no longer held by it. */
  function stopSkeleton() { skeletonAbortRef.current?.abort() }

  /** magic tap: streaming continue, written into the editor as it arrives. Click again to interrupt. */
  async function runMagicTap() {
    if (loading === 'tap') {

      abortRef.current?.abort()
      toast(t('Continue stopped; what was written stays — use “Revert” in the text if you don’t want it'))
      return
    }
    // Not a single char and the title is empty too: the model could only make things up. Ask the user for a direction first
    { const why = notePrecondition('tap', content, title); if (why) { toast(why); return } }   // same sentence as the backend
    if (!llmGate()) return
    setLoading('tap')
    setTapMeta(null)
    setTapNotes([])
    const ctrl = new AbortController()
    abortRef.current = ctrl
    // **Continue from the cursor** (Notion / Craft's "Continue writing" both work at the cursor). Cursor at the end or
    // never entered the editor → append; in the middle → send what's after the cursor to the model as the "following text",
    // and insert the written paragraph at the cursor. If the cursor sits mid-paragraph, first move back to that paragraph's end — forcing
    // a paragraph into the middle of a sentence isn't what anyone wants.
    const view = editorViewRef.current
    const docLen = view?.state.doc.length ?? content.length
    let at = view?.hasFocus || (view && view.state.selection.main.head > 0) ? view!.state.selection.main.head : docLen
    if (at > 0 && at < docLen) {
      const text = view!.state.doc.toString()
      const nextBreak = text.indexOf('\n\n', at)
      at = nextBreak < 0 ? docLen : nextBreak
    }
    const middle = at > 0 && at < docLen
    const full = view ? view.state.doc.toString() : content
    const before = middle ? full.slice(0, at) : full
    const following = middle ? full.slice(at) : ''
    // **Don't compute positions in setContent's updater**: streaming calls the updater once per chunk, and if the cursor in the closure

    // Fix head and tail, the middle only grows; compute the whole note directly per chunk.
    const head = middle ? before.replace(/\n*$/, '\n\n') : (before && !/\n\n$/.test(before) ? before.replace(/\n?$/, '\n\n') : before)
    const tail = middle ? following.replace(/^\n*/, '\n\n') : ''
    let inserted = ''
    try {
      const { truncated, fakeCitations } = await api.magicTap(
        before,
        spine,
        beats,
        setTapMeta,
        (piece) => {
          inserted += piece
          setContent(head + inserted + tail)

          requestAnimationFrame(() => {
            const v = editorViewRef.current
            if (v) v.dispatch({ effects: EditorView.scrollIntoView(Math.min(head.length + inserted.length, v.state.doc.length)) })
          })
        },
        ctrl.signal,
        // Deterministic check after writing: retrieved materials but used none of them means this passage is
        // generic content. magic tap deliberately doesn't use the full loop (it's meant to produce a paragraph in seconds with one click),
        // so here we neither interrupt nor rewrite; just a hint so the user decides whether to redo.
        (g) => { if (g.hint) toast(g.hint, 'error'); setTapNotes(g.notes ?? []) },
        following,
        title,
        intentText(intent),
        current?.id ?? '',
      )
      // After the stream ends, fix "**Title:**"-style bold once (the backend persist path has the same step; continue is assembled purely client-side)
      let fixed = fixBoldPunct(inserted)


      if (fakeCitations.length) {
        for (const fid of fakeCitations) fixed = fixed.replace(new RegExp('\\s*\\[' + fid.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\]', 'g'), '')
        toast(t('Removed {n} citations not found in the knowledge base', { n: fakeCitations.length }))
      }
      if (fixed !== inserted) { inserted = fixed; setContent(head + inserted + tail) }
      // ⌘Z undoes the whole passage: while the editor is read-only (`loading === 'tap'`), every chunk streamed in is merged into one undo event


      if (inserted.trim()) pushDiff(t('Continue'), full, head + inserted + tail)

      // **Now that sentence has somewhere to go**: revert is right there in the body; no more relying on the user's own ⌘Z.
      if (truncated) toast(t('This passage hit the length limit and one follow-up still didn’t finish it — use “Revert” in the text, or put the cursor at the end and click again'), 'error')
    } catch (e) {
      if ((e as Error).name !== 'AbortError') { if (isLlmUnreachable(e)) toastAction(t('Continue failed: {err}', { err: friendlyError(e) }), t('Open Settings'), () => void openVirtual('app:settings', t('Settings')), 8000); else toast(t('Continue failed: {err}', { err: friendlyError(e) }), 'error') }
    } finally {
      setLoading('')
      abortRef.current = null
    }
  }

  /** This note → a slides note (pain point 6).
   *
   *  **No multi-round loop**: slides are a one-shot restructure; multiple rounds only fragment the pages more. When done, take
   *  the user straight to that child note — the output is a note, so it should be seen like opening a note.
   *  Failing criteria don't block persisting; a hint says so, and the user decides whether to redo. */
  async function runSlides(style: 'points' | 'talk') {
    if (!current) return
    { const why = notePrecondition('slides', content); if (why) { toast(why); return } }
    if (!llmGate()) return
    setLoading('slides')
    slidesText.current = ''; setSlidePhase('')
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      await save()
      const r = await api.makeSlides(current.id, content, current.title, style,

        (delta) => {
          slidesText.current += delta
          const pages = (slidesText.current.match(/\n---/g) ?? []).length
          setSlidePhase(t('Making slides… page {n}', { n: pages + 1 }))
        },
        ctrl.signal)
      window.dispatchEvent(new CustomEvent('notes-changed'))
      await reload(); await reloadTree()
      if (r.note_id) {
        const n = await api.getNote(r.note_id)
        await switchTo(n)
      }
      const bad = r.notes.length
      toast(bad ? t('{pages} pages · {pct}% of pages cite sources · {bad} things to improve: {note}', { pages: r.pages, pct: Math.round(r.cite_coverage * 100), bad, note: r.notes[0] })
                : t('{pages} pages · {pct}% of pages cite sources', { pages: r.pages, pct: Math.round(r.cite_coverage * 100) }),
            bad ? 'error' : undefined)
    } catch (e) {
      if ((e as Error).name === 'AbortError') toast(t('Slide generation stopped'))
      else toast(t('Slide generation failed: {err}', { err: friendlyError(e) }), 'error')
    } finally { setLoading(''); setSlidePhase(''); abortRef.current = null }
  }

  /** Slides → PDF. The HTML is assembled here (`util/slideHtml`); printing is handed to the main process —
   *  `window.print()` in the renderer prints **this current window**, dragging the editor's DOM
   *  in; the main process opens an offscreen window, completely unrelated to what's being edited. */
  async function exportSlidesPdf() {
    if (!current) return
    try {
      // Render ```mermaid to SVG first and inline it: the print step runs in an offscreen window with JS disabled.
      // What can't be rendered prints as source; don't block the export — one diagram failing to render shouldn't fail the whole PDF.
      const svgs = new Map<string, string>()
      for (const b of parseMini(content)) {
        if (b.kind !== 'pre' || b.lang !== 'mermaid') continue
        const svg = await mermaidSvg(b.text.trim())
        if (svg) svgs.set(b.text.trim(), svg)
      }
      const where = await window.memoketDesktop?.slidesToPdf?.(
        slidesToHtml(current.title, content, svgs), displayTitle(current))
      if (where) toast(t('Saved to: {where}', { where }))
    } catch (e) { toast(t('PDF export failed: {err}', { err: friendlyError(e) }), 'error') }
  }

  /** Smart Continue: a harness within a single note — automatic revision (no waiting for manual accept) + automatic
   * continuation alternating, until the content is complete relative to spine/beats. Revisions are applied to local
   * content with the same applyRevision() anchor semantics as RevisionPanel's manual accept, and continuation increments are appended directly,
   * so in effect the editor shows it "editing itself" in real time.
   * Uses currentRef rather than the closure's `current` to decide whether to apply — if the user switches to another note
   * mid-run, this note's revisions/continuation must not be misapplied to the other note now being
   * shown. */
  /** Patch a round's record. Events arrive scattered (round-start / tool-calls /
   * evaluate / policy, one each); whichever arrives first builds this round's empty shell, later ones fill it in. */

  function emptyRound(round: number): AgentRound {
    return {
      round, cleanupOnly: false, revisions: 0, toolCalls: [], toolTruncated: false,
      scores: {}, status: '', weakest: null, policyReasons: [], policy: null, errors: [], dropped: [],
    }
  }

  function patchRound(noteId: string, round: number, patch: Partial<AgentRound>) {
    writeRounds(noteId, (rs) => {
      const i = rs.findIndex((r) => r.round === round)
      if (i < 0) {
        return [...rs, { ...emptyRound(round), ...patch }]
      }
      const next = [...rs]
      next[i] = { ...next[i], ...patch }
      return next
    })
  }

  /** Event handling for this run. **Starting and "Keep writing" share the same one** — if the two paths each had
   * their own, a resumed run would be missing a few handlers, and that's the hardest kind of
   * difference to spot: the UI looks like it's running, just some panel stops updating. */
  function noteHarnessHandlers(noteId: string, mode: 'write' | 'polish'): api.NoteHarnessHandlers {

    const noteName = (fallback = t('another note')) => {
      const n = notesRef.current.find((x) => x.id === noteId)
      return n ? displayTitle(n) : fallback
    }
    const awayToast = (detail: string) =>
      toast(t('“{name}”: {detail}', { name: noteName(), detail }))
    const h: api.NoteHarnessHandlers = {
      onSkeleton: (s, b, notes) => {

        // `persistSkeleton(s, b, noteId)` **persists by noteId** (`api.saveSkeleton(id, …)`
        // then updates that row in `notes` by id), never touching "the note currently shown".

        // **no switch → the library's `spine` becomes non-zero at second 8; switch 262 ms after clicking → watched 60 seconds and it stayed 0,
        // 0 after the run, still 0 after close and reopen.** And this is the only path in the whole repo that writes an outline generated mid-run into the note
        // (the sole call site of `store.set_skeleton` is `PUT /api/notes/<id>/skeleton`),
        // ⇒ blocking it = **the outline generated this time is lost forever**, and the next open needs another model call.
        void persistSkeleton(s, b, noteId)
        // ── Everything below is for **the note currently shown** (the right pane's three cells + status line) ──
        // This half **is still blocked**: putting A's outline into B's right pane after switching away is exactly what that cut was meant to block.
        if (currentRef.current?.id !== noteId) return
        setSpine(s); setBeats(b); setSkeletonNotes(notes ?? [])
        setNoteHarnessStatus(t('Outline generated automatically; starting round 1'))
      },
      onRoundStart: (d) => {


        // skipped_continue: last round's scoring said repetition is currently the weakest item, so this round
        // the backend skips continuation and only runs one more focused revision; no delta events

        // not "continuing", or the user would think it's stuck; nor should it reserve a blank line for continuation,
        // because this round will never have content to fill it.
        patchRound(noteId, d.round, {
          cleanupOnly: !!d.skipped_continue,
          revisions: d.revisions_applied,
          // "Why this round runs this way" (backend plan 12.1): what the last round diagnosed,
          // whether it entered this round's retrieval plan, how many code criteria this mode has in total,
          // and how many retrieval shots the depth gate dropped.
          steer: d.steer ?? '',
          steerDim: d.steer_dim ?? '',
          steerMaterial: !!d.steer_material,
          // **`undefined` and `false` are not the same**, so no `?? false`:
          // the former means "this round had no retrieval-planning step at all".
          steerInPlan: d.steer_in_plan,
          checksTotal: d.checks_total,
          depthDropped: d.depth_dropped ?? 0,
          depthDroppedAll: !!d.depth_dropped_all,

          factsIrrelevant: d.facts_irrelevant ?? 0,
          irrelevantDropped: !!d.irrelevant_dropped,
          irrelevantSample: d.irrelevant_sample ?? [],

          // means "this backend version doesn't have these three keys yet", `0` means "computed, and not one citable sentence",
          // two completely different sentences on the panel (see `citeCoverLine`).
          citeLocated: d.cite_located,
          citeMarked: d.cite_marked,
          citeMatched: d.cite_matched,
    })

        if (currentRef.current?.id !== noteId) return

        // **Added before reserving the blank line** — that blank line is also inserted by this round and shouldn't remain after ⌘Z.
        setUndoGroup((g) => g + 1)
        if (d.skipped_continue) {
          setNoteHarnessStatus(t('Round {n}: {m} revisions applied, cleaning up duplicates…', { n: d.round, m: d.revisions_applied }))
          return
    }
        // The knowledge base is empty (the most common case for new users): **say it once**. It used to be that
        // "nothing found this round" and "the library is empty altogether" looked identical in the UI; the user only saw

        setNoteHarnessStatus(d.round === 1 && d.kb_empty
          ? t('Round 1: the knowledge base is still empty, so this run can only build on what you have written — import materials and Continue will cite your own records. continuing…')
          : t('Round {n}: {m} revisions applied, continuing…', { n: d.round, m: d.revisions_applied }))
        insertCursorRef.current = null
        // Continuation increments only start arriving after this — the locally accumulated content must get a separator
        // first, same reasoning as the backend's prompts.join_round_text()

        // missed here before; only the folder-harness side had been fixed.
        {
          const c = liveContentRef.current
          const next = c ? c.replace(/\n*$/, '') + '\n\n' : c
          liveContentRef.current = next
          setContent(next)
        }
      },
      onRevision: (r) => {
        if (currentRef.current?.id !== noteId) return
        // Compute from liveContentRef, not an updater (same as onDelta): the updater waits for React's next tick,
        // while the deltas right behind it in the same event batch were already joined onto the old ref; the updater then overwrites the ref with a "revisions without increments" version,

        // After applying, squeeze blank lines like the server does (the server runs tidy_blank_lines after each revision), otherwise the three blank lines a delete leaves differ between the two sides
        const next = tidyBlankLines(applyRevision(liveContentRef.current, { id: '', op: r.op as Revision['op'], anchor: r.anchor, anchor_end: r.anchor_end, text: r.text, reason: r.reason, sources: r.sources ?? [] }))
        // Local replay changed no characters = the anchor wasn't located: record it, so the end-of-round "off by N chars" has an explanation
        if (next === liveContentRef.current) void api.clientLog('warn', `revision no-op (${r.op}): anchor ${JSON.stringify((r.anchor ?? '').slice(0, 50))}`, '', 'harness-sync')
        liveContentRef.current = next
        setContent(next)

        // the full record, one sentence in the status line is enough
        setNoteHarnessStatus(r.op === 'delete' ? t('Auto-deleted one place: {reason}', { reason: r.reason.slice(0, 50) }) : t('Auto-revised one place: {reason}', { reason: r.reason.slice(0, 50) }))
      },
      onInsertAt: (d) => {
        if (currentRef.current?.id !== noteId) return
        // Recompute the landing point against the local body (it may have just applied revisions and differ from the server by a few chars);
        // use the backend's pos only if the heading can't be found. Take back the blank line reserved for appending at round start.
        {
          const base = liveContentRef.current.replace(/\n+$/, '\n')
          const pos = sectionEnd(base, d.section) ?? Math.min(d.pos, base.length)
          // The make-room rule follows the server's outline.insert_into (editor/streamJoin.prepareInsert, cross-checked by check-stream-parity)
          const r = prepareInsert(base, pos)
          insertCursorRef.current = r.cursor
          liveContentRef.current = r.next
          setContent(r.next)
        }
        setNoteHarnessStatus((s) => (s.endsWith(t('continuing…')) ? s.slice(0, -t('continuing…').length) + t('writing the section “{section}”…', { section: d.section }) : s))
        requestAnimationFrame(() => {
          const view = editorViewRef.current
          if (view && insertCursorRef.current != null) view.dispatch({ effects: EditorView.scrollIntoView(Math.min(insertCursorRef.current, view.state.doc.length), { y: 'center' }) })
        })
      },
      onDelta: (text) => {
        // Also stream into the Agent run panel. After going two-phase the editor sits completely still for tens of seconds
        // (retrieval planning isn't streaming); seeing the written text live in the panel is far more useful than a single
        // waiting status line.
        //


        // versus 2 for the no-switch control.
        writeRounds(noteId, (rs) => {
          if (!rs.length) return rs
          const next = [...rs]
          const last = next[next.length - 1]
          next[next.length - 1] = { ...last, streamed: (last.streamed ?? '') + text }
          return next
    })
        // ── Bookkeeping ends here; below **touches the body** (not one char may change after switching away) ──
        if (currentRef.current?.id !== noteId) return
        {
          // Compute from liveContentRef, not an updater: if the updater's execution timing doesn't line up with the cursor in the closure
          // it drifts (observed on the magic tap side)

          // off by 2–4 chars per round) — the rule is in editor/streamJoin.ts, with unit tests
          const r = insertStreamed(liveContentRef.current, insertCursorRef.current, text)
          if (insertCursorRef.current != null) insertCursorRef.current = r.cursor
          const next = r.next
          liveContentRef.current = next
          setContent(next)
        }
      },
      onTextEnd: () => {
        if (currentRef.current?.id !== noteId) return
        // At the end of server-side continuation fix_bold_punct runs on the whole note (**x:** → **x**:); do the same pass locally (editor/format.fixBoldPunct, cross-checked by check-scrub-parity), otherwise end-of-round alignment reports char differences
        const next = fixBoldPunct(liveContentRef.current)
        if (next !== liveContentRef.current) { liveContentRef.current = next; setContent(next) }
      },
      onRoundEnd: (_round, serverContent) => {
        if (currentRef.current?.id !== noteId) return
        // Align with the server's body at the end of this round. Client-side replay of revisions by anchor drifts
        // (citations mangled, inconsistent separators); the server's is the truth.
        if (typeof serverContent === 'string' && serverContent && serverContent !== liveContentRef.current) {
          // Log it: how far the locally replayed body differs from the server's. A big difference means the client's replay logic
          // drifted again — this is evidence of "does the agent output match the editor", not a feeling.


          // strips it, while the separator reserved by local onInsertAt stayed) — still use the server's, but don't log it as drift with warn
          const local = liveContentRef.current
          if (local.replace(/\s+$/, '') !== serverContent.replace(/\s+$/, '')) {
            let at = 0
            while (at < local.length && at < serverContent.length && local[at] === serverContent[at]) at++
            const win = (t: string) => JSON.stringify(t.slice(Math.max(0, at - 20), at + 20))
            void api.clientLog('warn', `round ${_round}: local body ${local.length} chars vs server ${serverContent.length} chars, used the server's; first difference at ${at}: local ${win(local)} / server ${win(serverContent)}`, '', 'harness-sync')
          }
          liveContentRef.current = serverContent
          setContent(serverContent)
        }
        // At end of round, word-diff the snapshot against the current body to mark this round's additions and deletions.
        // Revisions are applied automatically (no waiting for manual accept); unmarked, the user wouldn't know at all
        // where the body was touched.
        // At the end of every round, recompute from **the start of the whole run**; highlights are cumulative:
        // decorations get cleared by the next round's doc changes, but are recomputed at the end of the next round,
        // and the range only grows.
        const base = runBaseRef.current
        const cur = liveContentRef.current
        // A difference only in leading/trailing whitespace (the blank line reserved for continuation at round start, model didn't answer) isn't a change — otherwise with the model unreachable

        if (base && cur && base.replace(/\s+$/, '') !== cur.replace(/\s+$/, '')) pushDiff(t('Smart Continue'), base, cur, true)
      },
      onEvaluate: (d) => {

        writeRounds(noteId, (rs) => {
          if (!rs.length) return rs
          const next = [...rs]
          next[next.length - 1] = {
            ...next[next.length - 1],
            scores: d.scores, status: d.status, weakest: d.weakest,

            judgeHallucinated: d.judge_hallucinated ?? [],
          }
          return next
    })
        // ── Bookkeeping ends here; below **touches the current note's right pane / status line** ──
        if (currentRef.current?.id !== noteId) return
        const beatScore = d.scores['beat_coverage']
        if (beatScore) setBeatCoverage(beatScore)
        if (d.status === 'continue' && d.weakest) {
          setNoteHarnessStatus(t('This round’s score: {dim} is still weak; next round focuses on it', { dim: d.weakest }))
    }
      },
      onPhase: (d) => {

        // Use patchRound rather than changing "the last card": the revision pass runs

        // changing the last card directly would drop that whole passage — and it's exactly the first passage people most want to see.
        patchRound(noteId, d.round, { phase: d.phase, phaseLabel: d.label })
      },
      onPhaseDelta: (d) => {

        writeRounds(noteId, (rs) => {
          const i = rs.findIndex((r) => r.round === d.round)
          const base = i < 0 ? null : rs[i]
          const pt = { ...(base?.phaseText ?? {}) }
          const cur = pt[d.phase] ?? { thinking: '', output: '' }
          pt[d.phase] = d.kind === 'thinking'
            ? { ...cur, thinking: cur.thinking + d.text }
            : { ...cur, output: cur.output + d.text }
          if (i < 0) {
            return [...rs, {
              round: d.round, cleanupOnly: false, revisions: 0, toolCalls: [],
              toolTruncated: false, scores: {}, status: '', weakest: null,
              policyReasons: [], policy: null, errors: [], dropped: [], phaseText: pt,
            }]
          }
          const next = [...rs]
          next[i] = { ...base!, phaseText: pt }
          return next
    })
      },
      onToolCalls: (d) => {

        patchRound(noteId, d.round, { toolCalls: d.calls, toolTruncated: d.truncated })
        if (currentRef.current?.id !== noteId) return
        setNoteHarnessStatus(t('Round {n}: the agent searched the knowledge base {m} times, continuing…', { n: d.round, m: d.calls.length }))
      },
      onPolicy: (d) => {



        patchRound(noteId, Math.max(1, d.round), { policyReasons: d.reasons, policy: d.policy })
      },
      onScrub: ({ sentence }) => {

        // Never mind if not found — the server's body at round end will align it back
        if (currentRef.current?.id !== noteId || !sentence) return
        const c = liveContentRef.current
        const at = c.indexOf(sentence)

        if (at < 0) { void api.clientLog('warn', `scrub miss: ${JSON.stringify(sentence.slice(0, 60))}`, '', 'harness-sync'); return }
        // Rules copied from the server (other sentences in the same paragraph get stripped too), see editor/streamJoin.applyScrub
        const next = tidyBlankLines(applyScrub(c, sentence))
        if (next === c) void api.clientLog('warn', `scrub no-op: ${JSON.stringify(sentence.slice(0, 60))}`, '', 'harness-sync')
        if (insertCursorRef.current != null && insertCursorRef.current > at) insertCursorRef.current = Math.max(at, insertCursorRef.current - (c.length - next.length))
        liveContentRef.current = next
        setContent(next)
      },
      onDedup: ({ paragraph }) => {
        // Paragraphs / lines the server stripped before landing in the body (duplicates, headings the model wrote itself): delete locally too — they already streamed into the editor
        if (currentRef.current?.id !== noteId || !paragraph) return
        const c = liveContentRef.current
        const at = c.indexOf(paragraph)
        if (at < 0) { void api.clientLog('warn', `dedup miss: ${JSON.stringify(paragraph.slice(0, 60))}`, '', 'harness-sync'); return }
        const next = tidyBlankLines(c.slice(0, at) + c.slice(at + paragraph.length))
        if (insertCursorRef.current != null && insertCursorRef.current > at) insertCursorRef.current = Math.max(at, insertCursorRef.current - (c.length - next.length))
        liveContentRef.current = next
        setContent(next)
      },
      onDropped: (detail) => {
        // A guard dropping a revision isn't an error; it goes into a separate collapsible area, not the error red.

        writeRounds(noteId, (rs) => {
          if (!rs.length) return rs
          const next = [...rs]
          next[next.length - 1] = {
            ...next[next.length - 1],
            dropped: [...next[next.length - 1].dropped, detail],
          }
          return next
    })
      },
      onSkills: (d) => {



        patchRound(noteId, d.round, { skills: { scope: d.scope, injected: d.injected, menu: d.menu } })
      },
      onCheckHit: (d) => {
        // A code criterion failed on the spot, so this round won't spend a model call on scoring. Without marking it
        // the user sees a 0 score, not knowing who judged it or why this round was so fast.
        // Ones with `stuck_rounds` are a different matter: this one has been stuck for several rounds unable to change, the backend has
        // let it through and scored as usual; this must be said clearly, otherwise "reported an error yet gave a score" looks contradictory.
        //
        // **Accumulate a list, not keep the last one** (plan 12.1): within a round several "stuck, let through" ones
        // may arrive first and the short-circuit one last; the later one used to overwrite the earlier
        // — the criterion really fired, and the user couldn't see it.
        //

        // `stuckCheckRef` is the sole source of `onDone`'s "fired N rounds in a row", and `onDone`
        // runs even after switching away — blocking here would cut that wrap-up sentence in half. The blanket guard is removed.
        if (d.stopped) stuckCheckRef.current = { check: d.check || '', rounds: d.stuck_rounds || 0 }
        writeRounds(noteId, (rs) => {
          if (!rs.length) return rs
          const next = [...rs]
          const last = next[next.length - 1]
          next[next.length - 1] = withCheckHit(last, d)
          return next
        })
      },
      onCost: (d) => {
        // Per-run cost cap (backend plan 12.3). **Stop and tell the user, not a silent cut** —
        // without a word, the user only sees "why did this run only do two rounds".
        //

        // and the `onDone(reason='cost_cap')` right after it only says "finished" in the switched-away branch,
        // **losing the reason half** (verbatim: "Smart Continue for “X” finished; the content is saved in that note").
        // The tokens spent are the user's money; "why only two rounds" shouldn't go unsaid just because they switched tabs.
        if (currentRef.current?.id !== noteId) { awayToast(d.detail); return }
        toast(d.detail, 'error')
      },
      onCrossRun: (d) => {
        // This run came out worse than the previous one (backend plan 9.3). **Report only, no rollback**: the previous body is in
        // "Revision history"; whether to go back is the user's decision, not ours.
        //

        // this sentence gives **a next action** ("the previous body is in 'Revision history'; go back any time"),
        // and "Revision history" is **a per-note right pane**. Not naming = sending the user to browse **the wrong note's** revision history.
        // ⇒ This one either names the note or doesn't pop; **passing it through unchanged is the worst of the three**.
        if (currentRef.current?.id !== noteId) { awayToast(d.detail); return }
        toast(d.detail, 'error')
      },
      onWarning: (d) => {
        // A middleware threw. The loop keeps running (the isolation benefit of capability packaging), but this round
        // lacks that capability — the backend comment says "must not be silent", yet before this the frontend didn't handle
        // this event at all, and every warning sent was dropped.
        //

        // Written by noteId, **before its own guard**: this cell should stay even after switching away
        // — it's **this note's bookkeeping for this round**, not about "the note on screen now".

        // ⚠️ **Must not be written as `if (!rs.length) return rs`** (the shape of `onError` / `onDropped`):
        //    those two always happen **within** some round, while **the earliest of these arrives before the run starts**
        //    — `hooks.skeleton` is run by the router **before** `loop.run`
        //    (the header of `middleware/cost.py` says so verbatim), and at that moment **there isn't a single card yet**.
        //    Observed on the real shell: that red toast popped at 412 ms, while the card's cell **appeared nowhere**
        //    — "recorded" and "recorded somewhere visible" are two different things.

        //    `patchRound(noteId, 1, …)` **merges into the same card** by round number, and the cell stays.

        //    it's exactly the capability missing before this round started.)
        writeRounds(noteId, (rs) => {
          const next = rs.length ? [...rs] : [emptyRound(1)]
          next[next.length - 1] = {
            ...next[next.length - 1],
            warnings: [...(next[next.length - 1].warnings ?? []),
              { middleware: d.middleware, hook: d.hook, error: d.error }],
          }
          return next
        })
        // ── Below belongs to **the note shown now** (that red toast) ──────────────────────

        //  · **The run keeps going and the user can't do anything at this moment** — `onCost` / `onCrossRun` each
        //    offer one thing (money ran out / go browse revision history); this one has nothing to offer.
        //  · **There can be several per round**: in `loop._wrap` **every hook of every middleware**
        //    sends one when it throws, and `hooks/note.py` alone has two kinds at the skeleton spot (generation failed / stored one is half a sentence).
        //    Popping several unactionable red messages after switching away is noise, not notification.
        // ⇒ **Whether to pop** and **whether to record** are two things: this batch only added the recording half.

        //   switching back (or never switching away) it's visible on the card, **without popping a red message elsewhere**.
        if (currentRef.current?.id !== noteId) return
        toast(warningLine({ middleware: d.middleware, hook: d.hook, error: d.error }), 'error')
      },
      onError: (detail) => {

        // written by noteId; the card should keep that red passage even after switching away.
        writeRounds(noteId, (rs) => {
          if (!rs.length) return rs
          const next = [...rs]
          next[next.length - 1] = {
            ...next[next.length - 1],
            errors: [...next[next.length - 1].errors, detail],
          }
          return next
    })
        // ── Everything below belongs to **the note shown now** (status line / toast / the "finished" switch) ──
        if (currentRef.current?.id !== noteId) return

        // the round card had a red passage while the status stayed at "Writing…", with no toast and no "stopped". Say it all here.
        setHarnessDone(true); harnessDoneRef.current = true
        setNoteHarnessStatus(t('{mode} stopped on an error: {detail}', { mode: mode === 'polish' ? t('Polish') : t('Smart Continue'), detail }))
        if (/\u8fde\u4e0d\u4e0a|\u62d2\u7edd|\u8fd4\u56de \d{3}|\u6ca1\u5e94\u7b54|unreachable|refused|returned \d{3}|no response|connect/i.test(detail)) toastAction(t('{mode} stopped on an error: {detail}', { mode: mode === 'polish' ? t('Polish') : t('Smart Continue'), detail }), t('Open Settings'), () => void openVirtual('app:settings', t('Settings')), 8000)   // connection-type errors (zh: "can't connect" / "refused" / "returned NNN" / "no response", or the English equivalents)
        else toast(t('{mode} stopped on an error: {detail}', { mode: mode === 'polish' ? t('Polish') : t('Smart Continue'), detail }), 'error')
      },
      onDone: (reason, blockedReason, runId, serverContent) => {
        // **The user has already switched to another note**: this note's result must never be written into the note shown now —

        // and autosave would then save A's content into B. Just a hint; the body is saved by the server.
        if (currentRef.current?.id !== noteId) {
          toast(t('{mode} on “{name}” has finished; the content is saved in that note', { name: noteName(), mode: mode === 'polish' ? t('Polish') : t('Smart Continue') }))
          return
        }
        // On finishing (or pausing) also align with the server's body — see onRoundEnd
        if (typeof serverContent === 'string' && serverContent && serverContent !== liveContentRef.current) {
          liveContentRef.current = serverContent
          setContent(serverContent)
        }

        writeRounds(noteId, (rs) => rs.map((r) => (r.phaseLabel ? { ...r, phase: undefined, phaseLabel: undefined } : r)))
        if (reason === 'awaiting_review' && runId) {
          // This round is written, waiting for your disposition. **The body's final form is decided by the editor** —
          // per-change accept/revert all happens here, and "Keep writing" sends the current body back.
          pausedRef.current = true
          setPausedRun({ id: runId, noteId, mode })
          setNoteHarnessStatus(t('This round is done; review each change, then click “Keep writing”'))
          return
    }
        const label = reason === 'no_more_changes' ? t('Nothing left to improve; polish finished')
          : reason === 'complete' ? (mode === 'polish' ? t('Everything written meets the bar; polish complete') : t('Content is complete; stopped automatically'))
          : reason === 'open_handoff' ? t('This round made progress and handed back to you; open issues are kept, and the note was not declared finished for you')
          : reason === 'needs_input' ? t('Draft saved, but not finished yet: {why}', { why: blockedReason || t('there are still empty sections or missing materials') })
          : reason === 'blocked' ? t('Stuck and needs your attention: {why}', { why: blockedReason || t('unknown reason') })


          : reason === 'stalled' ? t('No further improvement this time: two rounds of revisions in a row did not land; the current draft is saved')
          : reason === 'regressed' ? t('Further edits made it worse; restored and saved the best round')
          : reason === 'cost_cap' ? t('Cost cap reached; the best round is saved. Narrow the task and continue')
          : reason === 'material_used_up' ? t('Not enough material to continue; the current draft is saved. Add materials or narrow the task')
          : reason === 'no_actionable_revision' ? t('Scoring pointed to no locatable sentence; stopped spinning and saved the current draft. The diagnosis is kept in the run details')

          // "Which one, how many rounds" comes from the check_hit event carrying stopped, sent before wrap-up.
          : reason === 'check_stuck' ? (stuckCheckRef.current

              // other criteria firing several rounds in a row mean the content isn't there yet; the next step is "take a look yourself", not "switch models".
              ? t('Stopped forcing it: in the last 4 rounds, “{check}” failed {n} times. The best draft of this run is saved{tail}', { check: checkLabel(stuckCheckRef.current.check), n: stuckCheckRef.current.rounds, tail: stuckTail(stuckCheckRef.current.check) })
              : t('Stopped forcing it: the same clear problem kept failing over recent rounds. The best draft of this run is saved; see the run details for specifics'))

          // "reached the round limit" would make users think a few more rounds would help, while this rule says exactly the opposite:
          // it's been measured; continuing won't get better (`modes.BEST_STALL_ROUNDS`).
          : reason === 'best_stalled' ? t('Stopped forcing it: none of the last 4 rounds scored higher. The best draft of this run is saved; the run details list what still falls short')
          : t('Round limit reached without meeting the bar; the best draft is saved. Check the unfinished items in the plan')
        stuckCheckRef.current = null
        const delta = liveContentRef.current.length - runBaseRef.current.length
        const summary = `${label} · ${t('{n} rounds', { n: (roundsByNoteRef.current[noteId]?.length ?? 0) || 1 })} · ${delta === 0 ? t('text unchanged') : t('{n} chars', { n: `${delta > 0 ? '+' : ''}${delta}` })}`
        setNoteHarnessStatus(summary)
        harnessDoneRef.current = true
        setHarnessDone(true)
        // These are the quality loop's normal convergence exits, and the result already stays in the editor; another red toast
        // would only make users think the run errored. Real errors, blocks and successful completion still notify immediately.
        const inlineOnly = ['check_stuck', 'max_rounds', 'best_stalled', 'material_used_up', 'no_actionable_revision', 'stalled', 'needs_input', 'open_handoff'].includes(reason)
        if (!inlineOnly) toast(t('Smart Continue: {label}', { label }), reason === 'blocked' ? 'error' : undefined)
        notifyIfHidden(t('MEMOKET NOTE · Smart Continue'), t('{name}: {label}', { name: noteName(t('Notes')), label }))
      },
    }
    // **One guard layer for all**: the run belongs to note noteId; after the user switches away, the handlers that **touch the body / editor**
    // must not touch the note shown now — before, only half the handlers wrote this check themselves, and the missing half

    //



    // versus 2 without switching). So now **each key is checked against the `util/harnessGuard` table**:
    // those with a by-noteId bookkeeping part are let through (they put their bookkeeping lines before their own guard),
    // those that record nothing are still blocked. **Keys not in the table are always blocked** (the conservative side),
    // and "added a new one, forgot to classify it" turns a gate red on the spot (`scripts/check-harness-guard.mts`: set equality).
    //

    // (`guardBlocks('onDone')` already returns false since it's in the `self` tier),
    // and in this batch the `self` tier grew from 1 to 3 (`onDone` / `onCost` / `onCrossRun`:
    // all three **judge cross-note themselves** and say one **named** sentence after switching away);
    // keeping that hardcoded key name would read as "only onDone is an exception" — **not what the table says**.
    const guarded: api.NoteHarnessHandlers = {}
    for (const [k, fn] of Object.entries(h) as [keyof api.NoteHarnessHandlers, (...a: unknown[]) => void][]) {
      guarded[k] = ((...args: unknown[]) => {
        if (guardBlocks(k) && currentRef.current?.id !== noteId) return
        fn(...args)
      }) as never
    }
    return guarded
  }
  async function runNoteHarness(mode: 'write' | 'polish' = 'write', override?: { content: string; intent: DocIntent }) {
    const runContent = override?.content ?? content
    const runIntent = override?.intent ?? intent
    if (loading === 'note-harness') {
      // When "Stop" is clicked, **force-reset the state at the same time**; don't just abort and count on fetch's
      // finally to reset it — really hit this: after a backend restart cut the SSE connection, the frontend's
      // reader.read() hung without returning, finally never ran, and loading stayed stuck at
      // 'note-harness'. Hence a deadlock: clicking the button again thought it was still running, came here,
      // aborted an already-dead request and returned; nothing happened, and the user could only
      // refresh the page to continue.
      abortRef.current?.abort()
      abortRef.current = null
      setLoading('')
      setNoteHarnessStatus(t('You stopped Smart Continue; progress so far is saved'))
      setHarnessDone(true)
      harnessDoneRef.current = true
      toast(t('Smart Continue stopped; what was written stays — revert the whole layer from Changes in the right pane'))
      return
    }
    if (!current) return
    { const why = notePrecondition(mode === 'polish' ? 'polish' : 'harness', runContent, title); if (why) { toast(why); return } }
    if (mode === 'write' && needsHarnessGoal(runIntent)) {
      setWorkflowPicker({ resume: true, focus: 'goal' })
      setNoteHarnessStatus(t('Pick a writing mode in the editor first, or fill in a custom writing task'))
      return
    }
    if (!llmGate()) return
    const noteId = current.id
    // The per-change accepts / reverts the user just made must be persisted first, so the backend can carry them into this round's writing and scoring.
    await flushChangeLayers()

    // "running on another note"; without this log we could only guess.
    void api.clientLog('info', `harness start note=${noteId} title=${current.title.slice(0, 20)} content=${runContent.length} spine=${spine.slice(0, 30)} beats=${beats.length}`, '', 'harness-start')
    setLoading('note-harness'); setNoteHarnessNoteId(noteId)
    setNoteHarnessStatus(t('Starting…'))
    setHarnessDone(false); harnessDoneRef.current = false
    setBeatCoverage(null)
    writeRounds(noteId, () => [])
    setRoundDiff(null)
    setPausedRun(null)
    pausedRef.current = false
    liveContentRef.current = runContent
    runBaseRef.current = runContent
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      await api.runNoteHarness(
        noteId, runContent, spine, beats,
        noteHarnessHandlers(noteId, mode),
        ctrl.signal,
        mode,
        reviewEachRound,
        intentText(runIntent),
      )
    } catch (e) {
      if ((e as Error).name !== 'AbortError') toast(
        t('{mode} failed: {err}', { mode: mode === 'polish' ? t('Polish') : t('Smart Continue'), err: friendlyError(e) }), 'error')
    } finally {
      setLoading(''); setNoteHarnessNoteId(null)
      // Must not clear while stopped at "waiting for your disposition" — that hint was just set in onDone; clearing it would mean
      // two buttons appearing out of nowhere with no explanation.
      if (!pausedRef.current && !harnessDoneRef.current) setNoteHarnessStatus('')
      abortRef.current = null
      void reload()
      // reload() replaces the document with the server's body, and docChanged clears the decorations — after the run
      // they must be added once more, otherwise the user ends up seeing nothing (this is the second reason "only the first
      // time had green").
      const base = runBaseRef.current
      const cur = liveContentRef.current
      if (base && cur && base !== cur) pushDiff(t('Smart Continue'), base, cur, true)
    }
  }

  function acceptRevision(r: Revision) {
    setContent((c) => applyRevision(c, r))
    setRevisions((rs) => rs.filter((x) => x.id !== r.id))
  }

  /** Manually push the current note into the knowledge base. Not wired to
   * autosave: autosave fires every 1.5s of idle typing, so tying ingestion
   * to it would re-ingest the whole note repeatedly while the user is still
   * writing -- wasting LLM calls and producing a pile of near-duplicate
   * facts. */
  /** Sync: the server reads this note's latest body, deletes the old session and re-extracts. Like ingest it's a background job, same status bar / toast. */
  async function syncNoteToKb(noteId: string) {
    if (job) return                                    // only one at a time
    try {
      await save()
      const r = await api.syncNoteToKb(noteId)
      setJob(r.job_id)
    } catch (e) {
      toast(t('Sync failed: {err}', { err: friendlyError(e) }), 'error')
    }
  }

  // Auto sync: if enabled in Settings, an ingested note is synced once after 2 minutes without further edits; synced immediately on switching away.
  // Each sync is an extraction call, so it's off by default and debounced.
  const [autoSync, setAutoSync] = useState(false)
  useEffect(() => {
    const load = () => api.getProviderConfig().then((c) => setAutoSync(!!c.auto_sync_notes)).catch(() => {})
    void load()
    const onProv = () => { void load() }
    window.addEventListener('provider-changed', onProv)
    return () => window.removeEventListener('provider-changed', onProv)
  }, [])
  const autoSyncTimer = useRef<number | null>(null)
  const dirtySinceIngest = useRef<string>('')          // which note was changed and not yet synced
  useEffect(() => {
    if (!autoSync || !current?.ingested_at) return
    if (content === current.content) return           // unchanged
    dirtySinceIngest.current = current.id
    if (autoSyncTimer.current) window.clearTimeout(autoSyncTimer.current)
    const id = current.id
    autoSyncTimer.current = window.setTimeout(() => {
      if (dirtySinceIngest.current === id && currentRef.current?.id === id) {
        dirtySinceIngest.current = ''
        void syncNoteToKb(id)
      }
    }, 120_000)
    return () => { if (autoSyncTimer.current) window.clearTimeout(autoSyncTimer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, autoSync, current?.id])

  async function ingestCurrentNote() {
    { const why = notePrecondition('ingest', content); if (why) { toast(why); return } }

    if (job || loading === 'ingest') { toast(t('This note is being saved to the knowledge base; wait for it to finish')); return }
    setLoading('ingest')
    try {
      const r = await api.ingestText(content, title || t('Untitled'), 'note', current?.id ?? '')
      setJob(r.job_id)
    } catch (e) {
      toast(t('Could not save to knowledge base: {err}', { err: friendlyError(e) }), 'error')
    } finally {
      setLoading('')
    }
  }

  /** Delete unfindable citations from the body: through CM changes (undoable, same path as typing); without an editor, change content directly */
  function stripCitationIds(ids: string[]) {
    if (!ids.length) return
    const view = editorViewRef.current
    if (view) {
      const ranges = citationRanges(view.state.doc.toString(), ids)
      if (ranges.length) view.dispatch({ changes: ranges.map((r) => ({ from: r.from, to: r.to, insert: '' })) })
      toast(t('Removed {n} citations', { n: ranges.length }))
      return
    }
    setContent((c) => {
      const ranges = citationRanges(c, ids)
      let out = c
      for (const r of [...ranges].reverse()) out = out.slice(0, r.from) + out.slice(r.to)
      return out
    })
  }

  /** Turn `[title](note://id)` links to deleted notes into plain text: same path as stripCitationIds */
  function unlinkNotes(ids: string[]) {
    if (!ids.length) return
    const view = editorViewRef.current
    if (view) {
      const ranges = noteLinkRanges(view.state.doc.toString(), ids)
      if (ranges.length) view.dispatch({ changes: ranges })
      toast(t('Turned {n} links into plain text', { n: ranges.length }))
      return
    }
    setContent((c) => {
      let out = c
      for (const r of [...noteLinkRanges(c, ids)].reverse()) out = out.slice(0, r.from) + r.insert + out.slice(r.to)
      return out
    })
  }

  function insertAtCursor(text: string) {
    if (!text) return
    const view = editorViewRef.current
    if (!view) {
      setContent((c) => c + text)
      return
    }
    const { from, to } = view.state.selection.main
    // dispatch's own updateListener already calls onChange -> setContent,
    // same path a keystroke takes -- no need to also setContent here.
    view.dispatch({ changes: { from, to, insert: text }, selection: { anchor: from + text.length } })
  }

  /** Symmetric with exportMarkdown(): bring a .md file in as a real editable
   * note (not knowledge-base extraction -- that's the separate "Save to knowledge base"
   * / batch import path). Migrating content in from Obsidian/Notion exports etc.
   * shouldn't require re-typing it. */
  /** Import .md: one file is one note; **multiple files produce a subtree** — an "Import <date>"
   *  parent node with each file as a child. Dozens of notes scattered at the tree root can't be tidied up. */
  async function importMarkdown(files: FileList | null, under: string = api.ROOT_ID) {
    const list = Array.from(files ?? []).filter((f) => /\.(md|markdown|txt)$/i.test(f.name))
    if (list.length === 0) { if (files?.length) toast(t('Only .md / .markdown / .txt are accepted — none of the selected files match')); return }
    await save()

    try { await importMarkdownFiles(list, under) }
    catch (e) { toast(t('Import failed: {err}', { err: friendlyError(e) }), 'error'); void reload(); void reloadTree() }
  }

  async function importMarkdownFiles(list: File[], under: string) {
    const strip = (name: string) => name.replace(/\.(md|markdown|txt)$/i, '')

    const toTray = async (notes: { id: string; title: string; content: string }[]) => {
      const target = trayTargetRef.current
      if (!trayByDefault() || !target) return
      try {
        const k = await landNotesInTray(target, notes)
        if (k) toast(t('{n} imported notes added to materials; AI will draw on them when writing this note', { n: k }))
      } catch (e) { toast(t('Could not add to materials: {err}', { err: friendlyError(e) }), 'error') }
    }
    if (list.length === 1) {
      const text = await list[0].text()
      const n = await api.createNote(strip(list[0].name), text, under)
      await reload(); await reloadTree()
      await toTray([{ id: n.id, title: n.title, content: text }])
      open(n); return
    }
    const parent = await api.createNote(t('Import {date}', { date: fmtDate(new Date().toISOString()) }), t('Imported from {n} files.', { n: list.length }), under)
    void api.setNoteIcon(parent.id, 'bx-import').catch(() => {})     // the imported batch hangs under a node with an "Import" icon
    let first: Note | null = null
    const made: { id: string; title: string; content: string }[] = []
    for (const f of list) {
      const text = await f.text()
      const n = await api.createNote(strip(f.name), text, parent.id)
      made.push({ id: n.id, title: n.title, content: text })
      first ??= n
    }
    await reload(); await reloadTree()
    toast(t('Imported {n} notes under “{title}”', { n: list.length, title: parent.title }))
    await toTray(made)
    open(first ?? parent)
  }

  /** Full backstory (model, about 20 seconds): both the context menu and the ⌥ hover card's "Full backstory" go through here; the result is in the right pane's "Backstory".
   *  **The user writes no question** — the backend assembles it (criterion 1); the result isn't a popover (criterion 2). */
  async function traceFull(text: string, signal?: AbortSignal) {
    const noteId = currentRef.current?.id
    if (!noteId) return
    const r = await api.traceMemory(text, 10, signal)
    // Switched from note A to note B during the query: a late response must not pin A's backstory onto B's right pane.
    if (currentRef.current?.id !== noteId) return



    // and the user still can't tell. It uses the same `verifyScopeLine`: one rule, so the two places can't say different things.
    setTrace({ noteId, answer: r.answer, facts: r.facts, recalled: r.recalled ?? null, at: new Date().toISOString(), passage: text })

    setPaneFocus({ id: 'trace', n: Date.now() })
  }
  async function traceFromCard(phrase: string) {
    if (!llmGate()) return
    toast(t('Tracing the full story of “{phrase}”, about 20 seconds; results appear in Trace on the right', { phrase }))
    try { await traceFull(phrase) } catch (e) { toast(t('Could not trace: {err}', { err: friendlyError(e) }), 'error') }
  }


  async function restoreBeforeRound(r: RunRound) {
    if (!current) return
    setLoading('rounds')
    try {
      const n = await api.restoreRevision(current.id, r.before.id)
      setCurrent(n); setTitle(n.title); setContent(n.content); liveContentRef.current = n.content
      void reload()
      setRunsTick((t) => t + 1)
      toast(t('Back to before round {n} (a version of the text from before was kept too)', { n: r.round_no }))
    } catch (e) { toast(t('Could not go back: {err}', { err: friendlyError(e) }), 'error') }
    finally { setLoading('') }
  }

  async function undoRoundOnly(r: RunRound) {
    if (!current || !r.after) return
    setLoading('rounds')
    try {

      const [before, after, ...later] = await Promise.all([r.before, r.after, ...r.later].map((x) => api.getRevision(current.id, x.id)))
      // Read from the editor's live document (same as applyAsDiff): after the await, content in the closure may be stale
      const cur = editorViewRef.current?.state.doc.toString() ?? content
      const res = undoRound(before.content, after.content, cur, later.map((x) => x.content))
      if (res.undone === 0) {
        toast(t('None of the {total} edits from round {n} match the current text; nothing changed. {conflict}', { n: r.round_no, total: res.total, conflict: res.conflicts[0] ?? '' }), 'error')
        return
      }
      setContent(res.text)
      pushDiff(t('Undo round {n}', { n: r.round_no }), cur, res.text)
      if (res.conflicts.length) toast(t('Undid {undone} edits from round {n}; {bad} didn’t match and were left: {list}', { n: r.round_no, undone: res.undone, bad: res.conflicts.length, list: res.conflicts.join('; ') }), 'error')
      else toast(t('Undid {undone} edits from round {n}, other rounds kept; if wrong, revert this layer in Changes', { n: r.round_no, undone: res.undone }))
    } catch (e) { toast(t('Could not undo: {err}', { err: friendlyError(e) }), 'error') }
    finally { setLoading('') }
  }


  function acceptAllDiff() {
    const view = editorViewRef.current
    // First hand the per-change verdicts to the backend as-is, then burn the remaining pending. Otherwise "revert one, then immediately accept all"
    // would record that revert as an accept before the debounced persist.
    const decided = view ? serializeLayers(view.state) : []
    view?.dispatch({ effects: acceptAllHunks.of(null) })
    layerStuckRef.current = []
    setLayerStuck([])
    const id = currentRef.current?.id
    if (!id) return
    layersSaved.current = { noteId: id, payload: [] }     // the library is empty already; don't send another empty list
    void api.saveChangeLayers(id, decided, true)
      .then(() => api.burnChangeLayers(id, true))
      .then(() => api.getWritingFeedback(id))
      .then((x) => { if (currentRef.current?.id === id) setWritingFeedback(x) })
      .catch(() => { layersSaved.current = { noteId: '', payload: [] } })
  }

  /** Revert all: restore everything this round changed.
   *
   * **Revert from back to front** — each revert changes the document length; front to back, the positions of later
   * hunks would all be off. Per-change revert doesn't need this (after each dispatch the remaining hunks are
   * mapped along), but a batch in one go must guarantee the order itself. */
  function rejectAllDiff() {
    const view = editorViewRef.current
    if (!view) return
    const hunks = [...(view.state.field(roundDiffField, false)?.hunks ?? [])]
      .sort((a, b) => b.from - a.from)
    if (!hunks.length) return
    for (const h of hunks) {
      if (h.off) { view.dispatch({ effects: dropHunk.of(h.id) }); continue }   // a layer that's off: the body is already the original
      view.dispatch({ changes: { from: h.from, to: h.to, insert: h.del },
                      effects: dropHunk.of(h.id) })
    }
  }

  /** Continue after disposing, or stop here.
   *
   * What's sent back is **the editor's current body**: per-change accept/revert all happens in the editor; having the backend
   * merge a list of hunk ids again would be two implementations of the same merge, while what the user actually sees is
   * the copy in the browser.
   */
  async function resumePausedRun(stop = false) {
    const run = pausedRun
    const view = editorViewRef.current
    if (!run || !view) return
    const kept = view.state.doc.toString()
    setPausedRun(null)
    if (stop) {
      try {
        await api.stopHarness(run.id, kept)
        // Use a toast, not the status line: at this moment pausedRun is already cleared and loading is '',
        // so neither render condition of the status line holds; writing there, nobody would see it.
        setNoteHarnessStatus('')
        toast(t('Wrapped up using the text as you reviewed it'))
      } catch (e) {
        toast(t('Wrap-up failed: {err}', { err: friendlyError(e) }), 'error')
      }
      setLoading('')
      return
    }
    setLoading('note-harness'); setNoteHarnessNoteId(run.noteId)
    setNoteHarnessStatus(t('Keep writing…'))
    runBaseRef.current = kept
    liveContentRef.current = kept
    setRoundDiff(null)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      await api.resumeHarness(
        run.id, kept, noteHarnessHandlers(run.noteId, run.mode), ctrl.signal)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') toast(t('Keep writing failed: {err}', { err: friendlyError(e) }), 'error')
    } finally {
      abortRef.current = null
      setLoading(''); setNoteHarnessNoteId(null)
    }
  }

  /** One-key format of the whole note.
   *
   * **Pure rules, no model** (see editor/format.ts): formatting has clear rules;
   * handing it to a model only gives different results each time, and might change content on the side.
   *
   * The result goes to "Accept / Revert" by diff — re-laying out the whole note is a big change, the user must be able to inspect each spot
   * and also revert everything with one click. */
  function formatNote() {
    const view = editorViewRef.current
    if (!view) return
    const before = view.state.doc.toString()
    const after = formatMarkdown(before)
    if (after === before) { toast(t('Already well formatted; nothing to change')); return }
    // Replace only the part that really changed: replacing the whole note drags the cursor and viewport to the end (same path as external updates)
    const change = minimalChange(before, after)
    if (change) view.dispatch({ changes: change })
    setContent(after)
    pushDiff(t('Formatting'), before, after)
    toast(t('Formatted: {n} characters changed (blank lines / spaces / table alignment)', { n: Math.abs(after.length - before.length) }))
  }

  /** Smart layout. **Complementary** to one-key format:
   *
   * · Format (pure rules) can only normalize structure **already marked** — add spaces, align tables,
   *   add blank lines between blocks. It can't tell "this line should be a heading".
   * · Smart layout makes exactly that semantic judgment, but **the model only outputs "turn line N into which structure"**,
   *   and the original text is moved line by line by the backend, so content can't be changed.
   *
   * After layout, format runs once more so the output is still normalized; the result goes to "Accept / Revert" by diff. */
  async function restructureNote() {
    const view = editorViewRef.current
    if (!view || !current) return
    const before = view.state.doc.toString()

    { const why = notePrecondition('restructure', before); if (why) { toast(why); return } }
    if (!llmGate()) return

    setLoading('restructure')
    const ctrl = new AbortController()
    restructureAbortRef.current = ctrl
    try {
      const r = await api.restructureNote(current.id, title, before, intentText(intent), ctrl.signal)
      if (r.detail) toast(r.detail, 'error')
      if (!r.changed) { toast(r.detail ? t('No changes') : t('The structure is already clear; nothing to adjust')); return }
      const after = formatMarkdown(r.content)
      const v = editorViewRef.current
      if (!v) return
      // The user can still type during these seconds of waiting for the model (layout doesn't lock the editor like the harness). Positions computed by minimalChange

      if (v.state.doc.toString() !== before) {
        toast(t('The text changed during layout, so this result was not applied — finish editing and click “Smart layout” again'), 'error')
        return
      }
      // Replace only the changed part: replacing the whole note would map all earlier proposal layers' positions to a single point, emptying the ledger
      const change = minimalChange(before, after)
      if (change) v.dispatch({ changes: change })
      setContent(after)
      pushDiff(t('Smart layout'), before, after)
      const skipped = r.skipped.length ? t(', skipped {n}', { n: r.skipped.length }) : ''
      toast(t('Adjusted {n} structural places{skipped}; accept or revert each one', { n: r.ops, skipped }))
    } catch (e) {
      if ((e as Error).name === 'AbortError') toast(t('Smart layout stopped; text untouched'))
      else toast(t('Layout failed: {err}', { err: friendlyError(e) }), 'error')
    } finally {
      restructureAbortRef.current = null
      setLoading('')
    }
  }
  function stopRestructure() { restructureAbortRef.current?.abort() }

  /** Entry after an item is chosen in `/`. Items needing a prompt show an input box first; the rest finish on the spot. */
  /** The right-pane tray's "Write from tray": the same thing as that `/` menu item — open the same input box at the cursor (may be left empty) */
  function writeFromTray() {
    const view = editorViewRef.current
    const item = SLASH_ITEMS.find((i) => i.key === 'tray')
    if (!view || !current || !item) return
    const at = view.state.selection.main.head
    const coords = view.coordsAtPos(at)
    view.focus()
    setSlash({ item, from: at, to: at, x: coords?.left ?? 200, y: (coords?.bottom ?? 200) + 6 })
  }

  function applyWritingWorkflow(id: WritingTemplateId, resume: boolean) {
    const view = editorViewRef.current
    if (!view) return
    const template = writingTemplate(id)
    const doc = view.state.doc.toString()
    const scaffold = missingTemplateScaffold(template, doc)
    let nextContent = doc
    if (scaffold) {
      const from = view.state.selection.main.head
      const before = view.state.doc.sliceString(0, from)
      const after = view.state.doc.sliceString(from)
      const inserted = templateTextAt({ ...template, scaffold }, before, after)
      const scaffoldAt = inserted.indexOf(scaffold)
      const firstBody = scaffold.indexOf('\n\n') + 2
      view.dispatch({
        changes: { from, to: from, insert: inserted },
        selection: { anchor: from + scaffoldAt + Math.max(0, firstBody) },
      })
      nextContent = view.state.doc.toString()
    }
    const nextIntent: DocIntent = { ...template.intent, source: 'user', checked: [] }
    saveIntent(nextIntent)
    setWorkflowPicker(null)
    setNoteHarnessStatus(scaffold
      ? t('Enabled {template}: added missing structure and loaded the sourcing, writing and acceptance rules', { template: t(template.label) })
      : t('Enabled {template}: structure already complete; loaded the sourcing, writing and acceptance rules', { template: t(template.label) }))
    if (resume) void runNoteHarness('write', { content: nextContent, intent: nextIntent })
    view.focus()
  }

  function applyCustomWritingTask(task: Pick<DocIntent, 'goal' | 'reader' | 'done'>, resume: boolean) {
    const nextIntent: DocIntent = { ...task, workflow: '', source: 'user', checked: [] }
    saveIntent(nextIntent)
    setWorkflowPicker(null)
    setNoteHarnessStatus(t('Using a custom writing task; the workflow will follow the goal, audience and completion criteria'))
    if (resume) void runNoteHarness('write', { content: editorViewRef.current?.state.doc.toString() ?? content, intent: nextIntent })
    editorViewRef.current?.focus()
  }

  function onSlash(item: SlashItem, from: number, to: number, resumeHarness = false) {
    const view = editorViewRef.current
    const coords = view?.coordsAtPos(from)
    const at = { x: coords?.left ?? 200, y: (coords?.bottom ?? 200) + 6 }
    if (item.needsPrompt) { setSlash({ item, from, to, ...at, resumeHarness }); return }
    if (item.key === 'table-image' || item.key === 'audio') {
      pickKind.current = item.key === 'audio' ? 'audio' : 'image'
      setSlash({ item, from, to, ...at })
      filePick.current?.click()
      return
    }
    if (item.key === 'voice') {
      setSlash(null)
      // When the voice service is offline, don't let the user record a whole passage only to find it can't be transcribed: say so before recording
      if (asrOffline) { toast(t('Voice service unreachable ({offline}); transcription is unavailable, everything else works', { offline: asrOffline }), 'error'); return }
      void runVoice(from, to); return
    }
    // The rest (chart / eda) need no prompt; run directly
    setSlash({ item, from, to, ...at })
    void runBlock(item, from, to, '')
  }

  /** Voice input: record a passage, transcribe, insert the text at the `/` position.
   *
   * Uses a separate MediaRecorder rather than reusing the right-hand AudioRecorder component — that one's
   * output goes to "insert into editor" or "save to knowledge base", a permanent panel feature; this one is "insert a passage at
   * the cursor position", and only this place has the position. State goes through a placeholder block, consistent with other AI actions. */
  async function runVoice(from: number, to: number) {
    const view = editorViewRef.current
    if (!view) return

    // it used to be that `/` → voice input while recording started **a second MediaRecorder** — two placeholder blocks,
    // two microphone tracks, two passages each transcribed and inserted into the body separately, while "Stop" could only stop its own one.
    // The check guards **whether something is recording** (`voiceStopById`), not some button's disabled state:

    if (voiceStopById.current.size > 0) {
      toast(t('Already recording — stop the “Recording” block in the text before recording another'), 'error')
      return
    }
    const id = Math.random().toString(36).slice(2, 10)
    const push = (fx: StateEffect<unknown>) => editorViewRef.current?.dispatch({ effects: fx })
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      toast(micError(e), 'error')
      return
    }
    const chunks: Blob[] = []
    const mr = new MediaRecorder(stream)
    mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
    voiceStopById.current.set(id, () => { if (mr.state !== 'inactive') mr.stop() })
    view.dispatch({
      changes: { from, to, insert: '' },
      effects: startRun.of({ id, from, label: t('Voice input') }),
    })
    push(patchRun.of({ id, phase: t('Recording; click Stop to finish') }))
    mr.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop())
      voiceStopById.current.delete(id)
      push(patchRun.of({ id, phase: t('Transcribing…') }))

      const ctrl = new AbortController()
      runAborts.current.set(id, ctrl)
      try {
        const r = await api.transcribeOnly(new Blob(chunks, { type: 'audio/webm' }), 'recording.webm', ctrl.signal)
        if (ctrl.signal.aborted) return
        const text = (r.text || '').trim()
        if (!text) {
          push(patchRun.of({ id, error: t('Nothing was heard; no transcript produced'), expanded: true }))
          return
        }
        const v = editorViewRef.current
        if (!v) return
        const run = v.state.field(runsField, false)?.find((x) => x.id === id)
        const at = Math.max(0, Math.min(run?.from ?? from, v.state.doc.length))
        const before = v.state.doc.toString()
        v.dispatch({ changes: { from: at, insert: text }, effects: endRun.of(id) })
        const after = v.state.doc.toString()
        setContent(after)
        pushDiff(t('Voice input'), before, after)
      } catch (e) {
        if ((e as Error).name === 'AbortError') { toast(t('Stopped; this recording was not transcribed')); return }
        push(patchRun.of({
          id, error: t('Transcription failed: {err}', { err: friendlyError(e) }), expanded: true,
        }))
      } finally {
        runAborts.current.delete(id)
      }
    }
    mr.start()
  }

  /** After picking a file: images go to "recognize the table in it", audio to "insert + auto transcribe".
   *
   * Neither is "insert only" — the `/` menu holds only AI features; pure insertion is in the top toolbar.
   * State likewise goes through the placeholder block at the cursor, consistent with other AI actions. */
  async function onPickFile(files: FileList | null) {
    const f = files?.[0]
    const ctx = slash
    setSlash(null)
    const view = editorViewRef.current
    if (!f || !ctx || !view) return
    const id = Math.random().toString(36).slice(2, 10)
    const push = (fx: StateEffect<unknown>) => editorViewRef.current?.dispatch({ effects: fx })
    view.dispatch({
      changes: { from: ctx.from, to: ctx.to, insert: '' },
      effects: startRun.of({ id, from: ctx.from, label: ctx.item.label }),
    })
    const at = () => {
      const v = editorViewRef.current!
      const r = v.state.field(runsField, false)?.find((x) => x.id === id)
      return Math.max(0, Math.min(r?.from ?? ctx.from, v.state.doc.length))
    }
    try {
      if (ctx.item.key === 'table-image') {
        push(patchRun.of({ id, phase: t('Checking the image for a table…') }))

        const ctrl = new AbortController()
        runAborts.current.set(id, ctrl)
        let r: Awaited<ReturnType<typeof api.tableFromImage>>
        try { r = await api.tableFromImage(f, ctrl.signal) } finally { runAborts.current.delete(id) }
        if (ctrl.signal.aborted) return
        if (!r.detected) {
          // Honestly say nothing was detected; **don't force an empty table into the user's note**
          push(patchRun.of({
            id, expanded: true,
            error: t('No table detected') + (r.raw ? t(' (model said: {raw})', { raw: r.raw.slice(0, 40) }) : ''),
          }))
          return
        }
        const v = editorViewRef.current!
        const before = v.state.doc.toString()
        v.dispatch({ changes: { from: at(), insert: `\n${r.table}\n\n` }, effects: endRun.of(id) })
        const after = v.state.doc.toString()
        setContent(after)
        pushDiff(t('Image to table'), before, after)       // recognition results can be accepted/reverted too
        return
      }
      // Audio: upload first, **insert the player into the body first**, then transcribe the text.

      // was uploaded but not inserted into the note, and the error pointed to "LLM provider". The player doesn't need the voice service, so land it first;
      // transcription is a bonus, and failure only says transcription didn't work. When the voice service is known unreachable, the transcription request isn't even sent.
      push(patchRun.of({ id, phase: t('Uploading…') }))
      const a = await api.uploadAsset(f)
      push(logRun.of({ id, at: t('Uploaded'), text: t('{name} ({kb}KB)', { name: a.name, kb: Math.round(a.bytes / 1024) }) }))
      const v = editorViewRef.current!
      const before = v.state.doc.toString()
      const player = `\n<audio controls src="${a.url}"></audio>\n\n`
      v.dispatch({ changes: { from: at(), insert: player } })
      setContent(v.state.doc.toString())
      if (asrOffline) {
        push(patchRun.of({ id, expanded: true, error: t('Audio inserted; voice service unreachable ({offline}), so it was not transcribed — check the voice service address in Settings', { offline: asrOffline }) }))
        pushDiff(t('Insert audio'), before, v.state.doc.toString())
        return
      }
      push(patchRun.of({ id, phase: t('Transcribing…') }))
      let text = ''

      const tctrl = new AbortController()
      runAborts.current.set(id, tctrl)
      try {
        text = ((await api.transcribeOnly(f, f.name, tctrl.signal)).text || '').trim()
      } catch (e) {
        if ((e as Error).name === 'AbortError') { pushDiff(t('Insert audio'), before, editorViewRef.current!.state.doc.toString()); toast(t('Transcription stopped; the audio stays in the text')); return }
        push(patchRun.of({ id, expanded: true, error: t('Audio inserted, but transcription failed: {err}', { err: friendlyError(e) }) }))
        pushDiff(t('Insert audio'), before, editorViewRef.current!.state.doc.toString())
        return
      } finally {
        runAborts.current.delete(id)
      }
      const v2 = editorViewRef.current!
      v2.dispatch({ changes: { from: at(), insert: text ? text + '\n\n' : '' }, effects: endRun.of(id) })
      const after = v2.state.doc.toString()
      setContent(after)
      pushDiff(t('Insert audio'), before, after)
      if (!text) toast(t('Audio inserted, but the transcript came back empty'))
    } catch (e) {
      if ((e as Error).name === 'AbortError') { toast(t('Stopped; nothing was inserted')); return }
      push(patchRun.of({
        id, expanded: true,
        error: t('Processing failed: {err}', { err: friendlyError(e) }),
      }))
    }
  }

  /** Run one block generation.
   *
   * **Output doesn't stream into the body**: generation is previewed only in the placeholder block at the cursor, and lands
   * in the body all at once when done. Streaming directly into the document would interleave text when several tasks run at once;
   * and mid-run scoring may rewrite several rounds, so what streamed in would be overturned versions.
   *
   * After landing in the body, a diff is computed and handed to "Accept / Revert", the same disposition as harness changes and context-menu polish. */
  async function runBlock(item: SlashItem, from: number, to: number, prompt: string) {
    const view = editorViewRef.current
    if (!view || !current) return
    // custom is "replace the selected passage", the rest are "insert a block at the cursor". Both first clear
    // [from,to), and the output lands at from.
    const selection = item.key === 'custom' ? view.state.doc.sliceString(from, to) : ''

    // The input box already blocks empty instructions itself; this is the second line (the items `/` runs directly have no input box).

    const docWithoutSlash = item.key === 'custom' ? view.state.doc.toString()
      : view.state.doc.sliceString(0, from) + view.state.doc.sliceString(to)

    const why = blockPrecondition(item, prompt, selection, docWithoutSlash) || (item.key === 'tray' ? trayPrecondition(current.id) : '')
    if (why) {
      // The `/query` characters are still removed (insert type); the selection (custom) stays
      if (item.key !== 'custom' && to > from) view.dispatch({ changes: { from, to, insert: '' }, selection: { anchor: from } })
      setSlash(null)
      toast(why, 'error')
      return
    }
    if (!llmGate()) { if (item.key !== 'custom' && to > from) view.dispatch({ changes: { from, to, insert: '' }, selection: { anchor: from } }); setSlash(null); return }
    const id = Math.random().toString(36).slice(2, 10)
    const ctrl = new AbortController()
    runAborts.current.set(id, ctrl)
    retryArgs.current.set(id, { item, prompt })
    setSlash(null)                                   // input box closes, handing over to the placeholder block

    view.dispatch({
      changes: { from, to, insert: '' },
      selection: { anchor: from },
      effects: startRun.of({ id, from, label: item.label }),
    })
    const before = view.state.doc.toString()
    const push = (fx: StateEffect<unknown>) => editorViewRef.current?.dispatch({ effects: fx })

    let lastError = ''
    try {
      const block = await api.composeBlock(
        { note_id: current.id, title, content: before, cursor: from,
          // "Write from tray" goes through prompt mode + from_tray (not a new block mode); with an empty instruction the backend writes a passage from the tray materials
          mode: (item.key === 'tray' ? 'prompt' : item.key) as api.BlockMode,
          prompt: item.key === 'tray' && !prompt.trim() ? t('Write a passage from this note’s materials, citing the source material for every sentence') : prompt,
          selection, from_tray: item.key === 'tray' },
        {
          onPhase: (label) => {
            push(patchRun.of({ id, phase: label }))
            push(logRun.of({ id, at: t('Phase'), text: label }))
          },
          onSkills: (d) => {
            push(logRun.of({ id, at: t('Skills'), text: d.injected.length ? t('Loaded {list}', { list: d.injected.join(', ') }) : t('No skills configured for this scope') + (d.menu.length ? t(', {n} left for the model to load on demand', { n: d.menu.length }) : '') }))
          },
          onTools: (calls) => {
            for (const c of calls) {
              const args = Object.entries(c.args)
                .filter(([k]) => k !== 'limit')
                .map(([, v]) => String(v)).join(' / ')
              push(logRun.of({ id, at: t('Search'), text: `${c.tool}${args ? ' (' + args + ')' : ''}` }))
            }
          },
          onDelta: (t) => push(appendPreview.of({ id, text: t })),
          onEvaluate: (status, scores) => {
            const weak = Object.entries(scores ?? {}).filter(([, v]) => v.level < 2)
            push(logRun.of({
              id, at: t('Score'),
              text: status === 'complete' ? t('All criteria met')
                : weak.map(([k, v]) => `${dimLabel(k)}: ${v.note}`).join('; ') || status,
            }))
          },
          onError: (d) => { lastError = d; push(logRun.of({ id, at: t('Error'), text: d })) },
        },
        ctrl.signal)

      const v = editorViewRef.current
      if (!v) return
      const text = (block || '').trim()
      if (!text) {
        // Ones blocked by the threshold (no data near the cursor) get the reason written on the placeholder block, not just "no output"
        push(patchRun.of({ id, error: lastError || t('No content produced'), expanded: true }))
        return                                       // the placeholder block stays so the user can see why
      }

      // `{"text":…,"reason":…}` string into the body, which even entered the TOC and outline. Nothing along this path used to check shape,
      // and "the model answered wrong" is different from "the model errored" — the latter has long been handled, the former never was.
      // The rule is deliberately narrow (see `editor/blockShape`); blocked ones get a human sentence + a "Retry", with the output kept in the preview.
      const badShape = blockShapeProblem(item.key, text)
      if (badShape) {
        push(patchRun.of({ id, error: badShape, expanded: true, retry: true }))
        return
      }
      const run = v.state.field(runsField, false)?.find((r) => r.id === id)
      const at = Math.max(0, Math.min(run?.from ?? from, v.state.doc.length))

      // only reverts what was newly written and the originally selected text is gone; inline replacement adds no blank lines either (`editor/blockLanding`, a pure function with tests)
      const b2 = diffBaseForBlock(v.state.doc.toString(), at, item.key, selection)
      v.dispatch({ changes: { from: at, insert: textToLand(item.key, text) }, effects: endRun.of(id) })
      const after = v.state.doc.toString()
      setContent(after)
      pushDiff(item.label, b2, after)

      requestAnimationFrame(() => editorViewRef.current?.dispatch({ effects: EditorView.scrollIntoView(at, { y: 'start', yMargin: 80 }) }))
    } catch (e) {
      if (ctrl.signal.aborted) {
        push(endRun.of(id))                          // stopped by the user; leave no debris
      } else {

        push(patchRun.of({ id, error: friendlyError(e), expanded: true }))
      }
    } finally {
      runAborts.current.delete(id)
    }
  }

  /** "Stop" on the placeholder block. */
  function stopRun(id: string) {
    const rec = voiceStopById.current.get(id)
    if (rec) { rec(); return }        // recording: stopping still needs transcription, can't just remove the placeholder block
    runAborts.current.get(id)?.abort()
    editorViewRef.current?.dispatch({ effects: endRun.of(id) })
  }


  function retryRun(id: string) {
    const again = retryArgs.current.get(id)
    const v = editorViewRef.current
    if (!again || !v) return
    const at = v.state.field(runsField, false)?.find((r) => r.id === id)?.from ?? 0
    retryArgs.current.delete(id)
    v.dispatch({ effects: endRun.of(id) })
    void runBlock(again.item, at, at, again.prompt)
  }

  /** The split's second column. Real notes are editable (SplitEditor, autosaves itself); the note open in the main pane is read-only; virtual nodes go through KbNoteView.
   *  **A function, not a component**: written as a component inside App, it would be a new type on every render,
   *  so the MarkdownEditor inside would remount along with it, losing the scroll position. */
  function renderSplit(id: string) {
    const note = notes.find((n) => n.id === id)
    const row = allRows.find((r) => r.note_id === id)
    const title = note ? displayTitle(note) : (factsLabel(id) ?? row?.title ?? id)
    return (
      <>
        <div className="split-head">
          <span className="split-title" title={title}>{title}</span>
          {note && <button className="icon-btn" title={t('Open in a tab')} onClick={() => void switchTo(note)}><Icon n="bx-link-external" /></button>}
          <button className="icon-btn" title={t('Close split view')} onClick={() => setSplit(null)}><Icon n="bx-x" /></button>
          {}
          {!rightShown && !focusMode && (
            <button className="icon-btn" title={t('Show right pane ({key})', { key: fmtShortcut('⇧⌘\\') })} onClick={() => setPanes((p) => makeRoomForRight(p, winW, split?.w ?? 0))}><Icon n="bx-chevrons-left" /></button>
          )}
        </div>
        <div className="split-body">
          {api.isVirtualId(id)
            ? <Suspense fallback={<p className="muted" style={{ padding: 16 }}>…</p>}><KbNoteView id={id} rows={allRows} onOpen={(x) => openInSplit(x)}
                          onOpenNote={(nid) => { const n = notes.find((x) => x.id === nid); if (n) void switchTo(n) }}
                          onCite={current ? (fid, text) => insertAtCursor(`${text} [${fid}]`) : null} /></Suspense>
            : note
              ? (current?.id === note.id
                  // The same note is also open in the main pane: read-only here, otherwise both sides save their own and overwrite each other
                  ? <>
                      <p className="muted split-hint">{t('This note is open in the main pane; read-only here.')}</p>
                      {note.content.trim() ? <MarkdownEditor content={content} readOnly /> : <p className="muted">{t('This note is still empty.')}</p>}
                    </>
                  : <SplitEditor key={note.id} note={note} flushRef={splitFlush} onSaved={(n) => {
                      setNotes((prev) => prev.map((x) => (x.id === n.id ? n : x)))
                      void reloadTree(false)
                    }} />)
              : <p className="muted">{t('This note no longer exists.')}</p>}
        </div>
      </>
    )
  }

  // ---------------------------------------------------------------- rendering

  actionsRef.current = { runNoteHarness, runMagicTap, handleSelectionAction, runHarness, ingestCurrentNote, runBlock, dropIfStillEmpty, collapseAll, pushDiff, runSlides, onPickFile, restructureNote, runSkeleton, newNoteUnder, importMarkdown, runVoice, flushChangeLayers }

  return (
    <div className={'shell' + (focusMode ? ' focus-mode' : '')}>
      {treeMenu && (
        <ContextMenu
          at={treeMenu.at}
          items={api.isVirtualId(treeMenu.row.note_id) ? kbMenuItems(treeMenu.row) : treeMenuItems(treeMenu.row)}
          onClose={() => setTreeMenu(null)}
        />
      )}
      {tabMenu && (
        <ContextMenu at={tabMenu.at} items={tabMenuItems(tabMenu.tab)} onClose={() => setTabMenu(null)} />
      )}
      {noteLinkMenu && (
        <ContextMenu at={{ x: noteLinkMenu.x, y: noteLinkMenu.y }} onClose={() => setNoteLinkMenu(null)} items={[
          { kind: 'header', label: noteLinkMenu.title || t('Untitled') },
          { label: t('Add to materials'), icon: 'bx-layer-plus', hint: t('AI will draw on it when writing this note'),
            onSelect: () => {
              const id = noteLinkMenu.id
              // The summary needs the first few hundred chars of that note: fetch once (`[[` link marks carry only the title)
              void api.getNote(id)
                .then((n) => requestTrayAdd({ kind: 'note', ref_id: id, title: n.title || noteLinkMenu.title, excerpt: noteExcerpt(n.content) }))
                .catch(() => requestTrayAdd({ kind: 'note', ref_id: id, title: noteLinkMenu.title, excerpt: '' }))
            } },
          { label: t('Open this note'), icon: 'bx-note', onSelect: () => window.dispatchEvent(new CustomEvent('open-note', { detail: noteLinkMenu.id })) },
        ]} />
      )}
      {tabListAt && (
        <ContextMenu at={tabListAt} onClose={() => setTabListAt(null)} items={[
          { kind: 'header', label: t('Open tabs · {n}', { n: tabs.length }) },
          ...tabs.map((tab): MenuItem => {
            const n = notes.find((x) => x.id === tab.noteId)
            // Same-named tabs (three "One year of startup") can't be told apart by name: add a snippet of the first body line, same as ⌘K
            const dup = tabs.some((o) => o !== tab && o.title === tab.title)
            const snip = dup && n ? previewLine(n.content ?? '', tab.title) : ''
            return {
              label: ellipsize(tab.title || t('Untitled'), 36) + (snip ? ' · ' + ellipsize(snip, 24) : ''), icon: n?.icon || (api.isVirtualId(tab.noteId) ? 'bx-hash' : 'bx-note'),
              hint: tab.id === activeTabId ? t('Current') : undefined, onSelect: () => activateTab(tab),
            }
          }),
          { kind: 'sep' },
          { label: t('Close others'), icon: 'bx-x', disabled: tabs.length <= 1, onSelect: () => closeTabsWhere((x) => x.id !== activeTabId) },
        ]} />
      )}
      {picker && <NotePicker req={picker} rows={tree} />}
      <input ref={importInput} type="file" accept=".md,.markdown,.txt" multiple style={{ display: 'none' }}
             onChange={(e) => { void importMarkdown(e.target.files, importUnder.current); e.target.value = '' }} />
      {quick && <QuickView note={quick} onClose={() => setQuick(null)} onOpen={(n) => void switchTo(n)} />}
      {prompt && <TextPrompt req={prompt} />}
      <Toaster />
      <CommandPalette onOpenNote={(id) => { const n = notes.find((x) => x.id === id); if (n) void switchTo(n); else void api.getNote(id).then((fresh) => switchTo(fresh)).catch(() => toast(t('This note no longer exists'), 'error')) }} onInsertFact={insertAtCursor}
                      tabs={tabs.map((t) => ({ noteId: t.noteId, title: t.title, snip: previewLine(notes.find((n) => n.id === t.noteId)?.content ?? '', t.title) }))}
                      onOpenTab={(id) => activateTab(tabs.find((t) => t.noteId === id))} />
      {showShortcuts && <ShortcutsPanel onClose={() => setShowShortcuts(false)} />}
      {writingPlanParent && (
        <WritingPlanPanel
          parent={writingPlanParent}
          onClose={() => setWritingPlanParent(null)}
          onNoteChanged={() => { void reload(); void reloadTree() }}
          harness={harness}
          onRun={() => runHarness(writingPlanParent)}
          onToggleFollow={() => setHarness((h) => (h ? { ...h, follow: !h.follow } : h))}
          confirm={askConfirm}
        />
      )}
      {exportOne && (
        <div className="palette-backdrop" onMouseDown={() => setExportOne(null)}>
          <div className="palette export-one" role="dialog" aria-label={t('Export this note back')}
               onMouseDown={(e) => e.stopPropagation()}>
            <ExportNotePanel noteId={exportOne.id} title={displayTitle(exportOne)}
                             onMarkdown={() => {
                               if (exportOne.id === current?.id) exportMarkdown()
                               else void api.getNote(exportOne.id).then((n) => downloadMarkdown(displayTitle(n), n.content))
                                 .catch((e) => toast(t('Export failed: ') + friendlyError(e), 'error'))
                             }}
                             onClose={() => setExportOne(null)} />
          </div>
        </div>
      )}
      {}
      {confirmReq && <ConfirmDialog req={confirmReq} />}
      {/* Closing the panel no longer stops the harness (see the HarnessState comment) — while the panel is closed this is
         the only place showing "still running"; clicking reopens the panel for that folder. */}
      {harness?.running && !writingPlanParent && (
        <div
          className="card"
          style={{ position: 'fixed', right: 16, bottom: 16, zIndex: 60, width: 260, cursor: 'pointer' }}
          {...clickable(() => {
            // Find that row back in the tree — the running harness only remembered id and title, while the panel
            // needs the full TreeRow. If not found, don't open (the subtree may have been deleted).
            const row = tree.find((r) => r.note_id === harness.folderId)
            if (row) setWritingPlanParent(row)
          })}
          title={t('Click to open the writing plan panel')}
        >
          <div className="row" style={{ gap: 6 }}>
            <span className="spinner" />
            <strong style={{ fontSize: 'var(--t-md)' }}><Icon n="bx-folder-open" /> {harness.folderName}</strong>
          </div>
          <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '4px 0 0' }}>
            {harness.currentSectionTitle ? t('Writing: {section}', { section: harness.currentSectionTitle }) : t('Launching…')}
          </p>
        </div>
      )}

      <input
        ref={filePick}
        type="file"
        style={{ display: 'none' }}
        accept={pickKind.current === 'image' ? 'image/*' : 'audio/*'}
        onChange={(e) => { void onPickFile(e.target.files); e.target.value = '' }}
      />
      {slash?.item.needsPrompt && (
        <SlashPrompt
          key={`${slash.item.key}:${slash.from}:${slash.to}`}
          item={slash.item}
          x={slash.x}
          y={slash.y}
          busy={false}
          phase=""
          onRun={(p) => {
            void runBlock(slash.item, slash.from, slash.to, p)
          }}
          onCancel={() => setSlash(null)}
        />
      )}
      {selectionMenu && (
        <SelectionMenu
          x={selectionMenu.x}
          y={selectionMenu.y}
          busy={selectionBusy}
          onAction={handleSelectionAction}
          onStop={() => selectionAbortRef.current?.abort()}
          onClose={() => { if (!selectionBusy) setSelectionMenu(null) }}
        />
      )}
      {/* The tab row is at the very top, full width. macOS traffic lights sit in the left spacer; the right filler
          is the window drag area (per Trilium desktop_layout.tsx:71-95: with window controls on the left, a tab row
          occupying only rest-pane leaves no room, and the traffic lights would be drawn onto the launcher). */}
      <div className="tab-bar">
        <div className="tab-row-left-spacer" />
        {/* Back/forward (TabHistoryNavigationButtons). Jump to look at a note and come back. */}
        <span className="history-nav">
          <button className="icon-btn" disabled={!histState.back} title={t('Back ({key})', { key: fmtShortcut('⌘[') })} onClick={() => goHistory(-1)}><Icon n="bx-left-arrow-alt" /></button>
          <button className="icon-btn" disabled={!histState.fwd} title={t('Forward ({key})', { key: fmtShortcut('⌘]') })} onClick={() => goHistory(1)}><Icon n="bx-right-arrow-alt" /></button>
        </span>
        <TabBar
          tabs={tabs}
          activeId={activeTabId}
          onSelect={(id) => activateTab(tabs.find((x) => x.id === id))}
          onClose={closeTab}
          onNew={newNote}
          onContextMenu={(tab, at) => setTabMenu({ tab, at })}
          iconOf={(noteId) => notes.find((x) => x.id === noteId)?.icon || undefined}
          onReorder={reorderTab}
          onListTabs={setTabListAt}
          menuTabId={tabMenu?.tab.id ?? null}
          busyIds={new Set([loading === 'note-harness' ? noteHarnessNoteId : null, harness?.running ? harness.currentNoteId : null].filter((x): x is string => !!x))}
        />
      </div>
      <div className="shell-main">
      {/* Launcher — Trilium's 58px vertical strip. It holds **cross-note entries**:
          knowledge base, Skills, infinite continue, settings, user. Criterion in docs/product-north-star.md:
          memory is a first-class citizen and shouldn't hide in a popover behind some button. */}
      <div className="launcher-pane">
        <div className="launcher-logo" title="MEMOKET NOTE"><Logo size={30} /></div>
        <button className="launcher-btn" title={t('New note ({key})', { key: fmtShortcut('⌘N') })} onClick={newNote}><Icon n="bx-plus" /></button>
        <button className="launcher-btn" title={t('Today’s journal ({key}): Journal / year / month / day, created if missing', { key: fmtShortcut('⇧⌘D') })} onClick={() => void openToday()}><Icon n="bx-calendar-event" /></button>
        <button className="launcher-btn" title={t('Global search: notes + knowledge base ({key})', { key: fmtShortcut('⌘K') })}
                onClick={() => window.dispatchEvent(new CustomEvent('open-command-palette'))}><Icon n="bx-search" /></button>
        {}
        {DESTINATIONS.filter((d) => d.where === 'top').map((d) => (
          <button key={d.id} className={'launcher-btn' + (d.id === 'kb'
                    ? (virtualId === 'kb' || virtualId?.startsWith('kb:') ? ' active' : '')
                    : (virtualId === d.id ? ' active' : ''))}
                  title={d.hint} onClick={() => void openVirtual(d.id, d.name)}><Icon n={d.icon} /></button>
        ))}
        <div className="launcher-spacer" />
        {/* Settings and Skills are "special notes": they open a tab and go into the middle pane, treated like any other note
            (per Trilium: options are notes in a hidden subtree, not popovers). */}
        {DESTINATIONS.filter((d) => d.where === 'foot').map((d) => (
          <button key={d.id} className={'launcher-btn' + (virtualId === d.id ? ' active' : '')}
                  title={d.hint} onClick={() => void openVirtual(d.id, d.name)}><Icon n={d.icon} /></button>
        ))}
        <button className={'launcher-btn left-pane-toggle' + (panes.leftOn ? '' : ' collapsed')}
                title={panes.leftOn ? t('Hide left pane (⌘\\)') : t('Show left pane (⌘\\)')}
                onClick={() => setPanes((p) => ({ ...p, leftOn: !p.leftOn }))}><Icon n="bx-chevrons-left" /></button>
        {/* The user avatar sits at the very bottom — counterpart of the GlobalMenu at the bottom of Trilium's launcher. */}
        <UserSwitcher />
      </div>

      {/* Focus mode collapses the left pane — but the launcher stays: it holds the cross-note entries; without it
          focus mode would mean "nothing to click". */}
      {leftShown && (
      <div className="left-pane" style={{ width: leftW }}>
        {/* The left pane does only one thing, "find notes": quick search + tree.
            Title, user switch, new and import all moved into the launcher — per Trilium: the left pane is
            navigation, cross-note entries are in the launcher. */}
        {/* Quick search sits above the tree — Trilium's position. */}
        <div className="left-pane-search">
        <div className="quick-search">
          <Icon n="bx-search" />
          <input
            placeholder={t('Quick search')}
            title={t('Search titles and text; {key} is global search (including the knowledge base)', { key: fmtShortcut('⌘K') })}
            value={noteQuery}
            onChange={(e) => setNoteQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setNoteQuery('')
              // Enter opens the first hit (Trilium's quick search does too), no need to reach for the mouse
              else if (e.key === 'Enter' && visibleNotes.length && noteQuery.trim()) { void switchTo(visibleNotes[0]); setNoteQuery('') }
            }}
          />
          {noteQuery && <button className="icon-btn" title={t('Clear')} onClick={() => setNoteQuery('')}><Icon n="bx-x" /></button>}
        </div>
        </div>
        {}
        {}
        {(notes.length > 0 || searchResults !== null || noteQuery) && (
        <div className="list-head">
          {searchResults !== null || noteQuery ? (
            <span className="muted">{t('{n} results', { n: visibleNotes.length })}</span>
          ) : (
            <>
              <span className="seg">
                <button className={recentMode ? '' : 'on'} onClick={() => setRecentMode(false)}
                        aria-pressed={!recentMode} title={t('By your own hierarchy')}>{t('Tree')}</button>
                <button className={recentMode ? 'on' : ''} onClick={() => setRecentMode(true)}
                        aria-pressed={recentMode} title={t('By recent changes, flat')}>{t('Recent')}</button>
              </span>
              <span className="muted">{t('{n} notes', { n: notes.length })}</span>
            </>
          )}
        </div>
        )}
        {/* The tree's scroll container — with many notes, without it the bottom of the tree is cut off and unreachable */}
        <div className="left-pane-body">
        {recentMode && searchResults === null && !noteQuery ? (
          /* Flat, by recent change. No hierarchy drawn — same rule as when searching (the App line
             "a hit should be visible directly, without guessing which tree level it's on"): this mode answers
             "which notes did I touch recently", and hierarchy doesn't help with that question.
             `renderNoteItem` rows already carry "parent folder · time", exactly what this mode needs. */
          [...notes].sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? '')).map(renderNoteItem)
        ) : searchResults !== null || noteQuery ? (
          // No tree while searching: a hit should be visible directly, without guessing which tree level it's on.
          visibleNotes.length === 0
            ? (

              <div className="muted" style={{ padding: '4px 2px', lineHeight: 1.7 }}>
                {t('No matching notes.')}
                <br />
                <a href="#" onClick={(e) => {
                  e.preventDefault()
                  const q = noteQuery.trim()
                  setPendingKbQuery(q)                 // not mounted yet: it picks it up when mounting
                  window.dispatchEvent(new CustomEvent('kb-search', { detail: q }))  // already open: receives it directly
                  void openVirtual('kb', t('Knowledge base'))
                }}>{t('Search the knowledge base for “{q}” →', { q: noteQuery.trim().slice(0, 12) })}</a>
              </div>
            )
            : visibleNotes.map(renderNoteItem)
        ) : (
          <NoteTree
            rows={tree}
            menuRowId={treeMenu?.row.id ?? null}
            activeNoteId={current?.id ?? virtualId}
            onOpen={openFromTree}
            /* The note tree holds only the user's own notes; the knowledge base is a top-level workspace in the leftmost strip. */
            onToggle={(row) => void toggleTreeNode(row)}
            onDelete={(row) => { const n = notes.find((x) => x.id === row.note_id); if (n) void removeWithSubtree(n, row) }}
            locateTick={locateTick}
            onRename={(row) => void renameNode(row)}
            onNewChild={(row) => void newNoteUnder(row.note_id)}
            onDrop={(d, t, w) => void dropNode(d, t, w)}
            onFilesDrop={(files, t) => void importMarkdown(files, t?.note_id ?? api.ROOT_ID)}
            onContextMenu={(row, at) => setTreeMenu({ row, at })}
          />
        )}
        </div>
        {/* Bottom floating toolbar (note_tree.ts:113-121): locate the current note / collapse the whole tree.
            We especially need "locate" — cloning means the same note appears in several places in the tree. */}
        {searchResults === null && !noteQuery && (
        <div className="tree-actions">
          <button className="icon-btn" title={t('Locate current note')} onClick={() => setLocateTick((v) => v + 1)}><Icon n="bx-crosshair" /></button>
          <button className="icon-btn" title={t('Collapse all')} onClick={() => void collapseAll()}><Icon n="bx-collapse-vertical" /></button>
        </div>
        )}
      </div>
      )}

      {leftShown && (
        <Gutter side="left" onResize={(dx) => setPanes((p) => ({ ...p, leftW: Math.max(150, Math.min(600, p.leftW + dx)) }))} />
      )}

      <div className="rest-pane">
        {/* This branch is inside `!split`, so the split width counts as 0 when making room */}
        {!rightShown && !focusMode && !split && !!current && (
          <button className="right-pane-reopen" title={t('Show right pane ({key})', { key: fmtShortcut('⇧⌘\\') })}
                  onClick={() => setPanes((p) => makeRoomForRight(p, winW, 0))}><Icon n="bx-chevrons-left" /></button>
        )}
        <div className="center-pane">
        <div className={'note-pane' + (focusMode ? ' focus' : '')}>
        {/* The title row is fixed above the scroll area (Trilium's title-row is a sibling of ScrollingContainer,
            50px). A title that scrolls away with the body leaves you not knowing which note you're writing once scrolled down. */}
        {current && (
          <div className="title-row">
            {/* The icon is clickable: pick one as this note's marker (Trilium's NoteIcon). The same one in tree, tab and title row */}
            <button type="button" className="title-icon-btn" title={t('Change icon')} aria-label={t('Change icon')} aria-haspopup="dialog" aria-expanded={iconPicker} ref={iconBtnRef} onClick={() => setIconPicker((v) => !v)}>
              <Icon className="title-icon" n={current.icon || ((tree.find((r) => r.note_id === current.id)?.child_count ?? 0) > 0 ? 'bx-folder' : 'bx-note')} />
            </button>
            {iconPicker && (
              <IconPicker current={current.icon ?? ''} onClose={() => { setIconPicker(false); iconBtnRef.current?.focus() }}
                          onPick={(ic) => { setIconPicker(false); iconBtnRef.current?.focus(); void api.setNoteIcon(current.id, ic).then((n) => {
                            setCurrent((c) => (c && c.id === n.id ? { ...c, icon: n.icon } : c))
                            setNotes((prev) => prev.map((x) => (x.id === n.id ? { ...x, icon: n.icon } : x)))
                            void reloadTree(false)
                          }).catch((e) => toast(t('Could not change icon: {err}', { err: friendlyError(e) }), 'error')) }} />
            )}
            {/* When the title is a placeholder ("Untitled") the input shows empty with the body's first line as placeholder —
                using the same displayTitle as tree and tabs, so a note no longer has two names */}
            <input aria-label={t('Note title')}
              className="note-title"
              value={isPlaceholderTitle(title) ? '' : title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={displayTitle({ title: '', content }) === displayTitle({ title: '', content: '' }) ? t('Title') : displayTitle({ title: '', content })}
            />
            {saveStatus && (
              <span key={saveStatus.at} className={'save-status' + (saveStatus.error ? ' error' : '')}
                    title={saveStatus.error ?? undefined}>
                {saveStatus.error ? t('⚠ Not saved') : t('Saved')}
              </span>
            )}
          </div>
        )}
        {/* ribbon — this note's metadata. The first thing put in was **the writing outline**:
            criterion 3 says "plan autonomously, execute autonomously, check results", so **the plan must be visible**,
            together with the body, not in some right-pane panel you must switch to. Hide the plan, and
            all the user can see is a spinning indicator, which says nothing. */}
        {current && (
          <Ribbon
            noteKey={current.id}
            tabs={[{

              id: 'format', title: t('Format'), icon: 'bx-text',
              body: (
                <MarkdownToolbar
                  viewRef={editorViewRef}
                  onFormat={formatNote}
                  onRestructure={restructureNote}
                  onStopRestructure={stopRestructure}
                  restructuring={loading === 'restructure'}
                />
              ),
            }, {
              id: 'cites', title: t('Citations'), icon: 'bx-link',
              badge: citedIds.length || undefined,
              body: <NoteKbPanel
                citedIds={citedIds}
                row={tree.find((r) => r.note_id === current.id)}
                noteId={current.id}
                onOpenNote={(id) => { const n = notes.find((x) => x.id === id); if (n) void switchTo(n) }}
                onIngest={ingestCurrentNote}
                onSync={() => void syncNoteToKb(current.id)}
                ingesting={loading === 'ingest' || !!job}
                empty={!content.trim()}
                onStripMissing={stripCitationIds}
                refreshTick={ingestTick}
              />,
            }, {
              id: 'links', title: t('Links'), icon: 'bx-link-alt',
              badge: linkedNoteIds(content).length || undefined,
              body: <NoteLinksPanel noteId={current.id} content={content}
                                    onOpen={(id) => { const n = notes.find((x) => x.id === id); if (n) void switchTo(n) }}  onUnlink={unlinkNotes} knownIds={noteIdSet} knownNotes={notes} updatedAt={current.updated_at} />,
            }, {
              id: 'history', title: t('History'), icon: 'bx-history',
              body: <RevisionHistoryPanel noteId={current.id} currentChars={wordCount(content)} currentContent={content} updatedAt={current.updated_at}
                                          onRestored={(n) => { setCurrent(n); setTitle(n.title); setContent(n.content); liveContentRef.current = n.content; void reload() }} />,
            }, {
              id: 'paths', title: t('Paths'), icon: 'bx-git-branch',
              badge: (tree.find((r) => r.note_id === current.id)?.branch_count ?? 1) > 1
                ? tree.filter((r) => r.note_id === current.id).length : undefined,
              body: <NotePathsPanel noteId={current.id} rows={tree}
                                    onOpen={(id) => { const n = notes.find((x) => x.id === id); if (n) void switchTo(n) }}
                                    onClone={() => { const row = tree.find((r) => r.note_id === current.id); if (row) void cloneNodeTo(row) }} />,
            }, {
              id: 'info', title: t('Info'), icon: 'bx-info-circle',
              body: <NoteInfoPanel note={current} content={content} row={tree.find((r) => r.note_id === current.id)} />,
            },

            ...(journalDay
              ? [{ id: 'journey', title: t('Screen activity'), icon: 'bx-desktop',
                   body: <JourneyRibbonPanel date={journalDay} /> }]
              : [])] as RibbonTab[]}
          />
        )}
        <div className={'note-scroll' + (current ? ' has-composer' : '')}>
        <div className="note-body">

        {!current ? (
          virtualId === 'app:import' ? (
            <div className="kb-note" style={{ maxWidth: 760 }}>
              <MemoryPanel pendingJob={job} trayNoteId={trayTarget} />
            </div>
          ) : virtualId === 'app:settings' ? (
            <div className="kb-note"><h2 className="kb-note-title"><Icon n="bx-cog" /> {t('Settings')}</h2><SettingsPanel embedded /><h3 className="kb-section-title">{t('Interface language')}</h3><LanguageRow /><h3 className="kb-section-title">{t('Preferences')}</h3><PreferencesPanel /><AboutLine /></div>
          ) : virtualId === 'app:skills' ? (
            <div className="kb-note" style={{ maxWidth: 900 }}><h2 className="kb-note-title"><Icon n="bx-extension" /> {t('Writing Skills')}</h2><SkillsPanel embedded /></div>
          ) : virtualId === 'app:journey' ? (
            <Suspense fallback={<p className="muted" style={{ padding: 16 }}>…</p>}>
              <JourneyPage onLater={() => { if (activeTabId) closeTab(activeTabId) }}
                           onOpenNote={(id) => { void reload().then(() => api.getNote(id).then((n) => switchTo(n)).catch(() => {})) }}
                           onOpenJournal={(d) => void openToday(d)} />
            </Suspense>
          ) : virtualId === 'app:trash' ? (
            <div className="kb-note" style={{ maxWidth: 760 }}><h2 className="kb-note-title"><Icon n="bx-trash" /> {t('Trash')}</h2>
              <TrashPanel onRestored={(id) => { void reload(); void reloadTree(); void api.getNote(id).then((n) => switchTo(n)).catch(() => {}) }} /></div>
          ) : virtualId ? (
            <Suspense fallback={<p className="muted" style={{ padding: 16 }}>…</p>}><KbNoteView
              id={virtualId}
              rows={allRows}
              onOpen={(id) => void openVirtual(id)}
              onBack={() => { if (histState.back) goHistory(-1); else void openVirtual('kb') }}
              onOpenNote={(id) => { const n = notes.find((x) => x.id === id); if (n) void switchTo(n) }}
              onCite={null}
            /></Suspense>
          ) : (
            <WelcomePane
              notes={notes}
              factCount={kbRows.find((r) => r.note_id === 'kb')?.fact_count ?? 0}
              onNew={() => void newNote()}
              onImport={() => void openVirtual('app:import', t('Import'))}
              onOpen={(id) => void openVirtual(id)}
              onOpenNote={(n) => void switchTo(n)}
              onShortcuts={() => setShowShortcuts(true)}
            />
          )
        ) : (
          <>
            {/* Floating buttons (Trilium FloatingButtons): AI capabilities live with the body without taking body lines.
                Criterion 1, "one capability, one button": Continue and Smart Continue get one each; Polish and "I decide each round" are
                Smart Continue parameters, tucked into its ▾; recording is one microphone with two destinations; ⋯ is miscellany. */}
            <div className="floating-buttons">
              {}
              {loading === 'note-harness' && !pausedRun && noteHarnessStatus && (
                <span className="fb-status muted" title={noteHarnessStatus + '\n' + t('While running, AI has the text; stop before editing')}>
                  <span className="spinner" /><span className="fb-status-text">{noteHarnessStatus}</span>
                </span>
              )}
              <div className="workflow-control">
                <button ref={workflowButtonRef} className={'fb-btn' + (intent.workflow ? ' mode-active' : '')}
                        disabled={loading === 'note-harness' || loading === 'tap'}
                        title={t('Writing mode: choose Daily report, Weekly report, Journal, Meeting notes, or define this note’s writing task')}
                        aria-haspopup="dialog" aria-expanded={!!workflowPicker}
                        onClick={() => setWorkflowPicker((open) => open ? null : { resume: false })}>
                  <Icon n="bx-layout" /><span className="fb-label">{intent.workflow ? t(WORKFLOW_LABEL[intent.workflow]) : t('Writing mode')}</span>
                </button>
              </div>
              <button className={'fb-btn primary' + (loading === 'tap' ? ' running' : '')} onClick={runMagicTap}
                      disabled={loading === 'note-harness'}
                      title={t('Continue: write the next passage once, using relevant memory')}>
                <Icon n={(loading === 'tap' ? 'bx-stop' : 'bx-edit-alt')} /><span className="fb-label">{loading === 'tap' ? t('Stop') : t('Continue')}</span>
              </button>
              <span className="fb-split">
                <button className={'fb-btn secondary' + (loading === 'note-harness' ? ' running' : '')}
                        onClick={() => runNoteHarness('write')} disabled={loading === 'tap' || isSlides(content)}
                        title={isSlides(content) ? t('This note is a slide deck — appending prose would break the pages and citations; edit the source note and regenerate instead')
                          : t('Smart Continue: work toward your goal through multiple writing and checking rounds')}>
                  <Icon n={(loading === 'note-harness' ? 'bx-stop' : 'bx-bot')} /><span className="fb-label">{loading === 'note-harness' ? t('Stop') : t('Smart Continue')}</span>
                </button>
                <button className="fb-btn secondary fb-caret-btn" title={t('Polish / review each round')}
                        onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setFbMenu({ kind: 'harness', at: { x: r.right - 220, y: r.bottom + 4 } }) }}>
                  <Icon n="bx-chevron-down" />
                </button>
              </span>
              <AudioRecorder onTranscript={insertAtCursor} onIngested={setJob} offline={asrOffline} noteId={current?.id} />
              <button className="fb-btn" title={t('Download Markdown or send this note to a connected tool')}
                      onClick={() => { void save().then(() => setExportOne(current)).catch((e) => toast(t('Export failed: ') + friendlyError(e), 'error')) }}>
                <Icon n="bx-export" /><span className="fb-label">{t('Export')}</span>
              </button>
              <button className="fb-btn" title={t('More')}
                      onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setFbMenu({ kind: 'more', at: { x: r.right - 220, y: r.bottom + 4 } }) }}>
                <Icon n="bx-dots-horizontal-rounded" />
              </button>
              {workflowPicker && (
                <WritingWorkflowPicker
                  anchor={workflowButtonRef.current}
                  intent={intent}
                  resume={workflowPicker.resume}
                  focus={workflowPicker.focus}
                  onSelect={(id) => applyWritingWorkflow(id, workflowPicker.resume)}
                  onCustom={(task) => applyCustomWritingTask(task, workflowPicker.resume)}
                  onClose={() => {
                    setWorkflowPicker(null)
                    requestAnimationFrame(() => workflowButtonRef.current?.focus())
                  }}
                />
              )}
              {}
              {BUSY_LABEL[loading] && (
                <span className="fb-busy muted"><span className="spinner" /><span>{slidePhase || t(BUSY_LABEL[loading])}</span>
                  {}
                  {loading === 'slides' && <button className="linklike link" style={{ marginInlineStart: 6 }} onClick={() => abortRef.current?.abort()}>{t('Stop')}</button>}
                </span>
              )}
              {fbMenu && (
                <ContextMenu at={fbMenu.at} onClose={() => setFbMenu(null)} items={fbMenu.kind === 'harness' ? [
                  { label: t('Polish (revise only, no new text)'), icon: 'bx-brush', disabled: loading === 'note-harness' || !content.trim(),
                    hint: !content.trim() ? t('The note is empty') : undefined, onSelect: () => { void runNoteHarness('polish') } },
                  { kind: 'sep' },
                  { label: reviewEachRound ? t('Review each round: on') : t('Review each round: off'), icon: reviewEachRound ? 'bx-checkbox-checked' : 'bx-checkbox',
                    hint: t('Pauses after each round so you can accept/revert each change'), disabled: loading === 'note-harness',
                    onSelect: () => setReviewEachRound((v) => !v) },
                ] : [
                  { label: t('Save to knowledge base'), icon: 'bx-brain', disabled: !content.trim() || loading === 'ingest' || !!job,
                    hint: !content.trim() ? t('The note is empty') : job ? t('Saving to knowledge base') : undefined, onSelect: () => void ingestCurrentNote() },


                  { label: t('Endless writing…'), icon: 'bx-rocket', disabled: isSlides(content),
                    hint: isSlides(content) ? t('This note is a slide deck — edit the source note and regenerate instead')
                      : t('Give a goal; it is split into sections, each becoming a child note of this one'),
                    onSelect: () => { const row = tree.find((r) => r.note_id === current.id); if (row) setWritingPlanParent(row) } },
                  /* Pain point 6: "I want to make it a PPT, but then upload it to another agent tool, and the two tools aren't linked".
                     **The output is a note, not a file** — it lands as this note's child, so it can be found with ⌘K,
                     carry citations, be further edited by continue, and be exported. Exporting to PDF is the second step. */
                  { label: t('Make slides…'), icon: 'bx-slideshow', disabled: !content.trim() || loading === 'slides',
                    hint: !content.trim() ? t('The note is empty') : t('Lands as a child note of this one, each page carrying its citation ids'),
                    onSelect: () => { void runSlides('points') } },
                  /* Offered only when this note really is slides — "Export slides" on an ordinary note is an empty promise.
                     Zero new dependencies: the main process runs printToPDF in an offscreen window (the "Export" row under §landing in the design). */
                  ...(isSlides(content) && window.memoketDesktop?.slidesToPdf ? [{
                    label: t('Export these slides → PDF'), icon: 'bx-file-blank',
                    hint: t('{n} pages, 16:9', { n: slidePages(content).length }),
                    onSelect: () => { void exportSlidesPdf() },
                  }] : []),
                  { label: t('Split view with another note…'), icon: 'bx-columns', onSelect: () => { void askNode(t('Which note to open in split view?'), new Set([current.id])).then((id) => { if (id && id !== api.ROOT_ID) openInSplit(id) }) } },
                  { kind: 'sep' },
                  { label: t('Save a version now'), icon: 'bx-bookmark-plus', hint: t('Versions are under History in the ribbon'), disabled: !content.trim(),
                    onSelect: () => { void save().then(() => api.snapshotNote(current.id)).then(() => toast(t('Version saved'))).catch((e) => toast(t('Could not save version: {err}', { err: friendlyError(e) }), 'error')) } },
                  { label: t('Export as .md'), icon: 'bx-export', onSelect: exportMarkdown },

                  { label: t('Export back to Obsidian / Notion / Feishu…'), icon: 'bx-share',
                    /* **This sentence used to be inaccurate**: only Obsidian matches by memoket_id in the file;
                       Notion / Feishu match the note recorded on this machine (`note_remotes.remote_id`).
                       The difference is real: exporting from another machine, Notion / Feishu create a new copy instead of overwriting. */
                    hint: t('Overwrites the same note on the other side (Obsidian matches by the id in the file; Notion / Feishu by what this machine remembers)'),
                    onSelect: () => setExportOne(current) },
                  { label: t('Export all notes…'), icon: 'bx-package', hint: t('Whole library as a Markdown zip'), onSelect: () => window.dispatchEvent(new CustomEvent('export-all')) },
                  { label: t('Copy text'), icon: 'bx-copy', onSelect: () => void copyMarkdown() },
                  { kind: 'sep' },
                  { label: t('How to write'), icon: 'bx-help-circle',
                    hint: t('Markdown syntax, ```mermaid diagrams, [[ to link notes, @ to cite facts'),
                    onSelect: () => setShowShortcuts(true) },
                  { label: focusMode ? t('Exit focus mode') : t('Focus mode'), icon: 'bx-fullscreen', shortcut: '⌘.', onSelect: () => setFocusMode((v) => !v) },
                  { label: t('Save'), icon: 'bx-save', shortcut: '⌘S', onSelect: () => void save() },
                ]} />
              )}
            </div>
            {}
            {}
            {/* The folder harness writing into the current note also gets a bar — otherwise the editor suddenly can't be typed in, with no explanation */}
            {!pausedRun && loading !== 'note-harness' && harness?.running && harness.currentNoteId === current?.id && (
              <div className="harness-sticky">
                <p className="muted harness-line"><Icon n="bx-bot" /> <span style={{ flex: 1, minWidth: 0 }}>
                  {t('The writing plan for “{name}” is writing this note{section}', { name: harness.folderName, section: harness.currentSectionTitle ? t(' ({title})', { title: harness.currentSectionTitle }) : '' })}
                </span>
                  <span className="muted" style={{ marginInlineStart: 8, fontSize: 'var(--t-xs)' }}>· {t('AI has the text; stop before editing')}</span>
                </p>
              </div>
            )}
            {}
            {(pausedRun || (harnessDone && noteHarnessStatus)) && (
              <div className="harness-sticky">
                <p className="muted harness-line"><Icon n="bx-bot" /> <span style={{ flex: 1, minWidth: 0 }}>{pausedRun ? t('This round is done; after reviewing each change:') : noteHarnessStatus}</span>
                  {pausedRun && (
                    /* End-of-round pause: this round is written, waiting for you to accept/revert each change in the body.
                       Turning this switch off gives the old behavior — run straight through, then dispose, which means
                       any disposition you make during the run gets overwritten by the next round. */
                    <span className="row" style={{ gap: 6, marginInlineStart: 8 }}>
                      <button className="primary" onClick={() => resumePausedRun()}><Icon n="bx-play" /> {t('Keep writing')}</button>
                      <button onClick={() => resumePausedRun(true)}>{t('Stop here')}</button>
                    </span>
                  )}
                  {harnessDone && !pausedRun && (
                    <button className="chip" onClick={() => setPaneFocus({ id: 'plan', n: Date.now() })}>
                      <Icon n="bx-list-check" /> {t('View run details')}
                    </button>
                  )}
                  {harnessDone && !pausedRun && <button className="icon-btn sm" title={t('Close')} onClick={() => { setHarnessDone(false); harnessDoneRef.current = false; setNoteHarnessStatus('') }}><Icon n="bx-x" /></button>}
                </p>
              </div>
            )}

            {tapMeta && <TapProvenance meta={tapMeta} notes={tapNotes}
                                       onDismiss={() => { setTapMeta(null); setTapNotes([]) }} />}
            {/* The whole note is indented 4+ spaces (common when pasted from elsewhere): markdown treats all of it as a code block,
                headings aren't headings, just a sheet of monospace. Offer a one-click unindent; don't make people guess why rendering is wrong. */}
            {current && content.length > 40 && stripCommonIndent(content) !== content && (
              <p className="muted harness-line" style={{ marginBottom: 8 }}>
                <Icon n="bx-info-circle" /> {t('This note is indented throughout; Markdown treats it as one code block, so headings and lists won’t render.')}
                <button className="chip" style={{ marginInlineStart: 8 }} onClick={formatNote}><Icon n="bx-align-left" /> {t('Remove indentation')}</button>
              </p>
            )}

            {}
            {pendingDiff > 0 && (
              <div
                className="row pending-diff-bar"
                style={{
                  gap: 8, alignItems: 'center',
                  fontSize: 'var(--t-sm)', padding: '5px 8px', borderRadius: 'var(--r-sm)',
                  border: '1px solid var(--line)', background: 'var(--panel)',
                }}
              >
                <span style={{ color: 'var(--ins)' }}>●</span>
                <span>{t('{n} AI changes in this note', { n: pendingDiff })}</span>
                <span className="muted">{t('Hover to handle each one; ')}<a href="#" onClick={(e) => { e.preventDefault(); setPaneFocus({ id: 'changes', n: Date.now() }) }}>{t('view by round')}</a></span>
                <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                  <button onClick={acceptAllDiff}>{t('Accept all')}</button>
                  <button onClick={rejectAllDiff} title={t('Restore everything this round changed to how it was')}>
                    {t('Revert all')}
                  </button>
                </span>
              </div>
            )}
            <MarkdownEditor
              content={content}

              // on `servedRef`; the guard relies on it to tell "the user deleted it" from
              // "React's mirror lagged behind". Echoes don't come this way (`editor/syncEcho.ts` blocks them).
              onChange={onEditorChange}
              // Lock the editor while AI is writing: hand-typed text then would be overwritten by the server's body at round end (sync is
              // server-authoritative). Per-round pause, finishing and stopping all unlock it.
              // The note the folder harness is writing is read-only too: like the single-note one it writes into the body block by block,

              readOnly={loading === 'note-harness' || loading === 'tap'
                || (!!harness?.running && harness.currentNoteId === current?.id)}
              scrollPad
              revisions={revisions}
              onAcceptInline={acceptRevision}
              roundDiff={roundDiff}
              undoGroup={undoGroup}
              onPendingDiff={setPendingDiff}
              onLayersChanged={onLayersChanged}
              onSelectionContextMenu={(x, y, text) => setSelectionMenu({ x, y, text })}
              onCursorParagraph={setCursorPara}
              marginMarks={marginMarks}
              onMarginClick={(m, anchor, reason) => { if (!m || !anchor) { setMarginCard(null); return } setMarginCard({ m, anchor, reason }) }}
              onAltHover={(phrase, anchor, reason, range) => { if (!anchor) return; setTraceCard((c) => (c && c.phrase === phrase && c.reason === reason ? c : { phrase, anchor, reason, range })) }}
              onSlash={onSlash}
              onStopRun={stopRun}
              onRetryRun={retryRun}


              placeholder={t('Write here.  Type / for the menu: AI writing, images, tables, layout')}
              viewRef={editorViewRef}
            />
            {}
            {marginCard && current && (
              <MarginCard card={marginCard} content={content} onClose={() => setMarginCard(null)} onInsert={insertAtCursor}
                          onSeeAll={() => { setMarginCard(null); setPaneFocus({ id: 'memory', n: Date.now() }) }} />
            )}
            {}
            {traceCard && current && (
              <TraceCard card={traceCard} content={content} onClose={() => setTraceCard(null)} onInsert={insertAtCursor}
                         onTrace={(p) => void traceFromCard(p)} />
            )}
          </>
        )}
        </div>{/* note-body */}
        </div>{/* note-scroll */}
        </div>{/* note-pane */}
        {split && (
          <>
            <Gutter side="right" onResize={(dx) => setSplit((s) => s && ({ ...s, w: Math.max(260, Math.min(900, s.w + dx)) }))} />
            <div className="split-pane" style={{ width: splitW }}>
              {renderSplit(split.id)}
            </div>
          </>
        )}

      {rightShown && (
        <Gutter side="right" onResize={(dx) => setPanes((p) => ({ ...p, rightW: Math.max(180, Math.min(700, p.rightW + dx)) }))} />
      )}
      {rightShown && (
      <div className="right-pane" style={{ width: panes.rightW }}>
        {verifyResult && (
          <VerifyPanel findings={verifyResult.findings}
                       checked={verifyResult.checked ?? 0}
                       unparsed={verifyResult.unparsed ?? false}
                       passage={verifyResult.passage}
                       gone={!!verifyResult.passage && !content.includes(verifyResult.passage)}
                       onJump={jumpToPassage(verifyResult.passage)}
                       onClose={() => setVerifyResult(null)} />
        )}
        <RightPane
          onCollapse={() => setPanes((p) => ({ ...p, rightOn: false }))}
          defaultTab="memory"
          focusTab={paneFocus}
          tabs={[
            // Memory is the default tab: recall that surfaces as you write (criterion 2). No longer a permanent block above all tabs.
            { id: 'memory', title: t('Memory'), icon: 'bx-bulb', alwaysShown: true,
              body: current
                ? <div className="stack">
                    {}
                    <TrayPanel key={'tray:' + current.id} noteId={current.id} onWrite={writeFromTray} />
                    <RelatedMemory key={ingestTick} content={content} paragraph={cursorPara} onInsert={insertAtCursor}
                                   noRecordDots={noRecordDots}
                                   kbEmpty={kbRows.length > 0 && (kbRows.find((r) => r.note_id === 'kb')?.fact_count ?? 0) === 0} />
                  </div>
                : <p className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('Open a note and related memories will surface here as you write.')}</p> },

            /* Slides preview: **appears only when this note really is slides** (front-matter has slides: true).
               An extra tab that's always empty on ordinary notes is worse than no tab. */
            ...(isSlides(content) ? [{
              id: 'slides', title: t('Slides'), icon: 'bx-slideshow', alwaysShown: true,
              badge: slidePages(content).length || undefined,
              body: <SlidesPanel content={content} viewRef={editorViewRef} />,
            }] : []),
            // Layered ledger of changes: one layer per AI action, accept / revert whole layers (pain point 8: AI changed three rounds and I only want the first)



            // This cell used to look only at `pendingDiff` (excluding whitespace-only spots), while the panel drew from `layersOf` /
            // `settledOf` — after a layer was fully disposed per change the panel still had the grey "Disposed N accepted / M reverted" line

            // These two numbers are **read from the editor on the spot** — same render pass and same
            // view as `ChangeLayersPanel` below, so the two can't disagree; re-rendering is still triggered by `pendingDiff` / `layersTick`.
            { id: 'changes', title: t('Changes'), icon: 'bx-git-compare', badge: pendingDiff || undefined,
              hasContent: changesTabHasContent({
                layers: editorViewRef.current ? layersOf(editorViewRef.current).length : 0,
                settled: editorViewRef.current ? settledOf(editorViewRef.current).length : 0,
                runs: runs.length,
                stuck: layerStuck.length,
                feedback: writingFeedback?.decided ?? 0,
              }),
              body: <ChangeLayersPanel viewRef={editorViewRef} tick={pendingDiff + layersTick} runs={runs} busy={loading === 'rounds'}
                                       feedback={writingFeedback}
                                       stuck={layerStuck} onRecomputeStuck={recomputeStuckLayer} onDropStuck={dropStuckLayer}
                                       onRestoreBefore={(r) => void restoreBeforeRound(r)} onUndoRound={(r) => void undoRoundOnly(r)} /> },
            // Plan = done criteria (criteria) + contents (each section's status) + writing outline + what each round did (execution). Criterion 3: the plan must be visible —
            // always visible in the right pane beats pushing the body down. The harness switches here automatically when it starts.



            // the previous note's leftover `agentRounds`, while none of the body's four blocks could be drawn on a virtual page,

            // while `RightPane`'s own comment said "don't leave blanks" — that `emptyHint` path was unreachable at the time.



            { id: 'plan', title: t('Plan'), icon: 'bx-target-lock', alwaysShown: true,
              badge: planTabContent({ hasNote: !!current, running: loading === 'note-harness' || !!harness?.running,
                                      rounds: agentRounds.length, beats: beats.length }).badge || undefined,
              hasContent: planTabContent({ hasNote: !!current, running: loading === 'note-harness' || !!harness?.running,
                                           rounds: agentRounds.length, beats: beats.length }).has,
              emptyHint: PLAN_EMPTY_HINT,
              // Once running, round cards go first: the outline is a screen-high static text, and during the run users want to see

              // When not running: criteria → contents → outline → execution — then planning is the protagonist.
              body: (() => {
                const busy = loading === 'note-harness' || !!harness?.running || !!pausedRun
                const checks = current && (
                  <PlanChecks key="checks" done={intent.done} content={content} checked={intent.checked ?? []}
                    onToggle={(text, on) => {
                      const was = intent.checked ?? []
                      const next = on ? Array.from(new Set([...was, text])) : was.filter((t) => t !== text)
                      saveIntent({ ...intent, source: intent.source || 'user', checked: next })
                    }}
                    onEdit={() => setWorkflowPicker({ resume: false, focus: 'done' })} />
                )
                const outline = current && (
                  <div key="outline">
                    <h2>{t('Outline')}</h2>
                    <DocumentOutline content={content} viewRef={editorViewRef} withStatus />
                  </div>
                )
                const skeleton = current && (
                  <SkeletonPanel
                    key="skeleton"
                    spine={spine}
                    beats={beats}
                    beatCoverage={beatCoverage}
                    notes={skeletonNotes}
                    loading={loading === 'skeleton'}
                    onRun={runSkeleton}
                    onStop={stopSkeleton}
                    onJumpLine={jumpToLine}
                  />
                )
                const activity = (current || loading === 'note-harness' || harness?.running) && <AgentActivity
                  key="activity"
                  rounds={agentRounds}
                  status={loading === 'note-harness' || pausedRun ? noteHarnessStatus : ''}
                  running={loading === 'note-harness'}
                />
                return <div className="stack">{busy ? [activity, outline, checks, skeleton] : [checks, outline, skeleton, activity]}</div>
              })() },
            { id: 'revisions', title: t('Revision'), icon: 'bx-edit', badge: revisions.length || undefined,
              hasContent: revisions.length > 0, emptyHint: t('No pending revisions for this note.'),
              body: (
                <RevisionPanel
                  revisions={revisions}
                  content={content}
                  loading={loading === 'edit'}
                  onAccept={acceptRevision}
                  onReject={(r) => setRevisions((rs) => rs.filter((x) => x.id !== r.id))}
                  onRun={() => {}}
                />
              ) },
            { id: 'trace', title: t('Trace'), icon: 'bx-git-commit', hasContent: !!currentTrace,
              badge: currentTrace?.facts.length || undefined,
              body: currentTrace ? (
                <div className="stack">
                  {}
                  {!!verifyScopeLine(currentTrace.passage ?? '', !!currentTrace.passage && !content.includes(currentTrace.passage)) && (
                    <p className="muted verify-scope" style={{ margin: 0, fontSize: 'var(--t-sm)' }}>
                      {}
                      {jumpToPassage(currentTrace.passage)
                        ? <span className="scope-jump" title={t('Jump back to this passage')} {...clickable(jumpToPassage(currentTrace.passage)!)}>
                            {verifyScopeLine(currentTrace.passage ?? '', !!currentTrace.passage && !content.includes(currentTrace.passage))}
                          </span>
                        : verifyScopeLine(currentTrace.passage ?? '', !!currentTrace.passage && !content.includes(currentTrace.passage))}
                    </p>
                  )}
                  <TraceAnswer answer={currentTrace.answer} facts={currentTrace.facts} onInsert={insertAtCursor} />
                  {}
                  {!!traceRecallHint(currentTrace.facts.length, currentTrace.recalled) && (
                    <p className="muted" style={{ margin: 0, fontSize: 'var(--t-sm)' }}>
                      {traceRecallHint(currentTrace.facts.length, currentTrace.recalled)}
                    </p>
                  )}
                </div>
              ) : null },
          ] as PaneTab[]}
        />
      </div>
      )}
        </div>{/* center-pane */}
      </div>{/* rest-pane */}
      </div>{/* shell-main */}

      {/* Status bar. Shows **what is happening right now** — which round the harness is on, whether the backend is connected.
          Criterion 3 (high automation) requires the automated process to be visible; an indicator that only spins
          says nothing. */}
      <div className="status-bar">
        {/* Breadcrumbs: where the current note is in the tree. After cloning the same note is in several places; this is the only thing that
            says "which copy you're looking at" (Trilium StatusBar's Breadcrumb). */}
        <span className="breadcrumb status-crumbs">
          {crumbs.length === 0
            ? <span>{t('{n} notes total', { n: notes.length })}</span>
            : crumbs.map((r, i) => (
              <span key={r.id}>
                {i > 0 && <span className="muted"> / </span>}
                {i === crumbs.length - 1
                  ? <b>{displayTitle(r)}</b>
                  : <a href="#" onClick={(e) => { e.preventDefault(); openFromTree(r.note_id) }}>{displayTitle(r)}</a>}
              </span>
            ))}
        </span>
        {loading === 'note-harness' && noteHarnessStatus && (
          <span style={{ color: 'var(--accent)' }}><Icon n="bx-bot" /> {noteHarnessStatus}</span>
        )}
        {pausedRun && <span style={{ color: 'var(--accent)' }}><Icon n="bx-pause-circle" /> {t('Waiting for your review')}</span>}
        {harness?.running && <span style={{ color: 'var(--accent)' }}><Icon n="bx-folder-open" /> {harness.folderName}</span>}
        <span style={{ marginInlineStart: 'auto', display: 'inline-flex', gap: 12, alignItems: 'center' }}>
          {jobInfo && <span className="muted"><span className="spinner" /> {t('Saving to the knowledge base…')}{jobInfo.total > 0 ? ` ${t('chunk {i}/{total}', { i: Math.min(jobInfo.done + 1, jobInfo.total), total: jobInfo.total })}` : ''}{jobInfo.eta > 0 ? ` · ${t('about {eta} left', { eta: jobInfo.eta < 90 ? t('{n} s', { n: jobInfo.eta }) : t('{n} min', { n: Math.round(jobInfo.eta / 60) }) })}` : ''}{jobInfo.facts > 0 ? ` · ${t('{n} extracted', { n: jobInfo.facts })}` : ''}
            {}
            {jobInfo.status === 'cancelling'
              ? <>{' '}· {t('cancelling (waiting for this chunk’s model call to finish)')}</>
              : <>{' '}<button className="linklike" title={t('Cancel this save to knowledge base (what was extracted is kept)')} onClick={() => { void api.cancelJob(job).catch((e) => toast(t('Could not cancel: {err}', { err: friendlyError(e) }), 'error')) }}>{t('Cancel')}</button></>}
          </span>}
          {/* The red text is clickable: on first launch of an installed package, or a new machine without a model configured, red text only saying "unreachable" leaves users not knowing where to fix it */}
          {healthMsg && (
            <button className="health-bad linklike"
                    title={healthMsg === NOT_CONFIGURED
                      ? t('No model configured yet: open Settings, choose “Local model” and fill in the address and model name, or choose “OpenAI compatible” and fill in a key')
                      : t('Open Settings to fill in the model address / key')}
                    onClick={() => void openVirtual('app:settings', t('Settings'))}>
              <Icon n="bx-error" /> {healthMsg} · {t('Go to Settings')}
            </button>
          )}
          {asrOffline && <span className="muted" title={t('Voice service unreachable: {offline}. Recording transcription is unavailable; everything else works.', { offline: asrOffline })}><Icon n="bx-microphone-off" /> {t('Voice offline')}</span>}
        </span>
        {current && <span className="muted">{t('{n} chars', { n: wordCount(content) })}{wordCount(content) > 0 && <> · {t('about {n} min', { n: readingMinutes(wordCount(content)) })}</>}</span>}
      </div>
    </div>
  )
}
