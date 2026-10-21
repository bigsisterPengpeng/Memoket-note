"""Every feature's configuration, in one place.

Today these live in two: ``compose_block.MODES`` (six inline dicts) and
``harness_adapter.note_dimensions()`` / ``section_dimensions()``. Splitting
them meant "where do I add a dimension" had two answers depending on which
harness you were touching.

A Mode is pure data. Skills layer on top at runtime by producing a modified
copy, so nothing here may depend on anything only code can supply.
"""

from __future__ import annotations

import dataclasses

from .types import Dimension

from .checks import grounding_rules as grounding_check
from .checks import (chart_numbers_grounded, chart_readable, chart_restates_list,
                     charts_from_tools, citations_exist, citations_present, citations_hold,
                     heading_fits, language_consistent, material_thin, material_used,
                     no_audit_voice, no_echoed_text, no_fake_charts, no_foreign_script,
                     no_junk_tail, no_placeholder, output_not_json,
                     no_repeated_lists, no_restated_paragraph, no_same_sources_twice,
                     numbers_from_tools, outline_intact, section_budget,
                     table_columns_match, table_present, tail_clashes,
                     unsupported_specifics)
from .middleware import (Checklist, DoneCriteria, Repair, Replan, Runtime, Save, Sections,
                         WorkflowCriteria, UserFeedbackCriteria)
from .middleware.cited import Cited
from .middleware.revise import Revise, actionable_revision
from .state import State
from .types import Mode

# --------------------------------------------------------------- stops ---
# Beyond the three the loop always applies (complete / blocked / no
# progress), long-form runs need to notice they've run dry.


def material_used_up(st: State) -> str | None:
    """Stop when there is nothing new left to say.

    Without this, a run keeps going because a *coverage* dimension demands
    more sections while the material only supports one -- and the model
    obliges by restating the same facts from a new angle. Measured: the one
    harness lacking this check lost 0.278 per round on average, and what fell
    was ``non_repetition`` specifically, while ``factual_grounding`` held
    steady. That is the signature of "same material, said again".

    **The existing threshold barely ever fires** and this is knowingly kept
    as-is for now: "two consecutive rounds with zero new facts" almost never
    happens, because retrieval keeps returning fact rows that differ in
    wording while saying the same thing. Porting it unchanged would be
    cargo-culting; it needs a real criterion, and until then it is a
    formality. Written down here rather than quietly omitted, so nobody
    assumes there's a working guard.
    """
    if (st.round < 2 or st.bag.get("polish") or st.bag.get("cleanup_only")
            or st.bag.get("advisories") or st.skip_judge):
        # Polish adds nothing, so "the material ran out" is not a reason for
        # it to stop -- there was never any material being consumed. Repair
        # is the same shape: Repair just scheduled a next round that only
        # deletes/rephrases existing text. Stopping it because there is no new
        # material leaves a defect the scorer already located in the draft.
        # A deterministic check is also an instruction for the next round;
        # stopping in the same round means the instruction is never executed.
        # Advisory checks still run the scorer, so ``skip_judge`` is false for
        # them. Their messages live in ``advisories`` until the next prepare;
        # do not let material exhaustion cut that repair turn off.
        return None
    if st.bag.get("dry_rounds", 0) >= 2:
        return "material_used_up"
    if grounding_check.material_exhausted(st.content, st.facts):
        return "material_used_up"
    return None


# Two rounds that change nothing. The old harness used the same number as
# the fallback for "scoring failed": an occasional failure recovers next
# round, and repeated failure is indistinguishable from being stuck, so one
# safety net serves both rather than inventing a second policy for it.
STALL_ROUNDS = 2


def stalled(st: State) -> str | None:
    """Stop when rounds stop changing anything."""
    return "stalled" if st.bag.get("no_change_rounds", 0) >= STALL_ROUNDS else None


def no_actionable_repair(st: State) -> str | None:
    if not st.bag.get("cleanup_only") or st.skip_judge:
        return None
    return None if actionable_revision(st) else "no_actionable_revision"


CHECK_STUCK_ROUNDS = 3
CHECK_STUCK_WINDOW = 4


