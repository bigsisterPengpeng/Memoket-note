"""Request/response models."""

from __future__ import annotations

from typing import Literal

import re

from pydantic import BaseModel, Field, field_validator

from ..util import i18n
from ..editor.intent import WORKFLOW_LABEL


# ---------------------------------------------------------------- notes

# A title is one line: the tree, tabs and breadcrumbs all draw it as one line. The API used to

TITLE_MAX = 200


def _one_line_title(v: str) -> str:
    return " ".join((v or "").split())[:TITLE_MAX]


class NoteIn(BaseModel):
    title: str = ""
    content: str = ""

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return _one_line_title(v)


class NoteIntent(BaseModel):
    """Document intent (P9, agent-native-editor §3.1): what this note is for. Three fields, one line each;
    source = user (typed by the user or a workflow they chose) / empty; prefill is kept only for old data."""
    goal: str = ""
    reader: str = ""
    done: str = ""
    # The template identity the user chose. The visible fields are still only the three above; this one
    # carries the scenario's quality contract into the Harness.
    workflow: str = Field(default="", json_schema_extra={"enum": ["", *WORKFLOW_LABEL]})
    source: Literal["", "prefill", "user"] = ""

    # only the ones code cannot judge need a human tick
    checked: list[str] = []

    @field_validator("workflow")
    @classmethod
    def _workflow(cls, value: str) -> str:
        if value and value not in WORKFLOW_LABEL:
            raise ValueError("Unknown writing workflow")
        return value


class NoteIntentIn(NoteIntent):
    pass


class TrayItemIn(BaseModel):
    """One entry of the material tray (P14, agent-native-editor §3.4). kind: note = another note (ref_id is its id) /
    fact = a fact in the knowledge base (ref_id is the fact id) / import = an imported passage / selection = a passage clipped from elsewhere.
    excerpt is the part that goes into the prompt (capped on the backend at `store.TRAY_EXCERPT_MAX`)."""
    id: str = ""
    kind: Literal["note", "fact", "import", "selection"]
    ref_id: str = ""
    title: str = ""
    excerpt: str = ""


class TrayItem(TrayItemIn):
    position: int = 0
    added_at: str = ""


class TrayIn(BaseModel):
    """The whole tray (order = array order). Add one / remove one / reorder are all a PUT of the whole tray —
    the tray holds at most 24 entries, so the whole thing is simpler than a patch."""
    items: list[TrayItemIn] = Field(default_factory=list)


class TrayOut(BaseModel):
    items: list[TrayItem] = Field(default_factory=list)


class TrayClipIn(BaseModel):
    """Web clip into the tray (P15 #3): one URL. The article body is fetched and appended to the end of
    the tray as an `import` entry."""
    url: str


class Note(BaseModel):
    # Whether it has been ingested (empty = no). The frontend uses it to tell "changed but not synced"
    # and to decide whether to auto-sync.
    ingested_at: str = ""
    # Where it was imported from (obsidian / notion / apple / evernote / feishu...), the stable id on
    # the source side, and the last import time
    source: str = ""
    source_id: str = ""
    imported_at: str = ""

    id: str
    user_id: str
    title: str
    content: str
    pinned: bool = False
    # Note icon (boxicons class name, empty = default)
    icon: str = ""
    # The writing skeleton travels with the note. It used to live only in frontend memory: switching
    # notes / refreshing / infinite continuation auto-following to the next page lost it — and the
    # harness uses it as the main-line reference every round.
    spine: str = ""
    beats: list[str] = Field(default_factory=list)

    intent: NoteIntent = Field(default_factory=NoteIntent)
    created_at: str
    updated_at: str


class NoteIconIn(BaseModel):
    """A boxicons class name (like bx-rocket) or the empty string. Only this one shape is accepted:
    the icon name goes into className verbatim."""
    icon: str = ""

    @field_validator("icon")
    @classmethod
    def _shape(cls, v: str) -> str:
        v = (v or "").strip()
        if v and not re.fullmatch(r"bxs?-[a-z0-9-]{1,40}", v):
            raise ValueError(i18n.msg("The icon name must be a boxicons class name, e.g. bx-rocket"))
        return v


class ComposeBlockIn(BaseModel):
    """Block generation invoked with `/`. cursor is the character position of the caret in the body —
    only a stretch before and after it is taken as context, not the whole note (the whole note makes the
    model continue the tail of the document instead of filling this position)."""

    note_id: str = ""
    title: str = ""
    content: str = ""
    cursor: int = 0
    mode: str = "prompt"
    prompt: str = ""
    scope: str = "all"      # memory scope
    # The passage the user selected. Given = "do something to this passage" (right-click -> custom prompt);
    # not given = "insert a block here at the caret" (`/`). Same harness, different scope.
    selection: str = ""

    # (`hooks/block._system`)
    intent: str = ""

    # Empty tray -> 400, without spending a model call.
    from_tray: bool = False


class SkeletonSaveIn(BaseModel):
    spine: str = ""
    beats: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- note tree
# Following Trilium: the edges of the tree are branches, not a parent field on the note. A note with
# several branches is a "clone" — it grows in several places of the tree at once. So the subject of the
# operations below is the **branch** (which note, under which parent), not the note.

