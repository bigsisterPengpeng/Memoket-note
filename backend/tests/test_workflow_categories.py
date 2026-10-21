"""Template category contracts: all 11 category ids round-trip from the shared intent text to a
Recipe; the four originals keep their sections; category contracts have no fixed sections, so the
deterministic check never names headings; headings inserted by either UI language count."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from app.editor import intent
from app.harness import loop, modes, workflows
from app.harness.checks.workflow import workflow_quality
from app.harness.hooks.note import NoteHooks
from app.harness.middleware.workflow import WorkflowCriteria
from app.harness.state import State
from app.harness.tools import ToolContext
from app.harness.types import DimensionScore, Evaluation
from app.util.i18n_zh import ZH

ROOT = Path(__file__).resolve().parents[2]
ORIGINALS = ("daily", "weekly", "journal", "meeting")
CATEGORIES = ("reports", "meetings", "product", "research", "writing", "personal",
              "sales", "engineering", "people", "learning", "ops")
HAN = re.compile(r"[\u3400-\u9fff]")


def _intent(kind: str) -> str:
    return intent.as_text({"workflow": kind, "goal": "a document ready to use",
                           "reader": "readers", "done": "every needed section has text", "source": "user"})


def _state(kind: str, content: str) -> State:
    st = State(mode=modes.for_run(modes.NOTE),
               ctx=ToolContext(user="u", note_id="n", note_title="title", intent=_intent(kind)),
               content=content)
    st.bag["content_at_start"] = ""
    return st


def test_every_category_id_round_trips_to_a_recipe():
    assert set(intent.WORKFLOW_LABEL) == set(ORIGINALS) | set(CATEGORIES)
    assert set(workflows.RECIPES) == set(intent.WORKFLOW_LABEL)
    for kind in CATEGORIES:
        text = _intent(kind)
        assert text.startswith(f"Workflow: {kind}; Goal: ")
        assert intent.workflow_of(text) == kind
        assert intent.normalize({"workflow": kind})["workflow"] == kind
        recipe = workflows.recipe_of(text)
        assert recipe is not None and recipe.id == kind and recipe.label == intent.WORKFLOW_LABEL[kind]
        assert recipe.sections == () and recipe.sections_zh == ()
        for field in (recipe.retrieval, recipe.writing, recipe.quality):
            assert len(field) > 40 and not HAN.search(field), "contracts are English prompts"
    # Labels and ids also resolve; "Meetings" vs "Meeting notes" match on the whole value, not a prefix
    assert intent.workflow_of("Workflow: Meeting notes; Goal: x") == "meeting"
    assert intent.workflow_of("Workflow: Meetings; Goal: x") == "meetings"
    assert intent.workflow_of("Workflow: meeting; Goal: x") == "meeting"
    assert intent.workflow_of("Workflow: nope; Goal: x") == ""


def test_legacy_chinese_intent_text_still_resolves():
    """Text produced before the English-first flip (Chinese labels, fullwidth separators) still parses."""
    colon, sep = "\uff1a", "\uff1b"
    for kind in ORIGINALS + CATEGORIES:
        legacy = f"{ZH['Workflow']}{colon}{ZH[intent.WORKFLOW_LABEL[kind]]}{sep}{ZH['Goal']}{colon}g{sep}{ZH['Done']}{colon}d1{sep}d2"
        assert intent.workflow_of(legacy) == kind
        assert intent.goal_of(legacy) == "g"
        assert intent.done_of(legacy) == f"d1{sep}d2"


def test_originals_are_unchanged_and_keep_their_sections():
    expected = {
        "daily": ("Today's results", "Key progress and decisions", "Blockers and support needed", "Tomorrow's priorities"),
        "weekly": ("This week's results", "Key progress and decisions", "Risks and blockers", "Next week's focus"),
        "journal": ("What happened today", "How I felt and what I judged", "For my future self"),
        "meeting": ("Context", "Decisions", "Action items", "Open questions"),
    }
    for kind, sections in expected.items():
        recipe = workflows.RECIPES[kind]
        assert recipe.sections == sections
        assert len(recipe.sections_zh) == len(sections)
        assert all(HAN.search(s) for s in recipe.sections_zh), kind
        assert workflows.quality_contract(_intent(kind)).startswith(
            f"The user chose the \"{recipe.label}\" template. Required sections: {', '.join(sections)}.")
    assert workflows.completion_policy(_intent("journal")) == ("open", 2)
    for kind in ("daily", "weekly", "meeting"):
        assert workflows.completion_policy(_intent(kind)) == ("deliverable", 0)


def test_personal_is_open_handoff_and_the_rest_are_deliverables():
    assert workflows.completion_policy(_intent("personal")) == ("open", 2)
    for kind in CATEGORIES:
        if kind != "personal":
            assert workflows.completion_policy(_intent(kind)) == ("deliverable", 0), kind
    st = _state("personal", "body")
    asyncio.run(WorkflowCriteria().before_run(st))
    assert st.bag["completion_policy"] == "open" and st.bag["handoff_rounds"] == 2
    st.round = 1
    st.ev = Evaluation(scores={"workflow_fidelity": DimensionScore(2, "did not break the user's meaning")}, status="complete")
    loop._apply_completion_policy(st)
    assert st.ev.status == "continue" and loop._stop(st) == "open_handoff"


def test_category_recipe_adds_dimension_and_check_but_does_not_demand_fixed_headings():
    st = _state("product", "## Problem\n\nThe import flow is too long; users drop at step five.\n\n"
                           "## Solution and scope\n\nCut seven steps to four.")
    asyncio.run(WorkflowCriteria().before_run(st))
    assert "workflow_fidelity" in {d.name for d in st.mode.dims}
    assert workflow_quality in st.mode.checks
    assert workflow_quality(st) is None, "category contracts have no fixed sections; other headings are not missing sections"
    # The deterministic Markdown floor still applies
    st.content += "\n\n## Success metrics\n\n-\n"
    verdict = workflow_quality(st)
    assert verdict is not None and verdict.fix is not None


def test_category_prompts_do_not_print_an_empty_slot_list():
    text = _intent("engineering")
    plan = workflows.system_block(text, "plan")
    assert plan.startswith("[Engineering workflow - planning rules]\n")
    assert "these 0 kinds" not in plan and "slots: ." not in plan
    assert "The plan slots are the template sections already present in the body." in plan
    assert workflows.LANGUAGE_RULE in plan
    contract = workflows.quality_contract(text)
    assert contract.startswith("The user chose the \"Engineering\" template. "
                               "Required sections are the template headings already present in the body.")
    assert "Required sections: ." not in contract
    retrieve = NoteHooks()._plan_system(_state("research", "body"))
    assert "Research workflow - sourcing rules" in retrieve and "primary literature" in retrieve
    assert "Daily report workflow" not in retrieve and "Engineering workflow" not in retrieve


def test_headings_from_either_ui_language_count_as_present_sections():
    en = ("## Today's results\n\nShipped the import fix.\n\n## Key progress and decisions\n\nChose retry first.\n\n"
          "## Blockers and support needed\n\nNone recorded.\n\n## Tomorrow's priorities\n\nRegression tests.")
    assert workflow_quality(_state("daily", en)) is None
    tomorrow = ZH["Tomorrow's priorities"]
    mixed = (f"## Today's results\n\nShipped.\n\n## {ZH['Key progress and decisions']}\n\nChose retry first.\n\n"
             f"## Blockers and support needed\n\n\n\n## {tomorrow}\n\nAdd tests.")
    verdict = workflow_quality(_state("daily", mixed))
    assert verdict is not None and "Blockers and support needed" in verdict.message
    assert "Today's results" not in verdict.message and "Key progress and decisions" not in verdict.message
    assert workflows.section_titles(workflows.RECIPES["journal"]) == [
        ("What happened today", ZH["What happened today"]),
        ("How I felt and what I judged", ZH["How I felt and what I judged"]),
        ("For my future self", ZH["For my future self"]),
    ]


def test_section_headings_match_the_frontend_dictionary():
    """The frontend scaffold (English key -> Chinese value in i18n/zh/templates.ts) and the backend
    sections / sections_zh are the same headings; one character off and a section counts as missing."""
    dictionary = ROOT / "frontend" / "src" / "i18n" / "zh" / "templates.ts"
    if not dictionary.exists():
        pytest.skip("no frontend checkout")
    src = dictionary.read_text(encoding="utf-8")
    for kind in ORIGINALS:
        recipe = workflows.RECIPES[kind]
        en = "\\n\\n".join(f"## {s}" for s in recipe.sections).replace("'", "\\'")
        zh = "\\n\\n".join(f"## {s}" for s in recipe.sections_zh)
        key = f"'{en}': '{zh}'"
        assert key in src, f"{kind}: the dictionary has no such scaffold entry\n{key}"


def test_category_run_through_with_fake_judge(monkeypatch):
    """Same fake judge as test_workflow_quality: under a category contract, when the judge quotes a
    passage that does not exist for the scenario dimension, perfect generic scores must not mark
    the note finished."""
    st = _state("engineering", (
        "## Context and constraints\n\nThe service times out at peak.\n\n## Decision\n\nSwitch to a connection pool.\n\n"
        "## Alternatives considered\n\nMore machines: too expensive.\n\n## Consequences\n\nConfig needs migrating."))
    asyncio.run(WorkflowCriteria().before_run(st))

    async def fake_evaluate(*_args, dimensions, **_kwargs):
        scores = {
            dim.name: DimensionScore(
                level=2,
                note=("The text says “we have already validated every alternative”, an inference written as fact."
                      if dim.name == "workflow_fidelity" else "Meets the bar."),
            )
            for dim in dimensions
        }
        return Evaluation(scores=scores, status="complete")

    monkeypatch.setattr(loop, "evaluate", fake_evaluate)
    result = asyncio.run(loop._evaluate(st))
    assert result is not None
    assert result.status == "continue" and result.weakest == "workflow_fidelity"
    assert result.scores["workflow_fidelity"].level == 1


class _FakeHooks:
    """No model: produce() writes a fixed body, prepare() returns one fake fact."""

    def __init__(self, body: str):
        self.body = body
        self.saved: list[str] = []

    async def prepare(self, st):
        class _Trace:
            calls: list = []
            used = False
            iters = 0
        return [f"fact-{st.round}"], _Trace()

    async def produce(self, st):
        for ch in self.body:
            yield ch
        st.content = self.body

    async def commit(self, st):
        self.saved.append(st.content)


@pytest.mark.parametrize("kind, reason", [("personal", "open_handoff"), ("people", "complete")])
def test_fake_harness_run_for_a_new_category(kind, reason):
    """A whole `loop.run` with fake hooks and a fake scorer: the category workflow attaches its
    dimension, and the run ends by the category's completion policy (personal hands the pen back,
    people delivers)."""
    from app.harness import State as RunState
    from app.harness.loop import run
    from app.harness.types import Dimension, Mode

    async def score(st):
        return Evaluation(scores={d.name: DimensionScore(level=2, note="") for d in st.mode.dims},
                          status="complete")

    mode = Mode(key="t", label="test", skill_scope="test_scope", dims=(Dimension("d0", "..."),), max_rounds=4)
    st = RunState(mode=mode, ctx=ToolContext(user="u", note_id="n", intent=_intent(kind)), request=None)
    hooks = _FakeHooks("## What happened\n\nI walked to the river after work and sat there for an hour.\n\n"
                       "## How it felt\n\nCalm, a little tired.")

    async def go():
        return [e async for e in run(st, hooks, mw=(WorkflowCriteria(),))]

    original, loop._score = loop._score, score
    try:
        events = asyncio.run(go())
    finally:
        loop._score = original
    assert "workflow_fidelity" in {d.name for d in st.mode.dims}
    finished = [e for e in events if str(getattr(e.type, "value", e.type)) == "RUN_FINISHED"]
    assert finished and finished[-1].data["reason"] == reason
    assert hooks.saved == [hooks.body]