def check_stuck_detail(st: State) -> tuple[str, int]:
    window: list[dict[str, int]] = st.bag.get("check_name_rounds") or []
    counts: dict[str, int] = {}
    for rnd in window[-CHECK_STUCK_WINDOW:]:
        for name in rnd:
            counts[name] = counts.get(name, 0) + 1
    if not counts:


        streaks: dict[str, int] = st.bag.get("check_name_streak") or {}
        if not streaks:
            return "", 0
        name = max(streaks, key=lambda k: (streaks[k], k))
        return name, int(streaks[name])
    name = max(counts, key=lambda k: (counts[k], k))
    return name, counts[name]


def check_stuck(st: State) -> str | None:
    _name, n = check_stuck_detail(st)
    return "check_stuck" if n >= CHECK_STUCK_ROUNDS else None


# |---|---|---|---|


BEST_STALL_ROUNDS = 4


def best_stalled(st: State) -> str | None:
    """Stop after sustained failure to improve on the retained best round."""
    return "best_stalled" if int(st.bag.get("best_stall", 0)) >= BEST_STALL_ROUNDS else None


def pause_for_review(st: State) -> str | None:
    """Stop after each round and wait for the user.

    Without this the run keeps writing while the user is still reading, and
    every acceptance they make gets overwritten by the next round -- the
    editor's per-hunk accept/reject never reached the backend at all, so on
    an eight-round run "accept this one paragraph" was decided seven times
    and honoured zero.

    It is an ordinary stop condition, which is the point: the loop needs no
    concept of pausing. Resuming is loading the snapshot and running again
    with a higher round number.
    """
    return "awaiting_review" if st.mode.review_each_round else None


# |---|---:|---:|---|
# | eda | 3 | 9 | `max_rounds` ×3 |
# | chart | 3 | 4 | `complete` ×3 |
# | table | 3 | 6 | `complete` ×3 |
# | analysis | 3 | 9 | `max_rounds` ×3 |
# | prompt | 3 | 5 | `complete` ×2 · `max_rounds` ×1 |
# | custom | 3 | 5 | `complete` ×2 · `max_rounds` ×1 |


def nothing_changed(st: State) -> str | None:
    vectors = st.bag.get("score_vectors") or []
    if len(vectors) < 2 or vectors[-1] != vectors[-2]:
        return None
    return "nothing_changed"


def tools_ran_dry(st: State) -> str | None:
    stat = st.bag.get("ledger_round") or {}
    calls, repeats = int(stat.get("tool_calls") or 0), int(stat.get("repeat_calls") or 0)
    if st.round < 2 or calls <= 0 or repeats < calls:
        return None
    if st.best is not None and st.best[1] == st.content:
        return None
    return "tools_ran_dry"


def nothing_left_to_fix(st: State) -> str | None:
    """Polish only repairs. When a round applies no revision, the next one
    would propose the same nothing -- there is no second mechanism that could
    change the outcome."""
    if not st.bag.get("polish"):
        return None
    if st.round >= 1 and not st.bag.get("revisions_applied"):
        return "no_more_changes"
    return None


# ---------------------------------------------------------- dimensions ---


_NON_REPETITION = Dimension(
    "non_repetition",
    """When newly written sentences are supplied, penalize repetition among those sentences only.
Summarizing the user's original records once is not repetition: those records are evidence, not
another finished draft. Reusing the same facts in two sections with distinct responsibilities,
or restating a new paragraph as a list, is insufficient. Compare section topics as well as
wording: different titles can still retell the same material. Repeated arguments from the same
facts or boundary conditions are insufficient. Normal framing, a brief concluding restatement
without re-arguing, referring to a concept as a premise, and expanding a general statement into
specifics are allowed. Judge whether a passage advances the piece, not how often a term occurs.
Meets the bar: every section advances the subject rather than retelling another.""",
)