class TreeRow(BaseModel):
    """One node of the tree = one branch + the display info of that note."""
    id: str                  # branch id
    note_id: str
    parent_note_id: str      # 'root' means hanging off the tree root
    position: int
    is_expanded: bool = False
    title: str
    # Start of the body. When the title is empty or still a placeholder like "Untitled", the tree
    # uses this as the display name.
    preview: str = ""
    # The link to the knowledge base, visible right on the tree (see docs/kb-fusion-design.md):
    # how many facts it cites and when it was ingested. At a glance you see which notes are
    # "grounded" and which are still drafts.
    cite_count: int = 0
    ingested_at: str = ""
    pinned: bool = False
    icon: str = ""
    # Where this note came from: obsidian / notion / feishu / apple / plan (sections generated by a
    # writing plan); empty = written by the user. The tree picks the default icon by it. `created_at`
    # is not here — see docs/sidebar-ia-plan.md §3.
    source: str = ""
    updated_at: str
    child_count: int = 0
    # How many branches this note has in total. >1 means a clone and the tree must mark it — the user
    # needs to know that editing it here changes it elsewhere too.
    branch_count: int = 1
    # Only for nodes of the knowledge-base virtual subtree: how many facts sit under this topic /
    # entity / month (topics include the closure of their subtopics). Always 0 for real notes.
    fact_count: int = 0


class Snippet(BaseModel):
    before: str
    hit: str
    after: str


class NoteBrief(BaseModel):
    """Lightweight row for ⌘K / `[[` completion: no full body."""
    id: str
    title: str
    updated_at: str
    pinned: bool = False
    icon: str = ""           # note icon (boxicons class name, empty = default)
    preview: str = ""
    has_body: bool = True
    first_body: str = ""      # first non-heading body line; tells same-titled notes apart
    snippet: Snippet | None = None


class NoteBriefPage(BaseModel):
    notes: list[NoteBrief]
    total: int


class NoteCreateIn(BaseModel):
    title: str = ""
    content: str = ""

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return _one_line_title(v)
    # Which parent to create it under. A note is always created at some position in the tree; there is
    # no "create first, place later" intermediate state — unplaced, it exists in the DB but the user
    # cannot see it.
    parent_note_id: str = "root"


class BranchAttachIn(BaseModel):
    """Hang an existing note at another position = clone."""
    note_id: str
    parent_note_id: str = "root"


class BranchMoveIn(BaseModel):
    note_id: str
    from_parent_id: str
    to_parent_id: str
    position: int | None = None


class BranchReorderIn(BaseModel):
    parent_note_id: str
    order: list[str]


class BranchExpandIn(BaseModel):
    note_id: str
    parent_note_id: str
    expanded: bool


# ---------------------------------------------------------------- infinite-continuation plan

class WritingPlanStartIn(BaseModel):
    parent_note_id: str
    goal: str = ""
    scope: str = "all"      # memory scope (database/kb/scope.py)


class WritingSection(BaseModel):
    id: str
    plan_id: str
    idx: int
    title: str
    status: Literal["pending", "in_progress", "done"] = "pending"
    note_id: str = ""
    summary: str = ""
    created_at: str


class WritingPlan(BaseModel):
    id: str
    user_id: str
    parent_note_id: str
    goal: str
    status: Literal["active", "done", "abandoned"] = "active"
    doc_note_id: str = ""
    created_at: str
    updated_at: str


class WritingPlanOut(BaseModel):
    plan: WritingPlan | None = None
    sections: list[WritingSection] = Field(default_factory=list)


class WritingPlanRunIn(BaseModel):
    parent_note_id: str
    scope: str = "all"      # memory scope: each section only draws material from this tier


# ---------------------------------------------------------------- single-note harness

class NoteHarnessRunIn(BaseModel):
    """``mode`` decides which loop this run is:

    ``write`` (default) — alternate revising and continuing until the structural beats are substantively covered.
    ``polish`` — **revise only, never write**: revise + score repeatedly until the "already-written content
    itself" dimensions all pass. This fills what the "generate revision suggestions" feature always lacked —
    it used to be a one-shot call: one click gave at most 6 suggestions and ended; no scoring, no rounds,
    **nothing telling you this is good enough**, and you could keep clicking and it kept giving.
    """

    note_id: str
    content: str
    mode: Literal["write", "polish"] = "write"
    spine: str = ""
    beats: list[str] = Field(default_factory=list)


    # `e78306202d78` running 15 rounds, 385 seconds, 421k tokens. Round count is a property of the mode,
    # not a per-request parameter; passing it explicitly is for scripts / tests only, still capped by
    # `MAX_ROUNDS_CAP`.
    max_rounds: int | None = None

    # **right now** (persisting has an 800ms delay); omitted = use `notes.intent` from the DB.
    intent: str = ""
    # Stop after each round and wait for the user to accept/reject item by item. **It is the user's
    # choice, not a property of the feature** — the same person wants it on an important document and
    # not on a draft.
    review_each_round: bool = False
    scope: str = "all"      # memory scope (database/kb/scope.py); material is drawn only from this tier


class HarnessResumeIn(BaseModel):
    """What comes back after the user has dealt with the changes.

    ``content`` is **the body in the editor after accepting/rejecting item by item** — the user's
    decisions happen in the editor; having the backend merge again from a list of hunk ids would be the
    same merge implemented twice, and what the user actually sees is the copy in the browser.
    """

    content: str = ""
    # The user decided not to write further: save and wrap up, no more rounds.
    stop: bool = False


