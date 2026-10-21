"""Writing workflows the user chose on purpose: turn a template from a body scaffold into an
executable quality contract.

The template identity reaches ``ctx.intent`` through ``DocIntent.workflow``. This module does
three things only:

* give retrieval, writing and revision the scenario constraints that phase really needs;
* add a scenario dimension to the judge so a perfect generic prose score cannot hide a daily
  report / journal / minutes that is wrong as that kind of document;
* put the same contract into the score context so the verdict can name the clause that failed.

It does not start another loop and never guesses the scenario from the title. Without a chosen
template but with an explicit user goal it returns nothing and the generic Harness handles the
run; a request without a goal is rejected at the router.

Two kinds of Recipe:

* the four original templates (daily / weekly / journal / meeting) each have their own Recipe
  with fixed ``sections``;
* the other 100 templates (frontend ``editor/writingTemplateCatalog.ts``) are grouped into 11
  categories and share one Recipe per category. Their sections come from the template's own
  scaffold, so the category Recipe has ``sections=()`` and the deterministic section check only
  relies on the user's done criteria (``checks/done``).

Prompts are English. Notes and materials may be in any language, so every phase block tells the
model to write in the language of the note.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..editor import intent as doc_intent
from ..util.i18n_zh import ZH
from .types import Dimension


@dataclass(frozen=True)
class Recipe:
    id: str
    label: str
    sections: tuple[str, ...]
    retrieval: str
    writing: str
    quality: str
    # ``deliverable`` contracts can define "this deliverable is finished"; ``open`` treats the
    # contract as a guardrail against breaking the user's meaning, pushes a bounded number of
    # rounds and hands the pen back without declaring the text done.
    completion_policy: str = "deliverable"
    handoff_rounds: int = 0

    @property
    def sections_zh(self) -> tuple[str, ...]:
        """Chinese headings for the same sections (the Chinese UI inserts the scaffold through
        ``t()``, so a Chinese note carries these titles). Taken from the shared dictionary."""
        return tuple(ZH.get(s, s) for s in self.sections)


LANGUAGE_RULE = "Write in the language of the note and its materials."

RECIPES: dict[str, Recipe] = {
    "daily": Recipe(
        id="daily",
        label="Daily report",
        sections=("Today's results", "Key progress and decisions", "Blockers and support needed",
                  "Tomorrow's priorities"),
        retrieval=(
            "Look first for records, decisions and blockers that the title, body or materials clearly "
            "place on this day. When the date range is unclear, search around the current body and its "
            "sections, but never present an older record as something that happened today."
        ),
        writing=(
            "Write results, progress/decisions, blockers/support and tomorrow's actions as separate "
            "sections. Done, in progress and planned must be marked with clear status words; each fact "
            "goes into the one section that fits best -- results do not restate decisions, progress does "
            "not repeat the result numbers. A blocker states its impact and who needs to provide what. "
            "Do not add results, dates or events the material does not contain."
        ),
        quality=(
            "Pass: a reader can tell at a glance what was achieved today, which decisions were made on the "
            "way, what is blocked now and what happens tomorrow; statuses are not mixed, blockers can be "
            "acted on by others, tomorrow's items are executable, and no fact goes beyond the material."
        ),
    ),
    "weekly": Recipe(
        id="weekly",
        label="Weekly report",
        sections=("This week's results", "Key progress and decisions", "Risks and blockers",
                  "Next week's focus"),
        retrieval=(
            "Look first for this week's daily reports, project progress, decisions, risks and blockers; "
            "merge the same matter by date and project and keep the sources that support the key "
            "conclusions. When the range is unclear, do not count historical items as this week's results."
        ),
        writing=(
            "Before writing, assign every piece of material to exactly one slot: quantified results and "
            "user findings go to \"This week's results\"; decisions, trade-offs and completed-but-unverified "
            "process changes go to \"Key progress and decisions\"; the impact of risks and the support still "
            "needed this week go to \"Risks and blockers\"; only items the material explicitly marks as next "
            "week's plan go to \"Next week's focus\". Each fact appears in the one section that fits best -- "
            "never write it as a paragraph and then repeat it in other words; an unblocking action due this "
            "week must not slide into next week."
        ),
        quality=(
            "Pass: not a running log; this week's results, key decisions, risks and next week's focus are "
            "separate, the timeline is consistent, key conclusions trace back to the material, and the "
            "reader can judge progress, risk and next steps from it. If two sections use the same set of "
            "citation ids to describe one matter in different words, it fails: keep the result in the "
            "results section and the decision or action that produced it in the progress section, never "
            "the full chain of facts in both."
        ),
    ),
    "journal": Recipe(
        id="journal",
        label="Journal",
        sections=("What happened today", "How I felt and what I judged", "For my future self"),
        retrieval=(
            "Use the current body and the personal records the user provided; only look for material that "
            "restores the context of the events. When a personal record is hit, retrieve the original words "
            "-- a journal cannot be written from fact summaries alone; coexisting emotions, rhetorical "
            "questions and hedges in the original words must be kept. External facts never replace the "
            "writer's feelings; do not infer inner life the material never wrote down."
        ),
        writing=(
            "Keep the user's first-person voice and concrete details; keep hesitation, contradiction and "
            "unfinished thoughts. Events and feelings may echo each other, but only events, actions, "
            "dialogue and judgments that explicitly appear in the material may be rewritten; do not add "
            "new actions, turns in the meeting or scenes after it; never infer \"I did not do it\" from "
            "\"the material does not say\". Uncertainty the user expressed with \"if\", \"maybe\" or \"I don't "
            "know yet\" stays uncertain and must not become confirmed cause and effect; never patch gaps "
            "with phrases like \"I answered but did not write it down\", \"it was not discussed\" or \"to be "
            "confirmed\" -- a step the material does not describe is not written. Each section has one job: "
            "the first records observable events, the second the feelings, judgments and what-ifs of the "
            "moment, the third keeps only the questions still worth revisiting. A judgment goes in one "
            "section only; the third section does not restate events or the previous section's reasoning. "
            "If the original has bodily details such as fiddling with a pen, pauses, or coexisting emotion "
            "words, keep at least one of them -- not just an event summary. When the material has no new "
            "insight, the last section keeps the original question; do not invent rules of conduct, life "
            "lessons or an inspirational ending. An open question must not be turned into a self-improvement "
            "aim such as \"next time I want to see whether I can...\", nor given a condition like waiting for "
            "some result before confirming."
        ),
        quality=(
            "Guardrail pass: it reads like the same person continuing to write, with concrete experience "
            "and the judgment of the moment; no emotions were put in the user's mouth, no events or actions "
            "were added that the material lacks, no complex experience was flattened into a tidy conclusion, "
            "no platitudes or forced uplift. Check the subject and action of every new event sentence: one "
            "person's reaction must not become the whole team's; the user's guess, rhetorical question or "
            "undecided judgment must not become a meeting decision, an on-site fact or something that "
            "happened afterwards -- a plausible inference still counts as an addition. If the original ends "
            "on an unresolved question, the result must keep it open and must not answer it for the user or "
            "turn it into a list of suggestions. Events, feelings/judgments and questions for later must "
            "each keep their own job; a last section that restates the previous one sentence by sentence "
            "fails even when its content is true."
        ),
        completion_policy="open",
        handoff_rounds=2,
    ),
    "meeting": Recipe(
        id="meeting",
        label="Meeting notes",
        sections=("Context", "Decisions", "Action items", "Open questions"),
        retrieval=(
            "The current meeting transcript, recording description and the material the user named come "
            "first; supplementary material is only for checking the background. Keep who said what, the "
            "decisions, owners and dates; never fill this meeting with conclusions from another one."
        ),
        writing=(
            "Separate discussion, confirmed decisions, action items and open questions. Only what was "
            "explicitly settled goes under \"Decisions\"; a speaker's statement is not a decision just because "
            "it sounds firm. An action item states action, owner and date; whichever the material lacks is "
            "marked as to be confirmed. When the material explicitly says the owner is undecided, that gap "
            "must stay in the notes -- do not drop the item because it has no owner."
        ),
        quality=(
            "Pass: discussion was not upgraded to decisions and open items were not written as conclusions; "
            "action items are executable, owners and dates either trace to the material or are explicitly "
            "to be confirmed; every action and ownership gap in the material is kept, so the reader can act "
            "and hold people accountable."
        ),
    ),
}

# -- Template category contracts ---------------------------------------------------------------
# One entry per `category` in the frontend template catalogue. Templates in the category set
# ``intent.workflow`` to the category id. Sections belong to each template, so ``sections=()``
# here: the deterministic section check no longer names fixed headings and only follows the
# done criteria the user carries (checks/done). Each contract states only the sourcing, writing
# and acceptance discipline the whole genre really shares.
RECIPES.update({
    "reports": Recipe(
        id="reports",
        label="Reports",
        sections=(),
        retrieval=(
            "Bound the material by the reporting period (day / week / month / quarter / project phase) and "
            "take records, numbers, decisions and blockers from inside it first; older material may serve as "
            "comparison background but must not pose as this period. Prefer numbers whose source can be traced."
        ),
        writing=(
            "Results, process, risks and next steps each get one place; no running log. Mark done / in "
            "progress / planned with explicit status words; every conclusion maps to one piece of material "
            "and numbers carry their definition; a blocker states its impact and who must provide what; do "
            "not add achievements, causes or plans the material does not support."
        ),
        quality=(
            "Pass: a reader can judge progress, risk and next steps without the raw material; statuses are "
            "not mixed; every key conclusion traces to the material; no guess is written as fact and no fact "
            "is repeated across two sections."
        ),
    ),
    "meetings": Recipe(
        id="meetings",
        label="Meetings",
        sections=(),
        retrieval=(
            "Use this meeting's or conversation's transcript, recording description and the material the "
            "user named; keep who said what, the decisions and the owners. Conclusions from other meetings "
            "or other people only check the background and never fill this meeting."
        ),
        writing=(
            "Separate context, discussion, confirmed decisions, action items and open questions; only what "
            "was explicitly settled becomes a decision. An action item has action, owner and date, with "
            "missing parts marked as to be confirmed; keep the other side's exact words where they matter "
            "and do not put words in anyone's mouth. For 1:1s, interviews and customer calls, keep the other "
            "person's position and concerns as theirs instead of rewriting them into conclusions."
        ),
        quality=(
            "Pass: discussion was not upgraded to decisions and open items were not written as conclusions; "
            "every action item can be executed and traced to an owner; statements and positions are "
            "attributed correctly; the reader can act from the notes instead of re-listening to the recording."
        ),
    ),
    "product": Recipe(
        id="product",
        label="Product",
        sections=(),
        retrieval=(
            "Take verbatim user feedback, data, competitor facts and prior decisions first; separate what "
            "users said, what we observed and what we infer. Requirements and solutions must trace to the "
            "problem they came from; market judgments without a source are marked as assumptions."
        ),
        writing=(
            "State the problem and the target user first, then the solution and its trade-offs, then scope, "
            "metrics and open questions. Every requirement or change must be acceptable; metrics state their "
            "definition and baseline; risks and dependencies are listed apart; do not write wishes as "
            "validated facts or let adjectives stand in for data."
        ),
        quality=(
            "Pass: the reader can answer \"whose problem, how we will know it worked, what we will not do\"; "
            "requirements are acceptable, metrics measurable, assumptions flagged; nothing imagined is "
            "written as done and no constraint stated in the material is missing."
        ),
    ),
    "research": Recipe(
        id="research",
        label="Research",
        sections=(),
        retrieval=(
            "Take primary literature, experiment records, data and the user's own notes first; every citation "
            "keeps its source; separate the author's text, the author's conclusion and the writer's own "
            "appraisal, and never treat a second-hand retelling as primary evidence."
        ),
        writing=(
            "Write question, method, evidence, conclusion and limitations as separate parts; the strength of "
            "a conclusion matches its evidence; numbers carry units and conditions; contradictory evidence is "
            "presented side by side rather than one side only; the writer's own inferences are marked as such."
        ),
        quality=(
            "Pass: every conclusion leads back to specific evidence; no hypothesis is written as a finding; "
            "limitations and open questions are stated; citations are attributed correctly so the reader can "
            "follow them up."
        ),
    ),
    "writing": Recipe(
        id="writing",
        label="Writing",
        sections=(),
        retrieval=(
            "Gather material around the piece's core idea and its reader: facts, examples, quotations and data "
            "each keep their source; the user's own earlier views and phrasing come first and are not replaced "
            "with generic wording."
        ),
        writing=(
            "One piece serves one core idea; the opening gives the reader a reason to continue and paragraphs "
            "advance rather than pile up; examples and data serve the argument and name their source; keep "
            "the user's tone and word choices; add no facts, numbers or quotes the material lacks and do not "
            "end on an empty uplifting line."
        ),
        quality=(
            "Pass: the reader can restate the idea in one sentence; the structure advances; every concrete fact "
            "is grounded; the voice reads like the same person throughout; no filler paragraphs."
        ),
    ),
    "personal": Recipe(
        id="personal",
        label="Personal",
        sections=(),
        retrieval=(
            "Use the user's own records and words and only look for material that restores the context of the "
            "events; when a personal record is hit, retrieve the original words and keep coexisting emotions, "
            "rhetorical questions and hedges; external facts never replace the writer's feelings, and inner "
            "life the material never wrote down is not inferred."
        ),
        writing=(
            "Keep the first person and the user's existing voice, with hesitation, contradiction and unfinished "
            "thoughts; rewrite only events, actions and judgments that explicitly appear in the material; do "
            "not add scenes that did not happen or feelings that were not expressed; uncertainty worded as "
            "\"maybe\" or \"I don't know yet\" stays as it is; do not invent rules of conduct, life lessons or an "
            "inspirational ending for the user."
        ),
        quality=(
            "Guardrail pass: it reads like the same person continuing, with concrete experience and the "
            "judgment of the moment; no emotions were put in the user's mouth and no events were added; no "
            "complex experience was flattened into a tidy conclusion, no platitudes or forced uplift; the "
            "original open questions stay open."
        ),
        completion_policy="open",
        handoff_rounds=2,
    ),
    "sales": Recipe(
        id="sales",
        label="Sales & marketing",
        sections=(),
        retrieval=(
            "Take the customer's or audience's own words, validated product facts, prices and case data first; "
            "promises, numbers and customer quotes must trace to a source; competitor information is used only "
            "where it can be verified."
        ),
        writing=(
            "Lead with the problem and benefit the other side cares about, then our solution and evidence, then "
            "an explicit next step; every promise and number is grounded, nothing is exaggerated and no customer "
            "quote is invented; the tone matches the target audience and one piece drives one action."
        ),
        quality=(
            "Pass: the reader knows \"what this does for me, why I should believe it, what to do next\"; every "
            "factual promise and number can be traced; no made-up customer quotes or unverified comparisons."
        ),
    ),
    "engineering": Recipe(
        id="engineering",
        label="Engineering",
        sections=(),
        retrieval=(
            "Take code, logs, monitoring data, change records and existing design documents first; timelines, "
            "version numbers and interface names follow the material; separate reproduced facts from suspected "
            "causes."
        ),
        writing=(
            "Write context, proposal or symptom, trade-off or root cause, impact and follow-up actions as "
            "separate parts; every step is executable, reversible and verifiable; terms and names match the "
            "code; an unproven root cause is written as a hypothesis with a way to test it; do not write plans "
            "as done and do not omit risks and dependencies the material states."
        ),
        quality=(
            "Pass: another engineer can execute or review it without asking anyone; facts and inferences are "
            "distinct; timeline, versions and blast radius match the material; follow-ups have an owner or are "
            "explicitly pending."
        ),
    ),
    "people": Recipe(
        id="people",
        label="People",
        sections=(),
        retrieval=(
            "Take concrete behaviour, output, verbatim feedback and agreed goals first; every judgment must "
            "trace to an observable fact; do not write motive guesses or personality judgments the material "
            "does not support."
        ),
        writing=(
            "Describe behaviour and impact instead of labelling people; strengths and growth areas are written "
            "apart, each with concrete examples; expectations and next steps are observable actions that can "
            "be agreed; about others, write only what the material states, respectfully and in a way that "
            "invites conversation."
        ),
        quality=(
            "Pass: every judgment has a concrete example; no sweeping characterisation or motive guessing; "
            "next steps can be executed and followed up; the person concerned would read it as a fair record."
        ),
    ),
    "learning": Recipe(
        id="learning",
        label="Learning & teaching",
        sections=(),
        retrieval=(
            "Take textbooks, lecture notes, original notes and exercise records first; definitions follow the "
            "source; separate \"what the material says\" from \"my own understanding\", and examples keep their "
            "origin."
        ),
        writing=(
            "Give the goal and prerequisites first, then build from easy to hard; every concept gets a concrete "
            "example or exercise; restate in your own words without changing the meaning; doubts and what is "
            "not yet understood are written down rather than papered over."
        ),
        quality=(
            "Pass: the reader (or the future self) can learn or revise from it; definitions are accurate and "
            "examples match; half-understanding is not written as settled; open doubts are kept."
        ),
    ),
    "ops": Recipe(
        id="ops",
        label="Operations & finance",
        sections=(),
        retrieval=(
            "Take ledgers, contracts, process records and owner information first; numbers carry date, currency "
            "and definition; vendor and option comparisons use only terms that can be verified."
        ),
        writing=(
            "Write goal, current state, plan or steps, owners and risks as separate parts; steps can be executed "
            "one by one and numbers can be checked; decisions state their basis and alternatives; do not write "
            "estimates as actuals or omit exceptions and preconditions the material states."
        ),
        quality=(
            "Pass: the operator can follow it without asking anyone; every number and clause has a source; "
            "owners and dates are explicit or marked pending; estimates and actuals are not mixed."
        ),
    ),
})


def recipe_of(intent_text: str) -> Recipe | None:
    return RECIPES.get(doc_intent.workflow_of(intent_text))


def completion_policy(intent_text: str) -> tuple[str, int]:
    """How the workflow finishes. Without a workflow the generic deliverable Harness applies."""
    recipe = recipe_of(intent_text)
    if not recipe:
        return "deliverable", 0
    return recipe.completion_policy, recipe.handoff_rounds


def system_block(intent_text: str, phase: str) -> str:
    """The short constraint for one Harness phase. Each step reads only the part it can act on."""
    recipe = recipe_of(intent_text)
    if not recipe:
        return ""
    if phase == "retrieve":
        rule = recipe.retrieval
        action = "sourcing"
    elif phase == "plan":
        slots = (f"Use these {len(recipe.sections)} kinds of content as the plan slots: "
                 f"{', '.join(recipe.sections)}. "
                 if recipe.sections else "The plan slots are the template sections already present in the body. ")
        rule = slots + recipe.writing
        action = "planning"
    elif phase == "revise":
        rule = recipe.quality + " Revision only changes the specific sentences or paragraphs that break these rules."
        action = "revision"
    else:
        rule = recipe.writing
        action = "writing"
    return f"[{recipe.label} workflow - {action} rules]\n{rule} {LANGUAGE_RULE}\n\n"


def quality_contract(intent_text: str) -> str:
    recipe = recipe_of(intent_text)
    if not recipe:
        return ""
    head = f"The user chose the \"{recipe.label}\" template."
    if recipe.sections:
        head += f" Required sections: {', '.join(recipe.sections)}."
    else:
        head += " Required sections are the template headings already present in the body."
    return f"{head}\n{recipe.quality}"


def section_titles(recipe: Recipe) -> list[tuple[str, ...]]:
    """Accepted headings per required section: the English title plus its Chinese translation
    (the Chinese UI inserts the scaffold through ``t()``). Deduplicated, English first."""
    out: list[tuple[str, ...]] = []
    for en, zh in zip(recipe.sections, recipe.sections_zh):
        out.append((en,) if zh == en else (en, zh))
    return out


def dimension(intent_text: str) -> Dimension | None:
    recipe = recipe_of(intent_text)
    if not recipe:
        return None
    return Dimension(
        "workflow_fidelity",
        f"Judge only whether this text is genuinely usable as a {recipe.label}. {recipe.quality} "
        "When it fails, the note must name the section at fault and quote one passage from the text, "
        "saying what should move, be added or be removed; never just say \"does not match the template\".",
    )