_FACTUAL_GROUNDING = Dimension(
    "factual_grounding",
    """Judge explicit conflict with supplied evidence, not how much material was used. Meets the bar:
new claims agree with evidence, or available material neither proves nor disproves them.
Insufficient: an explicit contradiction, a nonexistent citation identifier, or presenting a
model-created assumption as an actual event. Absence from the current material window does not
prove a claim false and must not lower its score. Flag uncertain claims for verification while
preserving names, dates, figures and original wording. When newly written sentences are listed,
judge only those sentences; pre-run user content and earlier retained text are outside scope.
Check that citation identifiers exist; an abbreviated evidence window does not mean the library
lacks the fact. Unused or irrelevant retrieved facts are not a deficiency. Never pressure the
writer to force unrelated evidence into the note or invent specifics to satisfy a usage quota.""",
)

_STYLE_FIT = Dimension(
    "style_fit",
    """Meets the bar: tone, structure and wording match the user's stated preferences. Insufficient:
clear violations, such as verbose prose when concision was requested.""",
)

_PROSE_QUALITY = Dimension(
    "prose_quality",
    """Judge whether the text can be delivered as finished prose. When newly written sentences are
supplied, judge only them; otherwise judge the whole note in polish mode. Score 2: natural,
concrete complete sentences; real causal, contrastive or progressive connections; informative
headings; no planning labels, writing-process narration, evidence-audit voice, stock phrases,
slogans, abstract filler or obvious grammar defects. Score 1: readable but with a clear
formulaic phrase, flat inventory, abrupt transition or awkward sentence. Score 0: predominantly
an expanded outline, material report or generic AI copy that is not ready for the note. Citation
identifiers beside their sentence are normal, including spaces between identifiers. Only a whole
line containing nothing except citation identifiers indicates detached citations. For 0 or 1,
quote the 1-2 exact short sentences or headings most needing revision and explain the change;
avoid vague criticism.""",
)


_SECTION_COVERAGE = Dimension(
    "section_coverage",
    """Meets the bar: every aspect named by the section topic has concrete corresponding content,
enough to explain what happened. Insufficient: stopping after an introduction, omitting an
aspect named by the title, or providing principles without concrete projects, dates, figures or
decisions.""",
)

_MATERIAL_USE = Dimension(
    "material_use",
    """Judge only when [Knowledge-base facts] contains evidence; without material, this dimension
meets the bar. Meets the bar: concrete projects, figures, people or decisions from relevant
material appear substantively in the body. Insufficient: relevant evidence was supplied but the
result consists entirely of generic textbook advice. This dimension is essential to the value of
a personal note: polished, non-repetitive generalities cannot substitute for the user's actual
records.""",
)

_COHERENCE = Dimension(
    "coherence",
    """Judge the piece as one consistent product. Insufficient if any apply: (1) a conclusion closes
the piece, then new substantive material creates another ending; a Mermaid visualization of
existing relationships near the conclusion is allowed; (2) equivalent sections use inconsistent
heading levels; (3) numbering skips or reverses, such as 1, 2, 4, 3; (4) incompatible formatting
makes the piece look spliced from separate articles; (5) a passage contradicts the position
advocated elsewhere in the note.""",
)


def _note_dims(has_profile: bool, polish: bool = False) -> list[Dimension]:
    dims = [
        Dimension(
            "spine_fidelity",
            """Meets the bar: the body develops the core tension (spine). Insufficient: unrelated lists or a
disconnected running log replace that tension.""",
        ),
        _NON_REPETITION,
        _FACTUAL_GROUNDING,
        _PROSE_QUALITY,
        _COHERENCE,
    ]
    if not polish:
        dims.insert(1, Dimension(
            "beat_coverage",
            """Meets the bar: each structural beat has substantive corresponding content. Exhaustive treatment
is unnecessary, but its intended function must actually be present. Insufficient: a beat has no
corresponding content.""",
        ))
        dims.append(_MATERIAL_USE)
    if has_profile:
        dims.append(_STYLE_FIT)
    return dims


def _section_dims(has_profile: bool) -> list[Dimension]:
    dims = [
        Dimension(
            "topic_fidelity",
            """Meets the bar: this note develops its own section topic without taking content assigned to other
planned sections. Insufficient: off-topic material or clear overlap with another section.""",
        ),
        _SECTION_COVERAGE,
        _NON_REPETITION,
        _FACTUAL_GROUNDING,
        _MATERIAL_USE,
        _PROSE_QUALITY,
        _COHERENCE,
    ]
    if has_profile:
        dims.append(_STYLE_FIT)
    return dims