# ---------------------------------------------------------------- skill system

class SkillIn(BaseModel):
    name: str
    # Directory name, also the ``name`` in SKILL.md — the spec only allows lowercase letters / digits /
    # hyphens. The frontend may omit it and the backend derives it from name; when a Chinese name cannot
    # produce a legal slug it falls back to a stable hash, and the readable name goes into the body's
    # first-level heading (the place the spec leaves for it).
    slug: str = ""
    description: str = ""
    scopes: list[str] = Field(default_factory=list)
    content: str
    enabled: bool = True


class Skill(BaseModel):
    """The outward shape of a skill directory.

    ``id`` is the slug (directory name) — a skill is no longer a DB row and has no separate primary key.
    The frontend has always addressed by ``id``, so the field stays; only its meaning changed from
    "random id" to "directory name".
    """

    id: str
    slug: str
    name: str
    description: str
    scopes: list[str]
    content: str
    enabled: bool
    idx: int
    builtin: bool
    source: str = "user"
    sandbox: str = "none"


class SkillScope(BaseModel):
    value: str
    label: str


class SkillReorderIn(BaseModel):
    ordered_ids: list[str]


class SkillGenerateIn(BaseModel):
    goal: str
    scope_hint: str = ""


# ---------------------------------------------------------------- personal preferences

class ProfileEntryIn(BaseModel):
    text: str


class ProfileEntry(BaseModel):
    id: str
    user_id: str
    text: str
    created_at: str


# ---------------------------------------------------------------- LLM provider config

class ProviderConfigIn(BaseModel):
    provider: str  # any preset id in util/providers.PROVIDERS (legacy "local" / "gpt" unchanged; gpt = custom OpenAI-compatible endpoint)
    # new-style fields: key / model / address **of the `provider` entry itself**, used by every preset.
    # omitted = keep; api_key '' = clear; base_url '' = preset default. The legacy gpt_* / local_* fields still work.
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    gpt_api_key: str | None = None  # omitted = keep the saved value, see store.set_provider_config
    gpt_model: str | None = None
    gpt_base_url: str | None = None
    asr_base_url: str | None = None  # whisper.cpp server; empty string = clear, fall back to .env
    # Speech-to-text provider "whisper" | "assemblyai" | "speechmatics". Omitted = keep;
    # keys: omitted / blank = keep; regions: empty string = provider default.
    asr_provider: str | None = None
    assemblyai_api_key: str | None = None
    assemblyai_region: str | None = None
    speechmatics_api_key: str | None = None
    speechmatics_region: str | None = None
    auto_sync_notes: bool | None = None

    local_base_url: str | None = None
    local_model: str | None = None
    local_api_key: str | None = None
    # Vision: omitted = keep; empty string = clear -> follow the writing model
    vision_base_url: str | None = None
    vision_model: str | None = None
    vision_api_key: str | None = None


class ProviderTestIn(BaseModel):
    """"Test" (P19 #1): really send one request and show the result on the spot. `api_key` omitted = use the key
    already saved for the `saved_key_of` entry."""
    kind: str                      # "llm" | "vision" | "asr"
    base_url: str
    model: str = ""
    api_key: str | None = None
    saved_key_of: str = ""         # preset id ("local" / "gpt" / "openai" / ...) | "vision"
    provider: str = ""
    asr_provider: str = ""
    region: str = ""


class ProviderPresetOut(BaseModel):
    """One entry of the settings dropdown (a `util/providers.py` preset + what is saved for it). **Never the key itself**."""
    id: str
    label: str
    base_url: str                  # factory default address (the `local` entry: .env / factory default); UI placeholder
    models: list[str] = Field(default_factory=list)   # suggested model names (<datalist>), not exhaustive
    needs_key: bool = True
    family: str = "compatible"     # openai | compatible | local
    group: str = "hosted"          # hosted | local | custom
    docs: str = ""
    key_set: bool = False
    key_preview: str = ""          # last four characters, e.g. "...ab12"
    model: str = ""                # saved model name for this entry ('' = not set)
    base_url_saved: str = ""       # saved address for this entry ('' = default)


class ProviderTestOut(BaseModel):
    ok: bool
    message: str
    models: list[str] = Field(default_factory=list)
    model_found: bool | None = None   # whether the typed model is in the /models list; list unavailable = None
    elapsed_ms: int = 0