# The wording is what the scorer reads, so these read as sentences about
# what good and bad look like, not as labels. Anything a rule can decide
# reliably is NOT here -- it belongs in checks/, because the scorer and the
# writer are the same local model and share the same blind spots.

_NUMBERS_FROM_TOOLS = Dimension(
    "numbers_from_tools",
    "Meets the bar: every statistic in the text (mean, median, extreme, "
    "correlation, share) can be traced to a tool result. Insufficient: a "
    "number appears that no tool computed.")

_HONEST_CAVEATS = Dimension(
    "honest_caveats",
    "Meets the bar: small samples, heavy gaps and unreliable correlations are "
    "stated plainly. Insufficient: a correlation over three rows is presented "
    "as a finding.")

_HAS_CHARTS = Dimension(
    "has_charts",
    "The body should be charts, but every chart must show something.\n"
    "Insufficient at both extremes: (a) prose and numbers only, no chart, or "
    "one token chart at the end; (b) a pile of charts that say nothing -- a "
    "3:3 share pie, a two-bar histogram over six points. Real output once had "
    "seven charts of which one was informative. More charts is not better.\n"
    "Meets the bar: each chart corresponds to a specific finding, and the "
    "sentence beside it says what the shape means rather than restating the "
    "numbers.")

_NO_DUP_CHARTS = Dimension(
    "no_duplicate_charts",
    "Meets the bar: each chart looks at something different. Insufficient: "
    "the same data drawn twice -- a different title or a different chart type "
    "both count. Real output drew one set of market shares as both bars and a "
    "pie while the text itself noted the numbers exceed 100% so a pie doesn't "
    "fit. Pick one form per dataset and stay with it.")

_COVERS_THE_DATA = Dimension(
    "covers_the_data",
    "Every comparable group in the sentence near the cursor should be drawn, "
    "and drawn whole.\n"
    "Insufficient (all observed): the sentence is about vendor A at 38% with "
    "B/C/D in parentheses, and the chart has only the parenthetical ones -- "
    "**the subject of the sentence is missing**; three groups mentioned, two "
    "drawn.\n"
    "This checks for **omissions, not exhaustiveness**: a table can be sliced "
    "by channel, by month, per capita; drawing every slicing is endless. As "
    "long as the slicings you chose are each complete, that meets the bar -- "
    "do not mark it down for a slicing nobody drew. (Being strict here fought "
    "directly with fits_context for three rounds in real runs.)")

_FITS_CONTEXT = Dimension(
    "fits_context",
    "It should read like a passage that was always in this note, not a report "
    "dropped into it.\n"
    "Meets the bar: headings one level below the nearest heading above; **few "
    "headings** (one or two, not one per chart); each chart gets a sentence or "
    "two; tone and conventions match the surrounding text.\n"
    "This dimension is about headings and register, **not chart count** -- the "
    "body of this mode is charts, two or three is normal. Whether a chart "
    "deserves to exist is has_charts' problem.")

_ACTIONABLE = Dimension(
    "actionable",
    "Meets the bar: it says what to look at next. Insufficient: statistics "
    "with no direction.")

EDA_DIMS = (_NUMBERS_FROM_TOOLS, _HONEST_CAVEATS, _HAS_CHARTS, _NO_DUP_CHARTS,
            _COVERS_THE_DATA, _FITS_CONTEXT, _ACTIONABLE)

CHART_DIMS = (
    Dimension("chart_validity",
              "Meets the bar: the chart came from render_chart (a complete "
              "```mermaid block) or render_image (a markdown image reference). "
              "Insufficient: hand-written mermaid, a truncated block, or a "
              "reference to an image that doesn't exist."),
    Dimension("data_grounding",
              "Meets the bar: every number in the chart traces to a table in "
              "the note or to a tool result. Insufficient: a number with no "
              "source. Not applicable when the image is illustrative."),
    Dimension("right_kind",
              "Meets the bar: numbers and processes go through render_chart; "
              "render_image is for abstract concepts. Insufficient: using "
              "text-to-image for what should be exact -- the numbers in it are "
              "invented and can't be edited."),
    _FITS_CONTEXT,
)

TABLE_DIMS = (
    Dimension("table_validity",
              "Meets the bar: a complete markdown table whose header and rows "
              "have matching column counts."),
    Dimension("data_grounding",
              "Meets the bar: every cell traces to the note, a table in it, or "
              "a retrieved fact. Insufficient: invented data. An unknown should "
              "say so, not be filled in."),
    _FITS_CONTEXT,
)

ANALYSIS_DIMS = (
    Dimension("answers_the_question",
              "Meets the bar: it answers the question that was asked. "
              "Insufficient: it talks around it."),
    _NUMBERS_FROM_TOOLS,
    Dimension("states_limits",
              "Meets the bar: it says what the conclusion depends on and when "
              "it stops holding. Insufficient: a small-sample result stated as "
              "settled."),


    Dimension("chart_validity",
              "Meets the bar: any chart here came from render_chart (a "
              "complete ```mermaid block). Insufficient: a chart described in "
              "prose, or hand-written mermaid imitating tool output. Drawing "
              "nothing is fine -- this mode's body is an answer, not charts."),
    _FITS_CONTEXT,
)

_REPLACES_CLEANLY = Dimension(
    "replaces_cleanly",
    "Meets the bar: the output can be dropped in over the selected passage "
    "and still read continuously, in the same conventions. Insufficient: it "
    "carries a lead-in like \"here is the revision\", or it copies back text "
    "from outside the selection.")

_FOLLOWS_PROMPT = Dimension(
    "follows_prompt",
    "Meets the bar: it does what the instruction asked. Insufficient: it did "
    "something else, or only half.")

_NO_FABRICATION = Dimension(
    "no_fabrication",
    "Meets the bar: anything about the user's own projects, numbers or "
    "decisions comes from retrieved facts or from the note. Insufficient: "
    "invented names, dates or figures.")

# The two prompt-driven modes differ in one dimension, and the difference is
# the whole point: PROMPT writes at a cursor, so it is judged on fitting the
# surrounding text; CUSTOM overwrites a selection, so it is judged on dropping
# in cleanly over it.


PROMPT_DIMS = (_FOLLOWS_PROMPT, _FITS_CONTEXT, _NO_FABRICATION)
CUSTOM_DIMS = (_FOLLOWS_PROMPT, _REPLACES_CLEANLY, _NO_FABRICATION)


# --------------------------------------------------------------- modes ---
# Eight features. Everything that makes them different is here; the loop,
# the middleware chain and the event contract are identical for all of them.
# ``task`` is elided in this file for readability -- the real prompts move
# over from compose_block.MODES during migration. What matters here is the
# shape: which tools, which dimensions, which checks, how many rounds.


NOTE = Mode(
    key="note",
    label="Continue note",
    groups=("memory", "skill", "longform"),
    skill_scope="magic_tap",
    dims=(),                      # runtime-shaped; see for_run()


    checks=(output_not_json,
            no_foreign_script, no_junk_tail, no_echoed_text, chart_restates_list,
            language_consistent,
            no_placeholder, no_audit_voice, outline_intact, citations_hold,
            citations_exist, material_thin, citations_present, material_used,
            no_repeated_lists, no_restated_paragraph, no_same_sources_twice,
            charts_from_tools, unsupported_specifics),


    stop_when=(check_stuck, no_actionable_repair, material_used_up, stalled, best_stalled,
               nothing_left_to_fix, pause_for_review),


    extra_mw=(DoneCriteria(), WorkflowCriteria(), UserFeedbackCriteria(), Cited(), Revise(), Repair(), Runtime(), Replan(), Sections(), Save()),
    max_rounds=8,
    context_keep_last=4000,
)