class ProviderConfigOut(BaseModel):
    provider: str
    gpt_model: str
    gpt_base_url: str
    asr_base_url: str        # what the user typed (empty = not set, using the default)
    asr_default_url: str     # .env default, shown as a placeholder in the UI
    # Speech-to-text provider (stored value, else the .env default) and the hosted providers'
    # key-set flags / regions. Keys themselves are never returned.
    asr_provider: str = "whisper"
    assemblyai_api_key_set: bool = False
    assemblyai_api_key_preview: str = ""
    assemblyai_region: str = "us"
    speechmatics_api_key_set: bool = False
    speechmatics_api_key_preview: str = ""
    speechmatics_region: str = "eu"
    auto_sync_notes: bool = False
    # The vision endpoint (screen-activity descriptions go through it; a different thing from the writing
    # LLM). **Read-only**: it is deployment config, like `asr_default_url`. It is shown because the

    # otherwise it is just reassurance.
    vision_base_url: str = ""
    vision_model: str = ""
    vision_api_key_set: bool = False
    # Whether the vision field "follows the writing model" (not set in settings, not overridden by .env)
    vision_follows_llm: bool = True
    # The vision endpoint actually in effect (when following = the writing model's); shown read-only
    vision_active_url: str = ""
    vision_active_model: str = ""

    local_base_url: str = ""        # what the user typed (empty = using the default)
    local_model: str = ""
    local_api_key_set: bool = False
    local_default_url: str = ""     # .env / factory default, shown as a placeholder in the UI
    local_default_model: str = ""
    # Whether a model has been configured (llm_configured): if not, the status bar says "no model
    # configured yet" instead of reporting an address
    configured: bool = False
    configured_source: str = "default"
    # The writing model actually in effect (no key)
    active_url: str = ""
    active_model: str = ""
    active_provider: str = ""      # id of the entry actually in effect (a key-requiring entry without a key falls back to 'local')
    active_family: str = ""        # openai | compatible | local
    # every preset + what is saved for it (keys only as "set" + last four characters)
    providers: list[ProviderPresetOut] = Field(default_factory=list)
    # The real key is never sent back to the frontend — only "is it saved" and "the last few characters",
    # used to show a confirmation like "set sk-...ab12"; the full key is neither needed nor should be exposed
    gpt_api_key_set: bool
    gpt_api_key_preview: str


# ---------------------------------------------------------------- memory

class FactOut(BaseModel):
    id: str
    text: str
    when: str = ""
    kind: str = ""
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class TopicOut(BaseModel):
    code: str
    parents: list[str] = Field(default_factory=list)
    status: str = "candidate"
    aliases: list[str] = Field(default_factory=list)
    fact_count: int = 0


class TopicCreateIn(BaseModel):
    code: str
    parent: str = ""
    aliases: list[str] = Field(default_factory=list)


class EntityOut(BaseModel):
    code: str
    name: str = ""
    type: str = ""
    aliases: list[str] = Field(default_factory=list)
    relations: list[tuple[str, str]] = Field(default_factory=list)
    fact_count: int = 0


class TopicEntityLink(BaseModel):
    topic: str
    entity: str
    weight: int


class NoteGraphOut(BaseModel):
    """What surrounds this note: the facts its body cites + the facts it contributed, and which topics /
    entities each hangs on (for the local graph)."""
    facts: int = 0
    topics: list[TopicOut] = Field(default_factory=list)
    entities: list[EntityOut] = Field(default_factory=list)
    links: list[TopicEntityLink] = Field(default_factory=list)


class SourceLineOut(BaseModel):
    id: str
    unit: str
    date: str = ""
    who: str = ""
    text: str


class CitingNoteOut(BaseModel):
    """A note that cites a given fact. Used by the right-hand "backlinks" panel."""
    id: str
    title: str
    updated_at: str
    preview: str = ""      # when the title is "Untitled" the frontend uses the first body line as display name
    icon: str = ""         # note icon (boxicons class name, empty = default)


class RevisionOut(BaseModel):
    """Summary of one revision (for lists, no body)."""
    id: str
    note_id: str
    title: str
    reason: str            # auto / manual / before_restore / harness / round / run_end
    created_at: str
    chars: int

    # was burned into the body; the closing row = after the last round (a normal finish is `harness`,

    # Empty / 0 = a revision unrelated to any run.
    run_id: str = ""
    round_no: int = 0


class RevisionFullOut(RevisionOut):
    content: str


class ChangeHunkIn(BaseModel):
    """One change (P39). For `state` see `store.HUNK_STATES`.

    Coordinates are those **at the time this version was saved**, used together with the layer's
    `content_tag`: if the body is unchanged it goes back by coordinates; if it changed, it is relocated by
    `del`/`ins` + the `before`/`after` context snippets (if they do not match, say so plainly; no guessing).
    """
    k: int = 0
    from_: int = Field(0, alias="from")
    to: int = 0
    delete: str = Field("", alias="del")
    ins: str = ""
    state: str = "pending"
    soft: bool = False
    before: str = ""
    after: str = ""

    model_config = {"populate_by_name": True}


class ChangeLayerIn(BaseModel):
    """One layer of pending changes (P39). See the table-creation comment on `store.note_change_layers`."""
    id: str = ""
    label: str = ""
    source: str = "other"
    run_id: str = ""
    round_no: int = 0
    seq: int = 0
    state: str = "on"
    at: str = ""
    content_tag: str = ""
    hunks: list[ChangeHunkIn] = Field(default_factory=list)


class ChangeLayersIn(BaseModel):
    layers: list[ChangeLayerIn] = Field(default_factory=list)


class ChangeLayersOut(BaseModel):
    layers: list[ChangeLayerIn] = Field(default_factory=list)


class RestoredRound(BaseModel):
    """**The skeleton of one round** read back from `harness_rounds` (P101 A).

    **It is not the whole round card** — the details on the card (written body / each tool call / skills /
    verdicts / discards / strategy reasoning / phase output) have not a single character in the DB; each is
    named in `NoteRoundsOut.missing`, and the frontend marks them on the card truthfully.
    """
    round: int = 0
    #: `{dimension: level}`. **The level is an int, not `{level, note}`** — the verdict was not persisted.
    scores: dict[str, int] = Field(default_factory=dict)
    status: str = ""
    weakest: str = ""
    contentLen: int = 0
    toolCalls: int = 0
    repeatCalls: int = 0
    revisionsProposed: int = 0
    revisionsDropped: int = 0
    depthDropped: int = 0
    factsNew: int = 0
    factsTotal: int = 0
    #: For all three columns **`-1` = this round never reached that step**, `0` = computed, nothing citable.
    #: Hence the default is `-1`, not `0` (the two must never become the same number).
    citeLocated: int = -1
    citeMarked: int = -1
    citeMatched: int = -1
    firedChecks: str = ""
    at: str = ""


class NoteRoundsOut(BaseModel):
    """Round skeletons of **the most recent run** of this note (P101 A · read-only).

    `reason` has four values, **kept apart because "cannot select" != "does not exist"**:
      · `ok` — read successfully;
      · `no_rounds` — this note has never run a single round (truly nothing in the DB);
      · `no_run_id` — there are rounds, but the recent ones are from the old path without a `Ledger`
        (`run_id` empty), so they cannot be split by run => **not shown**. This is **not** "this note never ran".
      · `run_without_rounds` — the run was interrupted before the first retrieval finished; there is a stop
        record but no round skeleton => **show the reason, never fake a card**.
    """
    runId: str = ""
    at: str = ""
    status: str = ""
    stopped: str = ""
    rounds: list[RestoredRound] = Field(default_factory=list)
    reason: str = "ok"
    runsTotal: int = 0
    roundsTotal: int = 0
    #: What the card has and the DB does not, item by item. **The frontend shows it as-is.**
    missing: list[str] = Field(default_factory=list)


class ChangeLayerDropped(BaseModel):
    label: str = ""
    at: str = ""
    why: str = ""


class ChangeLayersSaveOut(BaseModel):
    """**Eviction must be loud**: what was not saved and why, returned as-is for the frontend to say so."""
    saved: int = 0
    evicted: list[ChangeLayerDropped] = Field(default_factory=list)
    rejected: list[ChangeLayerDropped] = Field(default_factory=list)


class ChangeLayersBurnOut(BaseModel):
    """"Accept all" = how many layers were cleared after burning into the body (P41 #6). If layers remain
    in the DB after burning, `store.burn_change_layers` raises on the spot and never gets here."""
    dropped: int = 0


class WritingFeedbackItem(BaseModel):
    layer_id: str = ""
    hunk_key: int = 0
    run_id: str = ""
    source: str = "other"
    label: str = ""
    decision: str = ""
    del_text: str = ""
    ins_text: str = ""
    decided_at: str = ""


class WritingFeedbackLatest(BaseModel):
    layer_id: str = ""
    label: str = ""
    accepted: int = 0
    reverted: int = 0
    decided_at: str = ""


class HarnessRetention(BaseModel):
    run_id: str = ""
    generated_chars: int = 0
    kept_chars: int = 0
    kept_percent: int = 0
    changed_section: str = ""
    edited_at: str = ""


class WritingFeedbackOut(BaseModel):
    accepted: int = 0
    reverted: int = 0
    decided: int = 0
    latest: WritingFeedbackLatest = Field(default_factory=WritingFeedbackLatest)
    items: list[WritingFeedbackItem] = Field(default_factory=list)
    run_retention: HarnessRetention | None = None


class NoteLinksOut(BaseModel):
    """Links between notes: `[title](note://<id>)`. outgoing = links out of this note, backlinks = links into it."""
    outgoing: list[CitingNoteOut]
    backlinks: list[CitingNoteOut]
    # Note ids linked from the body that no longer exist (deleted / imported from another library): the
    # panel lists them so they can be turned into plain text with one click
    dangling: list[str] = Field(default_factory=list)


class FactPeekOut(BaseModel):
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)   # entity display names, one-to-one with entities (chips show Facebook, not facebook)
    """What the inline source popover needs: one fact + its original words.

    `sources` is at most three — the popover is for **a glance**, not a reader; to see everything use the
    knowledge-base panel.
    """
    id: str
    text: str
    when: str = ""
    kind: str = ""
    sources: list[str] = Field(default_factory=list)


class FactDetailOut(BaseModel):
    """Row for the facts table — compared with FactOut it adds who/conf/unit and drops sources (fetched on
    demand via /facts/{id}/sources, so the list page does not look up the original text for every row)."""
    id: str
    text: str
    when: str = ""
    kind: str = ""
    who: str = ""
    conf: str = ""
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)   # entity display names, one-to-one with entities (chips show Facebook, not facebook)
    unit: str = ""
    superseded_by: str = ""
    merged: bool = False


class FactsPageOut(BaseModel):
    facts: list[FactDetailOut]
    total: int
    limit: int
    offset: int


class TimelineBucket(BaseModel):
    date: str
    units: int = 0
    facts: int = 0


class TimelineOut(BaseModel):
    buckets: list[TimelineBucket]


class StatsOut(BaseModel):
    facts: int
    topics: int
    entities: int
    units: int = 0
    lines: int = 0
    speakers: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    codebook: str