SECTION = Mode(
    key="section",
    label="Write section",
    groups=("memory", "skill", "chart", "longform"),
    skill_scope="section_write",
    dims=(),                      # runtime-shaped; see for_run()


    checks=(output_not_json,
            no_foreign_script, no_junk_tail, no_echoed_text, chart_restates_list,
            language_consistent,
            no_placeholder, no_audit_voice, citations_hold, citations_exist,
            material_thin, citations_present, material_used, no_repeated_lists,
            no_restated_paragraph, no_same_sources_twice, no_fake_charts,
            charts_from_tools, unsupported_specifics, section_budget),
    stop_when=(check_stuck, no_actionable_repair, material_used_up, pause_for_review),
    extra_mw=(Cited(), Revise(), Repair(), Sections(), Save()),
    # Measured cap, not a completion criterion: a section that keeps
    # scoring 'continue' must not hold the whole plan hostage.
    max_rounds=4,
)

# The six block modes. They share one set of Hooks -- only the fields below
# differ. Note the tool groups: render_table moves out of ``chart`` into its
# own group, so drawing modes stop being handed a table builder and the table
# mode stops being handed three chart builders.

def _eda_has_data(st) -> str | None:
    from .tools import tabular
    from .tools.data_tools import NEAR_CHARS
    text = st.ctx.content or ""
    cur = st.ctx.cursor or 0
    if tabular.sentences_with_numbers(text, cur, radius=1200):
        return None
    for t in tabular.find_tables(text):
        if tabular.distance(t, cur) <= NEAR_CHARS and not tabular.headings_between(text, cur, t.start, t.end):
            return None
    return "No data to plot near the cursor. Move the cursor to a paragraph with numbers or a nearby table and try again."


def _has_context(st) -> str | None:
    if (st.ctx.content or "").strip():
        return None
    return "The note is still empty — write something first (even one sentence about the topic) before adding figures, tables or analysis."


EDA = Mode(
    task=(
        """Explore the data in this note. Charts are the main output, not a list of statistics.
1. Call numbers_near_cursor first to inspect the paragraph where the user invoked the action.
   Then use list_tables. Prefer nearby material; ignore tables marked as far from the cursor
   unless the user explicitly selected one.
2. For numbers in prose, use chart_from_text and include the complete group, including
   the sentence's main subject rather than just parenthetical comparisons. Draw each
   distinct numerical group when useful. Values must match the original text.
3. For tables, use describe_table. Draw informative findings rather than one chart per
   column. If chart_column rejects an uninformative chart, follow its guidance.
4. Use aggregate_table before render_chart for grouped comparisons; use line charts
   for ordered time data. Use correlate_columns for suspected relationships and state n.
Give each chart one or two sentences explaining the pattern, not repeating its values.
End with what is worth investigating next. All numbers come from tools; do not calculate
mentally or handwrite Mermaid.
"""),
    key="eda",
    label="Data visualization",
    verb="Drawing",
    groups=("data", "chart", "memory", "skill"),
    focus_groups=("chart",),
    skill_scope="block_write",
    dims=EDA_DIMS,


    checks=(no_fake_charts, charts_from_tools, heading_fits, tail_clashes,
            chart_numbers_grounded, numbers_from_tools, chart_readable),

    stop_when=(nothing_changed, tools_ran_dry),
    precheck=_eda_has_data,
    max_rounds=3,
)

CHART = Mode(
    task=(
        """Create an illustration for the current location in the note. For concrete numbers
or step dependencies, use render_chart: pie for shares, bar for categories, line for
time, and flow for process dependencies. Never handwrite Mermaid. For an abstract
concept or scene needing visual expression, use render_image; it is slower, so use
it only when a picture rather than data visualization is needed. Introduce the image
with one sentence explaining what it shows.
"""),
    key="chart",
    label="Smart illustration",
    verb="Drawing",
    groups=("data", "chart", "image", "memory", "skill"),
    skill_scope="block_write",
    dims=CHART_DIMS,
    checks=(no_fake_charts, charts_from_tools, heading_fits,
            chart_numbers_grounded, chart_readable),

    stop_when=(nothing_changed, tools_ran_dry),
    precheck=_has_context,
    max_rounds=3,
)