class RecallIn(BaseModel):
    query: str
    limit: int = 8
    scope: str = "all"      # memory scope: all / notes / meetings / imports (database/kb/scope.py)
    relaxed: bool = False    # the user actively clicks "widen the search" after an empty result; never replaces the evidence gate of auto-recall


class EvidenceOut(BaseModel):
    """One recall evidence term + why it counts as evidence (P32 / plan §2 A5).

    `why`: `vocab` = a vocabulary entry in the knowledge base; `span` = a whole stretch of original words this
    long matched verbatim; `pair` = not strong enough alone, only counts when it hits together with another
    term. `units` = how many records in the DB mention it (df).
    """
    term: str
    why: str = "pair"
    units: int = 0


class RecallOut(BaseModel):
    facts: list[FactOut]
    took_ms: float
    terms: list[str] = Field(default_factory=list)
    relaxed: bool = False
    can_expand: bool = False

    # said "matched: decide again"; it described correctly what it was doing, and what it was doing was wrong.

    # the whole DB land here); the frontend says so truthfully and **must not** fall back to the more
    # fragmented `terms`; `None` = **not judged** this time (the judge itself raised / an old backend lacks
    # the field), and then falling back to `terms` is right. Default `None`: callers that do not fill this
    # field never judged.
    evidence: list[EvidenceOut] | None = None
    # The knowledge base has no facts at all. **"Nothing found" and "the library is empty" must be told


    # related to 'prototype' in the knowledge base" — misleading for someone who has not imported anything.
    kb_empty: bool = False

    # are words, but no record hits two different words at once (long queries are not forced); "" = there
    # are results or the reason is unclear.
    why_empty: str = ""


class IngestTextIn(BaseModel):
    content: str
    title: str = ""
    source: str = "doc"
    # Date of the original content (YYYY-MM-DD). **Bulk imports must include it** — otherwise everything is
    # recorded as the import day, years of a user's notes collapse onto one day and the timeline is ruined.
    # And the date of a fact is exactly what factual_grounding is judged on while writing (see
    # harness-architecture section 9, the root cause "time information of facts never entered the prompt").
    date: str = ""
    # Stable identifier on the source side (Notion page_id, Obsidian relative path, ENEX GUID...).
    # KITE rejects duplicate session_ids without spending an LLM call, so with a stable id
    # **re-running the import becomes an incremental sync automatically**; without one it falls back to a
    # random id, importing the same batch twice stores two copies in the knowledge base, and the second
    # copy pays for extraction again.
    source_id: str = ""
    # Sync: first delete the session this note was last ingested as, then re-extract (only meaningful for source="note")
    replace: bool = False


# Legal item statuses. Used by the frontend for label mapping, and as the write-side whitelist (see
# tests/test_importers.py::test_every_item_status_written_is_allowed_by_the_schema).
ITEM_STATUSES = ("queued", "extracting", "transcribing", "chunking",
                 "remembering", "done", "failed", "cancelled")


class IngestItemOut(BaseModel):
    """Progress of a single file in a batch job. Single-file jobs (/text /audio) produce no items; always an empty list."""
    id: str
    idx: int
    filename: str
    kind: str
    # The output uses str, not Literal. **Literal is a trap here**: if a single status written to the DB is
    # not in the enum, `GET /api/ingest/jobs` 500s entirely — one bad history row can keep the progress panel
    # from ever opening; the user sees "Processing..." stuck and Cancel does nothing.
    # What must be policed is the **write** side: tests/test_importers.py scans every set_item call and
    # ensures every status written is in ITEM_STATUSES.
    status: str
    facts: int = 0
    detail: str = ""
    chunks_total: int = 0
    chunks_done: int = 0
    # Which note this item became (empty = no note created: knowledge base only, or the item failed).

    note_id: str = ""


# Legal job statuses. "cancelling" = cancel received but the background work has not fully stopped (it may
# be stuck in an LLM call or the KITE write lock); the UI must truthfully say "stopping", not "processing".
JOB_STATUSES = ("queued", "running", "cancelling", "done", "error", "cancelled", "interrupted")


class IngestOut(BaseModel):
    job_id: str
    # Same as IngestItemOut.status: **the output uses str, not Literal**. A status not in the enum 500s the
    # whole endpoint, the UI hangs on "processing" and Cancel does nothing — this trap was hit twice tonight
    # (once for items, once for jobs), so both are now policed by a write-side whitelist + tests.
    status: str
    facts: int = 0
    detail: str = ""
    items: list[IngestItemOut] = Field(default_factory=list)
    # Progress / estimate / usage (store.job_progress): chunk counts, time remaining, time elapsed, estimated
    # tokens spent, the file currently being processed; resumable = interrupted by a service restart but the
    # payload is still there, so it can continue
    chunks_total: int = 0
    chunks_done: int = 0
    eta_s: int = 0
    elapsed_s: int = 0
    tokens_est: int = 0
    current: str = ""
    resumable: bool = False
    # The estimate before starting (from _queue): how many chunks in this batch, roughly how long, how many tokens
    estimate: dict = Field(default_factory=dict)


# ---------------------------------------------------------------- writing

class SkeletonIn(BaseModel):
    """Line 1: generate the main-line skeleton for the current writing."""
    content: str
    title: str = ""
    # The document intent sentence (`editor/intent.as_text`), appended to the first system paragraph;

    intent: str = ""