TABLE = Mode(
    task=(
        """Organize a table for the current location. Call render_table to generate it. Decide what each row and column represents before filling it. Introduce the table with one sentence explaining what it organizes.
"""),
    key="table",
    label="Generate table",
    verb="Building table",
    groups=("data", "table", "memory", "skill"),
    skill_scope="block_write",
    dims=TABLE_DIMS,


    checks=(table_present, table_columns_match, chart_numbers_grounded,
            heading_fits),

    stop_when=(nothing_changed, tools_ran_dry),
    precheck=_has_context,
    max_rounds=3,
)

ANALYSIS = Mode(
    task=(
        """Answer the user's data question. Compute numbers with data tools rather than mentally. Lead with the conclusion, then supporting figures, then the conditions under which the conclusion would not hold. Use render_chart for a useful comparison.
"""),
    key="analysis",
    label="Data analysis",
    verb="Analyzing",
    groups=("data", "chart", "memory", "skill"),
    focus_groups=("chart",),
    skill_scope="block_write",
    dims=ANALYSIS_DIMS,
    checks=(no_fake_charts, charts_from_tools, heading_fits,
            chart_numbers_grounded, numbers_from_tools, chart_readable),

    stop_when=(nothing_changed, tools_ran_dry),
    precheck=_has_context,
    max_rounds=3,
)

PROMPT = Mode(
    task=(
        """Write content at the current location according to the user's instruction. Use memory tools when facts from the user's records are needed.
"""),
    key="prompt",
    label="Generate from prompt",
    groups=("memory", "skill"),
    skill_scope="block_prompt",
    dims=PROMPT_DIMS,
    checks=(no_placeholder, heading_fits),


    extra_mw=(Checklist(),),

    stop_when=(nothing_changed, tools_ran_dry),
    max_rounds=3,
)

# CUSTOM replaces a selection; PROMPT inserts at a cursor. That is why they
# do not share a dimension list: only one of them can be judged on whether the
# output drops in cleanly over what it replaces.
CUSTOM = Mode(
    task=(
        """Transform the selected passage according to the user's instruction. Output only its replacement, without surrounding body text or prefatory phrases such as 'Here is the revision'. Use memory tools when the user's own facts are needed.
"""),
    key="custom",
    label="Rewrite selection",
    groups=("memory", "skill"),
    skill_scope="block_prompt",
    dims=CUSTOM_DIMS,
    checks=(no_placeholder,),


    extra_mw=(Checklist(),),

    stop_when=(nothing_changed, tools_ran_dry),
    max_rounds=3,
)

BLOCK: dict[str, Mode] = {m.key: m for m in (EDA, CHART, TABLE, ANALYSIS,
                                             PROMPT, CUSTOM)}
ALL: tuple[Mode, ...] = (NOTE, SECTION, *BLOCK.values())


# ------------------------------------------------------------ runtime ---


def for_run(mode: Mode, *, has_profile: bool = False,
            polish: bool = False) -> Mode:
    """Return ``mode`` with the dimensions this particular run can act on.

    Most of a Mode is decided when the feature is written. Two of the
    long-form dimensions are not, because they depend on facts only known at
    call time, and getting this wrong does not merely score badly -- it stops
    the loop converging at all:

      * ``style_fit`` needs a style profile to compare against. With no
        profile there is nothing to be faithful *to*, so the dimension can
        never be satisfied and the run burns every round chasing it.
      * ``beat_coverage`` and ``material_use`` both measure *how much got
        written*. Polish mode is forbidden to write. Measured on a short note
        with a duplicated heading: beat_coverage scored 0 every round (the
        beats genuinely were not written), the run never reached complete,
        hit max_rounds, and each round's steer pushed it towards writing the
        very thing the mode prohibits.

    The rule both cases share: **never score a run on a dimension it has no
    power to improve.** Modes with fixed dimensions pass through untouched.
    """
    if mode.key == "note":
        dims = _note_dims(has_profile, polish)
    elif mode.key == "section":
        dims = _section_dims(has_profile)
    else:
        return mode
    return dataclasses.replace(mode, dims=tuple(dims))