class SkeletonOut(BaseModel):
    """spine: one sentence, the core tension/question this piece is really dealing with — not the topic.
    beats: 3-6 structural/rhetorical functions ("establish the situation", "introduce the turn"), not content summaries.
    See SKELETON_SYSTEM in prompts.py."""
    spine: str = ""
    beats: list[str] = Field(default_factory=list)
    # Result of the deterministic check-up (plan 4.3, `harness/checks/skeleton.py`). **It does not block the
    # response**, it is shown with the skeleton — the skeleton is a one-shot product; whether to regenerate
    # is the user's call.
    notes: list[str] = Field(default_factory=list)
    took_ms: float


class Revision(BaseModel):
    """One track-changes revision. The frontend renders acceptable/rejectable marks from it.

    insert inserts **after** the anchor; insert_before inserts **before** the anchor — the latter is for
    "expand context" (adding content in front of the selected passage); without it, insert's constraint of
    "only after the anchor" cannot express "add in front"."""
    id: str
    op: Literal["insert", "delete", "replace", "insert_before"]
    anchor: str = ""          # the located passage in the original (for delete/replace/insert_before)
    # The **end** marker of the located passage. When given, the target is the whole stretch from the start
    # of anchor to the end of anchor_end, and anchor itself only needs to be a short start marker.
    # Why: anchor used to have to be "the complete original text to replace", so a 200-character paragraph
    # had to be echoed verbatim, and for replace the revised text was output again — the same passage in and
    # out once each. Output tokens convert directly into time; this was pure waste.
    anchor_end: str = ""
    text: str = ""            # new content (for insert/replace/insert_before)
    reason: str = ""
    sources: list[str] = Field(default_factory=list)


class EditOut(BaseModel):
    """A batch of track-changes revision suggestions.

    Right-click "rewrite / polish / expand context" share this one shape, matching the frontend's
    accept/reject UI — the three entry points do different things, but all produce "a few revisions you can
    pick one by one".
    """

    revisions: list[Revision]
    took_ms: float
    # When there are no suggestions, give a reason (e.g. "hit the length limit, JSON cut in half"); the
    # frontend shows it as-is; empty = the model truly gave no suggestions.
    note: str = ""
    # **"The model says it is not needed" and "the model failed to answer" are two different things**


    # context is needed." — **a sentence the model never said**. It was the frontend branch's `emptyNote`,
    # and this schema used to carry a value only for the "hit the length limit" case
    # (`compose._truncated_note`); **there was no third possibility**.
    # The criterion is narrow and only looks at shape: only when the reply **lacks even the expected keys**
    # (not a JSON object / no `text` or `before`/`after`) is it "could not extract". Keys present with empty
    # strings are the model answering in format "nothing to add in this direction" (`EXPAND_SYSTEM` says
    # explicitly "leave both as empty strings if neither is needed"); **that case must not count as failing
    # to answer**.
    unparsed: bool = False


class MagicTapIn(BaseModel):
    content: str
    spine: str = ""
    beats: list[str] = Field(default_factory=list)
    max_tokens: int = 1200
    # The body already after the caret. When present, "continue" inserts a passage in the middle: continue
    # from content, connect to following, and do not repeat what following already has. Empty = append to
    # the end (the original semantics).
    following: str = ""
    # Title: while the body is still short it is the only direction the model knows (smart continuation goes
    # through ctx.note_title; this continuation path did not carry it before)
    title: str = ""
    scope: str = "all"      # memory scope (same as RecallIn.scope)
    intent: str = ""

    # empty = no tray (old callers unchanged)
    note_id: str = ""


# ---------------------------------------------------------------- selected-text actions
# The three actions triggered by right-clicking selected text are all "given selection + context ->
# concrete revision suggestions"; they share the Revision model and the frontend accept/reject UI with
# line 2's revisions, instead of a separate display layer.

class RewriteIn(BaseModel):
    content: str
    selection: str
    intent: Literal["rewrite", "polish"] = "rewrite"
    spine: str = ""
    beats: list[str] = Field(default_factory=list)
    doc_intent: str = ""


class ExpandIn(BaseModel):
    content: str
    selection: str
    scope: str = "all"      # memory scope (database/kb/scope.py)
    intent: str = ""
    note_id: str = ""


class VerifyIn(BaseModel):
    content: str
    selection: str
    scope: str = "all"      # memory scope: lexical recall only looks at this tier; facts explicitly cited in the body are not limited
    intent: str = ""
    note_id: str = ""


class VerifyFinding(BaseModel):
    # Verdict values are the Chinese words the model is told to answer with: "contradicts", "supports",
    # "cannot tell". They are data matched against model output, not UI text.
    verdict: Literal['\u77db\u76fe', '\u652f\u6301', '\u65e0\u6cd5\u5224\u65ad']
    reason: str
    fact_id: str = ""
    fact_text: str = ""
    sources: list[str] = Field(default_factory=list)


class VerifyOut(BaseModel):
    """Distinguish absent evidence from a malformed model response.

    ``checked`` counts evidence supplied to the model. ``unparsed`` means its
    answer could not be interpreted; this must not be shown as missing evidence.
    """

    findings: list[VerifyFinding]
    took_ms: float
    # How many records were handed to the model to check this time. 0 = truly nothing related in the knowledge base.
    checked: int = 0
    # The model's answer yields no extractable judgement (wrong shape); different from "checked, nothing to say".
    unparsed: bool = False


class SlidesIn(BaseModel):
    """This note -> slides. `style`: `points` bullet version / `talk` speaker-script version —
    the two uses want exactly opposite page density, so they are separate rather than a toggle."""

    note_id: str = ""
    content: str
    title: str = ""
    style: Literal["points", "talk"] = "points"
    max_tokens: int = 3000


class DigestIn(BaseModel):
    """Generate a period review for a date range (or the last N days). Without date_from/date_to, days is used."""
    days: int = 7
    date_from: str = ""
    date_to: str = ""
    scope: str = "all"      # memory scope (database/kb/scope.py)


class DigestOut(BaseModel):
    summary: str
    fact_count: int
    date_from: str
    date_to: str
    took_ms: float


class TraceIn(BaseModel):
    """Input of "background & history": **only a passage of body text, no question**.

    The question is assembled by the backend — criterion 1: the user clicks a button, never writes a prompt.
    """
    passage: str
    limit: int = 10


class AskIn(BaseModel):
    """Ask the knowledge base explicitly. Goes through KITE's native planning: slow, but supports temporal reasoning."""
    question: str
    limit: int = 10


class AskOut(BaseModel):
    """Response of "background & history". **An empty `facts` has two completely different origins that must
    be told apart** (P41 #1 / P40 issue #1).

    P40 capture: on the same screen "verify" said about **the same passage** "the knowledge base has 6 related
    records", while "background & history" said "the knowledge base has no records related to this passage."
    — **the two panels contradicted each other, and the latter was false**. `facts` counts how many records
    KITE's own planning retrieval strung together, while that sentence talks about "whether the knowledge base
    has any". Exactly the same idea as `checked` in `VerifyOut`.
    """

    answer: str
    facts: list[FactOut] = Field(default_factory=list)
    # How many records **lexical recall** returned for the same passage (same path and same limit as "verify").
    # `None` = not measured this time (KITE strung something together, or another caller); only `0` means
    # "truly nothing in the knowledge base".
    recalled: int | None = None
    took_ms: float


# ---------------------------------------------------------------- screen activity
# The segments themselves live on the shell side (`<userData>/journey/<date>/segments.json`); this is only

# there is one; to see the image use `/api/journey/frame` — images are not kept by default, and if kept,
# only on this machine (daily-journey-plan §1).

class JourneySegment(BaseModel):
    # Index of this segment in that day's file. **Deleting a segment goes by it** — deleted positions in the
    # array are kept (removing them would shift every later index by one, so clicking delete on segment 5
    # would actually delete segment 6).
    i: int = 0
    start: str = ""
    end: str = ""
    app: str = ""
    title: str = ""
    desc: str = ""
    n: int = 0
    has_frame: bool = False
    # Whether there is the 256px thumbnail (the full image is deleted once the description is done, §1 ③).
    has_thumb: bool = False
    # **Why this segment will never get a description** (empty string = not its turn yet, not "cannot be

    # specific said"), it just was never handed to the UI — so the UI could only use `has_frame` as a stand-in


    # `has_frame=true` -> the button said "describe these 10 segments" -> clicking only returned "nothing left

    # **The criterion must keep its source**: if it cannot be filled, it cannot; do not make the UI guess.
    skip: str = ""


class JourneyDayOut(BaseModel):
    date: str
    segments: list[JourneySegment] = Field(default_factory=list)
    minutes: int = 0
    # The daily report already written (`<that day>/report.json`). Empty string if none — **never
    # auto-generated**: it is a model call; the user has to ask for it.
    report: str = ""
    # How many segments the report was written from, and when. **The report is a snapshot; the day is still
    # growing**: without these two numbers the user sees the morning's report in the afternoon with no hint
    # that it is stale.
    report_segments: int = 0
    report_at: str = ""
    # Result of the deterministic check-up of that report (`harness/checks/journey.py`, plan 8.2).
    # **Judged, not blocked** — stored in `report.json` together with the report, still there after a refresh.
    report_notes: list[str] = Field(default_factory=list)


class JourneyReportOut(BaseModel):
    date: str
    report: str = ""
    segments: int = 0
    report_at: str = ""
    # See `JourneyDayOut.report_notes`.
    notes: list[str] = Field(default_factory=list)
    took_ms: float = 0.0


class JourneySpanOut(BaseModel):
    date_from: str
    date_to: str
    days: int = 0
    """The days in this span without a daily report — written into the note body; the reader must know which days it was written from."""
    missing: list[str] = Field(default_factory=list)
    note_id: str = ""
    title: str = ""
    took_ms: float = 0.0


class JourneyDenyIn(BaseModel):
    apps: list[str] = Field(default_factory=list)
    words: list[str] = Field(default_factory=list)


class JourneyDenyOut(BaseModel):
    apps: list[str] = Field(default_factory=list)
    words: list[str] = Field(default_factory=list)
    # The built-in list **cannot be removed**; read-only, for display in the UI
    builtin_apps: list[str] = Field(default_factory=list)
    builtin_words: list[str] = Field(default_factory=list)


class JourneyRunOut(BaseModel):
    date: str
    described: int = 0
    ingested: int = 0
    skipped: int = 0
    left: int = 0
    removed_facts: int = 0
