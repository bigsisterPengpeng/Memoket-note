"""Template identity, phase rules, the scenario dimension and the deterministic floor must work end to end.

Most detectors in checks/workflow.py match Chinese user content, so most fixtures here are Chinese
notes written with unicode escapes (the repo keeps Han characters out of code); each test says in
English what its note contains. Chinese headings are the ones `workflows.section_titles` accepts
(the translations in `util/i18n_zh.py`)."""

from __future__ import annotations

import asyncio

from app.editor import intent, outline
from app.harness import loop, modes, workflows
from app.harness.checks.workflow import workflow_quality
from app.harness.checks.structure import no_same_sources_twice
from app.harness.checks.grounding import no_placeholder
from app.harness.hooks.note import NoteHooks
from app.harness.middleware.workflow import WorkflowCriteria
from app.harness.middleware.repair import Repair
from app.harness.state import State
from app.harness.tools import ToolContext
from app.harness.types import DimensionScore, Evaluation


def _intent(kind: str) -> str:
    return intent.as_text({"workflow": kind, "goal": "a document ready to use",
                           "reader": "readers", "done": "every needed section has text", "source": "user"})


def _state(kind: str, content: str, *, fresh: str = "") -> State:
    st = State(mode=modes.for_run(modes.NOTE),
               ctx=ToolContext(user="u", note_id="n", note_title="title", intent=_intent(kind)),
               content=content, fresh=fresh)
    st.bag["content_at_start"] = ""
    return st


def test_workflow_identity_roundtrip_and_unknown_value_is_dropped():
    raw = {"workflow": "weekly", "goal": "weekly report", "source": "user"}
    assert intent.normalize(raw)["workflow"] == "weekly"
    text = intent.as_text(raw)
    assert text == "Workflow: weekly; Goal: weekly report"
    assert intent.workflow_of(text) == "weekly"
    # A goal that merely mentions a workflow is not one
    assert intent.workflow_of("Goal: explain why Workflow: weekly failed") == ""
    assert intent.normalize({"workflow": "invented"})["workflow"] == ""
    assert intent.as_text({"workflow": "weekly"}) == "", "no visible task means no hidden workflow"


def test_selected_workflow_adds_dimension_and_check_but_plain_note_does_not():
    selected = _state("daily", "")
    asyncio.run(WorkflowCriteria().before_run(selected))
    assert "workflow_fidelity" in {d.name for d in selected.mode.dims}
    assert workflow_quality in selected.mode.checks

    plain = State(mode=modes.for_run(modes.NOTE),
                  ctx=ToolContext(user="u", note_id="n", intent=""))
    asyncio.run(WorkflowCriteria().before_run(plain))
    assert "workflow_fidelity" not in {d.name for d in plain.mode.dims}
    assert workflow_quality not in plain.mode.checks


def test_journal_is_open_handoff_not_a_complete_machine():
    st = _state("journal", "body")
    asyncio.run(WorkflowCriteria().before_run(st))
    assert st.bag["completion_policy"] == "open"
    assert st.bag["handoff_rounds"] == 2

    st.round = 1
    st.ev = Evaluation(
        scores={"workflow_fidelity": DimensionScore(2, "did not break the user's meaning")},
        status="complete",
    )
    loop._apply_completion_policy(st)
    assert st.ev.status == "continue", "passing the guardrail must not mark a journal complete"
    assert loop._stop(st) == "open_handoff"


def test_journal_hands_back_after_bounded_passes_even_if_guardrail_is_not_perfect():
    st = _state("journal", "body")
    asyncio.run(WorkflowCriteria().before_run(st))
    st.round = 2
    st.ev = Evaluation(
        scores={"workflow_fidelity": DimensionScore(1, "the user can keep exploring")},
        status="continue", weakest="workflow_fidelity",
    )
    assert loop._stop(st) == "open_handoff"


def test_deliverable_workflow_still_uses_complete():
    st = _state("weekly", "body")
    asyncio.run(WorkflowCriteria().before_run(st))
    st.round = 1
    st.ev = Evaluation(
        scores={"workflow_fidelity": DimensionScore(2, "ready to use")},
        status="complete",
    )
    loop._apply_completion_policy(st)
    assert st.ev.status == "complete"
    assert loop._stop(st) == "complete"


def test_empty_template_headings_do_not_count_as_finished():
    # A Chinese daily report with the four headings and nothing under them.
    st = _state("daily", "## \u4eca\u5929\u7684\u7ed3\u679c\n\n## \u5173\u952e\u8fdb\u5c55\u4e0e\u51b3\u5b9a\n\n## \u963b\u585e\u4e0e\u9700\u8981\u7684\u652f\u6301\n\n## \u660e\u5929\u4f18\u5148\u5904\u7406")
    verdict = workflow_quality(st)
    assert verdict is not None
    assert "still have only a heading or filler" in verdict.message
    assert "\u4eca\u5929\u7684\u7ed3\u679c" in verdict.message and "\u660e\u5929\u4f18\u5148\u5904\u7406" in verdict.message


def test_explicit_no_record_is_a_deliberate_answer_not_an_empty_heading():
    # Chinese daily report; the blockers section says 'no record' on purpose.
    st = _state("daily", (
        "## \u4eca\u5929\u7684\u7ed3\u679c\n\n\u5b8c\u6210\u4e86\u5bfc\u5165\u6821\u9a8c\u3002\n\n## \u5173\u952e\u8fdb\u5c55\u4e0e\u51b3\u5b9a\n\n\u51b3\u5b9a\u5148\u4fee\u590d\u5931\u8d25\u91cd\u8bd5\u3002\n\n"
        "## \u963b\u585e\u4e0e\u9700\u8981\u7684\u652f\u6301\n\n\u6682\u65e0\u8bb0\u5f55\u3002\n\n## \u660e\u5929\u4f18\u5148\u5904\u7406\n\n\u5148\u8865\u9f50\u56de\u5f52\u6d4b\u8bd5\u3002"))
    assert workflow_quality(st) is None


def test_daily_future_plan_cannot_hide_inside_today_results():
    # Today's results says 'shipped; tomorrow we watch two hours before scaling up'.
    st = _state("daily", (
        "## \u4eca\u5929\u7684\u7ed3\u679c\n\n\u65b0\u7248\u5df2\u7ecf\u4e0a\u7ebf\uff0c\u660e\u5929\u89c2\u5bdf\u4e24\u5c0f\u65f6\u540e\u518d\u51b3\u5b9a\u6269\u91cf\u3002\n\n"
        "## \u5173\u952e\u8fdb\u5c55\u4e0e\u51b3\u5b9a\n\n\u57cb\u70b9\u5b57\u6bb5\u5df2\u7ecf\u786e\u8ba4\u3002\n\n"
        "## \u963b\u585e\u4e0e\u9700\u8981\u7684\u652f\u6301\n\n\u6682\u65e0\u8bb0\u5f55\u3002\n\n"
        "## \u660e\u5929\u4f18\u5148\u5904\u7406\n\n\u89c2\u5bdf\u7070\u5ea6\u8868\u73b0\u3002"))
    verdict = workflow_quality(st)
    assert verdict is not None and "future marker" in verdict.message and verdict.fix
    fixed = verdict.fix(st.content)
    parts = {title.strip(): body for title, body in outline.section_bodies(fixed)}
    assert "\u660e\u5929\u89c2\u5bdf" not in parts["\u4eca\u5929\u7684\u7ed3\u679c"]
    assert "## \u660e\u5929\u4f18\u5148\u5904\u7406\n\n\u89c2\u5bdf\u7070\u5ea6\u8868\u73b0" in fixed


def test_workflow_check_removes_orphan_list_marker():
    # Meeting notes with a bare '-' left under Decisions.
    st = _state("meeting", (
        "## \u8ba8\u8bba\u80cc\u666f\n\n\u8ba8\u8bba\u4e86\u5b9a\u4ef7\u3002\n\n## \u51b3\u5b9a\n\n- \u91c7\u7528\u65b9\u6848 A\u3002\n-\n\n"
        "## \u884c\u52a8\u9879\n\n\u8d1f\u8d23\u4eba\u5f85\u786e\u8ba4\u3002\n\n## \u672a\u51b3\u95ee\u9898\n\n\u6298\u6263\u4ecd\u672a\u51b3\u5b9a\u3002"))
    verdict = workflow_quality(st)
    assert verdict is not None and verdict.fix is not None
    fixed = verdict.fix(st.content)
    assert "\n-\n" not in fixed and verdict.fix_done and verdict.fix_done(fixed)


def test_workflow_check_repairs_nested_broken_markdown_list():
    # Weekly report with a nested broken bold list item '- **- **keep variant B**'.
    st = _state("weekly", (
        "## \u672c\u5468\u7ed3\u679c\n\n\u5b8c\u6210\u7387\u8fbe\u5230 62%\u3002\n\n## \u5173\u952e\u8fdb\u5c55\u4e0e\u51b3\u5b9a\n\n"
        "- **- **\u4fdd\u7559 B \u7248**\n\n## \u98ce\u9669\u4e0e\u963b\u585e\n\n\u9690\u79c1\u6e05\u5355\u5f85\u786e\u8ba4\u3002\n\n"
        "## \u4e0b\u5468\u91cd\u70b9\n\n\u53d1\u5e03\u56db\u6b65\u5bfc\u5165\u6d41\u7a0b\u3002"))
    verdict = workflow_quality(st)
    assert verdict is not None and verdict.fix is not None
    fixed = verdict.fix(st.content)
    assert "- **\u4fdd\u7559 B \u7248**" in fixed
    assert "- **- **" not in fixed
    assert verdict.fix_done and verdict.fix_done(fixed)


def test_weekly_removes_a_decision_repeated_in_results_and_progress():
    # Results and progress both say 'decided to keep variant B'; results also has the 62% / 51% numbers.
    st = _state("weekly", (
        "## \u672c\u5468\u7ed3\u679c\n\nA/B \u6d4b\u8bd5\u5b8c\u6210\uff0cB \u7248\u4e3a 62%\uff0cA \u7248\u4e3a 51%\u3002\u57fa\u4e8e\u7ed3\u679c\uff0c\u51b3\u5b9a\u4fdd\u7559 B \u7248\u3002"
        "[note-123456789abc-0F1]\n\n## \u5173\u952e\u8fdb\u5c55\u4e0e\u51b3\u5b9a\n\n"
        "\u56e2\u961f\u51b3\u5b9a\u4fdd\u7559 B \u7248\uff0c\u5e76\u628a\u5bfc\u5165\u6d41\u7a0b\u4ece 7 \u6b65\u51cf\u5230 4 \u6b65\u3002\n\n"
        "## \u98ce\u9669\u4e0e\u963b\u585e\n\n\u9690\u79c1\u6e05\u5355\u4ecd\u5f85\u6cd5\u52a1\u786e\u8ba4\u3002\n\n"
        "## \u4e0b\u5468\u91cd\u70b9\n\n\u53d1\u5e03 4 \u6b65\u6d41\u7a0b\u5e76\u89c2\u5bdf\u5b8c\u6210\u7387\u3002"))
    verdict = workflow_quality(st)
    assert verdict is not None and verdict.fix is not None
    fixed = verdict.fix(st.content)
    parts = {title.strip(): body for title, body in outline.section_bodies(fixed)}
    assert "62%" in parts["\u672c\u5468\u7ed3\u679c"]
    assert "\u51b3\u5b9a\u4fdd\u7559 B \u7248" not in parts["\u672c\u5468\u7ed3\u679c"]
    assert "\u51b3\u5b9a\u4fdd\u7559 B \u7248" in parts["\u5173\u952e\u8fdb\u5c55\u4e0e\u51b3\u5b9a"]
    assert verdict.fix_done and verdict.fix_done(fixed)


def test_journal_rejects_new_generic_uplift_but_not_user_old_text():
    # The new text adds 'this experience taught me to be braver'; a plain 'not figured out yet' is fine.
    content = ("## \u4eca\u5929\u53d1\u751f\u7684\u4e8b\n\n\u4e0b\u5348\u628a\u5931\u8d25\u7684\u7248\u672c\u91cd\u65b0\u8dd1\u4e86\u4e00\u904d\u3002\n\n"
               "## \u6211\u5f53\u65f6\u7684\u611f\u53d7\u548c\u5224\u65ad\n\n\u6211\u6709\u4e9b\u70e6\uff0c\u4e5f\u4e0d\u786e\u5b9a\u8fd9\u4e2a\u65b9\u5411\u5bf9\u4e0d\u5bf9\u3002\n\n"
               "## \u60f3\u7559\u7ed9\u4e4b\u540e\u7684\u81ea\u5df1\n\n\u8fd9\u6bb5\u7ecf\u5386\u8ba9\u6211\u660e\u767d\uff0c\u672a\u6765\u8981\u66f4\u52c7\u6562\u3002")
    st = _state("journal", content, fresh="\u8fd9\u6bb5\u7ecf\u5386\u8ba9\u6211\u660e\u767d\uff0c\u672a\u6765\u8981\u66f4\u52c7\u6562\u3002")
    verdict = workflow_quality(st)
    assert verdict is not None and "generic uplifting line" in verdict.message
    st.fresh = "\u6211\u6682\u65f6\u8fd8\u6ca1\u60f3\u6e05\u695a\u3002"
    assert workflow_quality(st) is None


def test_journal_removes_invented_happened_but_not_recorded_process():
    # The model appended 'I did not note the exact time, to be confirmed' to a journal whose source never mentioned it.
    source = ("## \u968f\u624b\u8bb0\n\n\u5c0f\u5468\u53ea\u95ee\u6700\u665a\u4ec0\u4e48\u65f6\u5019\u80fd\u7ed9\u53ef\u6d4b\u8bd5\u7248\u672c\u3002\n\n"
              "## \u4eca\u5929\u53d1\u751f\u7684\u4e8b\n\n\u6211\u8bf4\u7248\u672c\u8d76\u4e0d\u4e0a\u5468\u4e94\u3002\n\n"
              "## \u6211\u5f53\u65f6\u7684\u611f\u53d7\u548c\u5224\u65ad\n\n\u6211\u8fd8\u4e0d\u77e5\u9053\u8fd9\u6837\u662f\u5426\u8d1f\u8d23\u3002\n\n"
              "## \u60f3\u7559\u7ed9\u4e4b\u540e\u7684\u81ea\u5df1\n\n\u8fd9\u4e2a\u95ee\u9898\u4ecd\u7136\u6ca1\u6709\u7b54\u6848\u3002")
    st = _state("journal", source + "\n\u5177\u4f53\u65f6\u95f4\u6211\u6ca1\u6709\u8bb0\u4e0b\u6765\uff0c\u5f85\u786e\u8ba4\u3002")
    st.bag["content_at_start"] = source
    verdict = workflow_quality(st)
    assert verdict is not None and verdict.fix is not None
    assert "never described" in verdict.message
    fixed = verdict.fix(st.content)
    assert "\u6ca1\u6709\u8bb0\u4e0b\u6765" not in fixed and "\u5f85\u786e\u8ba4" not in fixed
    assert verdict.fix_done and verdict.fix_done(fixed)


def test_journal_keeps_absence_when_user_explicitly_wrote_it():
    # The user wrote 'the exact time was not noted' themselves; it stays.
    content = ("## \u4eca\u5929\u53d1\u751f\u7684\u4e8b\n\n\u6211\u56de\u7b54\u4e86\u95ee\u9898\uff0c\u4f46\u5177\u4f53\u65f6\u95f4\u6ca1\u6709\u8bb0\u4e0b\u6765\u3002\n\n"
               "## \u6211\u5f53\u65f6\u7684\u611f\u53d7\u548c\u5224\u65ad\n\n\u6211\u5bf9\u6b64\u6709\u4e9b\u4e0d\u5b89\u3002\n\n"
               "## \u60f3\u7559\u7ed9\u4e4b\u540e\u7684\u81ea\u5df1\n\n\u4e4b\u540e\u518d\u6838\u5bf9\u65f6\u95f4\u3002")
    st = _state("journal", content)
    st.bag["content_at_start"] = content
    assert workflow_quality(st) is None


def test_journal_removes_self_improvement_added_to_open_question():
    # The source only has an open question ('was confessing more responsible, or just shifting pressure?'); the model added 'later I want to see whether I can cut scope earlier'.
    source_fact = "\u7528\u6237\u8fd8\u4e0d\u77e5\u9053\u8fd9\u6b21\u5766\u767d\u66f4\u8d1f\u8d23\u4efb\uff0c\u8fd8\u662f\u53ea\u662f\u628a\u538b\u529b\u5206\u7ed9\u4e86\u522b\u4eba\u3002"
    content = ("## \u4eca\u5929\u53d1\u751f\u7684\u4e8b\n\n\u6211\u5728\u4f8b\u4f1a\u4e0a\u627f\u8ba4\u7248\u672c\u4f1a\u5ef6\u671f\u3002\n\n"
               "## \u6211\u5f53\u65f6\u7684\u611f\u53d7\u548c\u5224\u65ad\n\n\u6211\u677e\u4e86\u4e00\u53e3\u6c14\uff0c\u4e5f\u6709\u70b9\u4e0d\u7518\u5fc3\u3002\n\n"
               "## \u60f3\u7559\u7ed9\u4e4b\u540e\u7684\u81ea\u5df1\n\n"
               "\u4e4b\u540e\u6211\u60f3\u770b\u81ea\u5df1\u80fd\u4e0d\u80fd\u66f4\u65e9\u780d\u6389\u8fb9\u7f18\u9700\u6c42\uff0c\u7b49\u7ed3\u679c\u51fa\u6765\u518d\u56de\u5934\u5224\u65ad\u3002\n\n"
               "\u6211\u8fd8\u4e0d\u77e5\u9053\u8fd9\u6b21\u5766\u767d\u66f4\u8d1f\u8d23\u4efb\uff0c\u8fd8\u662f\u53ea\u662f\u628a\u538b\u529b\u5206\u7ed9\u4e86\u522b\u4eba\u3002")
    st = _state("journal", content)
    st.facts = [source_fact]
    verdict = workflow_quality(st)
    assert verdict is not None and verdict.fix is not None
    fixed = verdict.fix(st.content)
    assert "\u80fd\u4e0d\u80fd\u66f4\u65e9" not in fixed and "\u8fd8\u4e0d\u77e5\u9053\u8fd9\u6b21\u5766\u767d" in fixed
    assert verdict.fix_done and verdict.fix_done(fixed)


def test_journal_keeps_original_voice_and_removes_cross_section_event_repeat():
    # Original words (fiddling with a pen, afraid of blame, relief and reluctance) sit next to a paraphrase in the feelings section and repeat in the events section.
    original = ("\u8bf4\u51fa\u53e3\u524d\u6211\u4e00\u76f4\u5728\u8f6c\u7b14\uff0c\u6015\u5927\u5bb6\u89c9\u5f97\u662f\u6211\u6ca1\u6709\u628a\u9879\u76ee\u7ba1\u597d\u3002"
                "\u5c0f\u5468\u6ca1\u6709\u8ffd\u95ee\u8d23\u4efb\uff0c\u53ea\u95ee\u6700\u665a\u4ec0\u4e48\u65f6\u5019\u80fd\u7ed9\u53ef\u6d4b\u8bd5\u7248\u672c\u3002"
                "\u90a3\u4e00\u523b\u6211\u677e\u4e86\u4e00\u53e3\u6c14\uff0c\u4f46\u4e5f\u6709\u70b9\u4e0d\u7518\u5fc3\u3002")
    content = ("## \u4eca\u5929\u53d1\u751f\u7684\u4e8b\n\n\u6211\u8bf4\u7248\u672c\u8d76\u4e0d\u4e0a\u5468\u4e94\u3002\u8bf4\u51fa\u53e3\u524d\u6211\u4e00\u76f4\u5728\u8f6c\u7b14\u3002"
               "\u5c0f\u5468\u6ca1\u6709\u8ffd\u95ee\u8d23\u4efb\uff0c\u53ea\u95ee\u6700\u665a\u4ec0\u4e48\u65f6\u5019\u80fd\u7ed9\u53ef\u6d4b\u8bd5\u7248\u672c\u3002\n\n"
               "## \u6211\u5f53\u65f6\u7684\u611f\u53d7\u548c\u5224\u65ad\n\n\u6211\u6ca1\u6cd5\u7b80\u5355\u5224\u65ad\u8fd9\u6b21\u5766\u767d\u3002\n\n" + original + "\n\n"
               "## \u60f3\u7559\u7ed9\u4e4b\u540e\u7684\u81ea\u5df1\n\n\u6211\u8fd8\u4e0d\u77e5\u9053\u8fd9\u662f\u5426\u66f4\u8d1f\u8d23\u3002")
    st = _state("journal", content)
    st.facts = ["[note-123456789abc-0F1 \u7684\u539f\u8bdd] " + original]
    verdict = workflow_quality(st)
    assert verdict is not None and verdict.fix is not None
    fixed = verdict.fix(st.content)
    parts = {title.strip(): body for title, body in outline.section_bodies(fixed)}
    assert "\u6211\u6ca1\u6cd5\u7b80\u5355\u5224\u65ad" not in fixed
    assert "\u4e00\u76f4\u5728\u8f6c\u7b14" not in parts["\u4eca\u5929\u53d1\u751f\u7684\u4e8b"]
    assert "\u4e00\u76f4\u5728\u8f6c\u7b14" in parts["\u6211\u5f53\u65f6\u7684\u611f\u53d7\u548c\u5224\u65ad"]


def test_meeting_keeps_unresolved_item_out_of_decisions():
    # Decisions contains 'release date to be confirmed'.
    st = _state("meeting", (
        "## \u8ba8\u8bba\u80cc\u666f\n\n\u56e2\u961f\u8ba8\u8bba\u4e86\u53d1\u5e03\u8303\u56f4\u3002\n\n## \u51b3\u5b9a\n\n\u53d1\u5e03\u65e5\u671f\u5f85\u786e\u8ba4\u3002\n\n"
        "## \u884c\u52a8\u9879\n\n\u6574\u7406\u5019\u9009\u65e5\u671f\uff0c\u8d1f\u8d23\u4eba\u5f85\u786e\u8ba4\u3002\n\n## \u672a\u51b3\u95ee\u9898\n\n\u8fd8\u9700\u786e\u8ba4\u4f9d\u8d56\u65b9\u65f6\u95f4\u3002"))
    verdict = workflow_quality(st)
    assert verdict is not None and "still unresolved" in verdict.message
    assert "\u672a\u51b3\u95ee\u9898" in verdict.message


def test_meeting_pending_owner_is_state_not_placeholder():
    # Action item 'owner for notifying sales: to be confirmed' is a real state, not a placeholder.
    st = _state("meeting", (
        "## \u8ba8\u8bba\u80cc\u666f\n\n\u8ba8\u8bba\u4e86\u53d1\u5e03\u3002\n\n## \u51b3\u5b9a\n\n\u5468\u4e94\u53d1\u5e03\u3002\n\n"
        "## \u884c\u52a8\u9879\n\n\u901a\u77e5\u9500\u552e\u7684\u8d1f\u8d23\u4eba\uff1a\u5f85\u786e\u8ba4\u3002\n\n## \u672a\u51b3\u95ee\u9898\n\n\u6682\u65e0\u5176\u4ed6\u95ee\u9898\u3002"))
    st.facts = ["\u4f1a\u8bae\u6750\u6599"]
    assert no_placeholder(st) is None


def test_meeting_keeps_explicit_unassigned_responsibility_gap():
    # The material says 'who notifies sales is not decided'; the notes drop that gap until an action item restores it.
    st = _state("meeting", (
        "## \u8ba8\u8bba\u80cc\u666f\n\n\u8ba8\u8bba\u4e86\u53d1\u5e03\u5b89\u6392\u3002\n\n## \u51b3\u5b9a\n\n\u4f1a\u8bae\u786e\u8ba4\u5468\u4e94\u8fdb\u884c\u8bc4\u5ba1\u3002\n\n"
        "## \u884c\u52a8\u9879\n\n\u674e\u742a\u6574\u7406\u6d4b\u7b97\u3002\n\n## \u672a\u51b3\u95ee\u9898\n\n\u6298\u6263\u5c1a\u672a\u51b3\u5b9a\u3002"))
    st.bag["content_at_start"] = "\u4f1a\u8bae\u786e\u8ba4\u674e\u742a\u6574\u7406\u6d4b\u7b97\uff1b\u8c01\u8d1f\u8d23\u901a\u77e5\u9500\u552e\u6ca1\u6709\u5b9a\u3002"
    verdict = workflow_quality(st)
    assert verdict is not None and verdict.advisory
    assert "\u901a\u77e5\u9500\u552e" in verdict.message and "mark the owner as to be confirmed" in verdict.message

    st.content = st.content.replace("\u674e\u742a\u6574\u7406\u6d4b\u7b97\u3002", "\u674e\u742a\u6574\u7406\u6d4b\u7b97\u3002\n- \u901a\u77e5\u9500\u552e\uff1a\u8d1f\u8d23\u4eba\u5f85\u786e\u8ba4\u3002")
    assert workflow_quality(st) is None


def test_meeting_finds_unassigned_responsibility_in_retrieved_facts():
    # Same gap, found in a retrieved fact; the restored item words it in reverse order ('sales notification owner').
    st = _state("meeting", (
        "## \u8ba8\u8bba\u80cc\u666f\n\n\u8ba8\u8bba\u4e86\u53d1\u5e03\u5b89\u6392\u3002\n\n## \u51b3\u5b9a\n\n\u4f1a\u8bae\u786e\u8ba4\u5468\u4e94\u8fdb\u884c\u8bc4\u5ba1\u3002\n\n"
        "## \u884c\u52a8\u9879\n\n\u674e\u742a\u6574\u7406\u6d4b\u7b97\u3002\n\n## \u672a\u51b3\u95ee\u9898\n\n\u6298\u6263\u5c1a\u672a\u51b3\u5b9a\u3002"))
    st.facts = ["[note-123456789abc-0F7] \u8c01\u8d1f\u8d23\u901a\u77e5\u9500\u552e\u6ca1\u6709\u5b9a\u3002"]
    verdict = workflow_quality(st)
    assert verdict is not None and verdict.advisory and "\u901a\u77e5\u9500\u552e" in verdict.message

    st.content = st.content.replace("\u674e\u742a\u6574\u7406\u6d4b\u7b97\u3002", "\u674e\u742a\u6574\u7406\u6d4b\u7b97\u3002\n- \u9500\u552e\u901a\u77e5\u8d1f\u8d23\u4eba\uff1a\u5f85\u786e\u8ba4\u3002")
    assert workflow_quality(st) is None, "a reordered action phrase (sales notification / notify sales) is the same action"


def test_meeting_keeps_pending_owner_in_action_only_once():
    # The pending owner for notifying sales appears in both action items and open questions.
    st = _state("meeting", (
        "## \u8ba8\u8bba\u80cc\u666f\n\n\u8ba8\u8bba\u4e86\u5b9a\u4ef7\u548c\u9500\u552e\u901a\u77e5\u3002\n\n## \u51b3\u5b9a\n\n\u4f01\u4e1a\u7248\u6309\u5e2d\u4f4d\u6536\u8d39\u3002\n\n"
        "## \u884c\u52a8\u9879\n\n- \u901a\u77e5\u9500\u552e\uff1a\u8d1f\u8d23\u4eba\u5f85\u786e\u8ba4\u3002\n\n## \u672a\u51b3\u95ee\u9898\n\n"
        "- \u6559\u80b2\u6298\u6263\u5f85\u786e\u8ba4\u3002\n- \u8c01\u8d1f\u8d23\u901a\u77e5\u9500\u552e\uff1a\u5f85\u786e\u8ba4\u3002"))
    st.facts = ["[note-123456789abc-0F7] \u8c01\u8d1f\u8d23\u901a\u77e5\u9500\u552e\u6ca1\u6709\u5b9a\u3002"]
    verdict = workflow_quality(st)
    assert verdict is not None and verdict.fix is not None
    fixed = verdict.fix(st.content)
    parts = {title.strip(): body for title, body in outline.section_bodies(fixed)}
    assert "\u901a\u77e5\u9500\u552e" in parts["\u884c\u52a8\u9879"]
    assert "\u901a\u77e5\u9500\u552e" not in parts["\u672a\u51b3\u95ee\u9898"]


def test_retrieval_phase_receives_only_the_selected_workflow_rule():
    st = _state("weekly", "body")
    plan = NoteHooks()._plan_system(st)
    assert "[Weekly report workflow - sourcing rules]" in plan and "this week's daily reports" in plan
    assert "Journal workflow" not in plan
    assert workflows.quality_contract(st.ctx.intent).startswith('The user chose the "Weekly report" template')


def test_hallucinated_required_workflow_score_cannot_turn_run_complete(monkeypatch):
    # Journal note; the judge quotes a sentence that is not in the text.
    st = _state("journal", (
        "## \u4eca\u5929\u53d1\u751f\u7684\u4e8b\n\n\u6211\u5728\u4f8b\u4f1a\u4e0a\u627f\u8ba4\u7248\u672c\u4f1a\u5ef6\u671f\u3002\n\n"
        "## \u6211\u5f53\u65f6\u7684\u611f\u53d7\u548c\u5224\u65ad\n\n\u6211\u677e\u4e86\u4e00\u53e3\u6c14\uff0c\u4f46\u8fd8\u4e0d\u786e\u5b9a\u8fd9\u6837\u505a\u662f\u5426\u66f4\u8d1f\u8d23\u3002\n\n"
        "## \u60f3\u7559\u7ed9\u4e4b\u540e\u7684\u81ea\u5df1\n\n\u4e0b\u6b21\u4ecd\u8981\u8bb0\u4f4f\u8fd9\u4efd\u4e0d\u786e\u5b9a\u3002"))
    asyncio.run(WorkflowCriteria().before_run(st))

    async def fake_evaluate(*_args, dimensions, **_kwargs):
        scores = {
            dim.name: DimensionScore(
                level=2,
                note=("The text says \u201cI have completely figured it out\u201d, flattening a complex experience into a conclusion."
                      if dim.name == "workflow_fidelity" else "Meets the bar."),
            )
            for dim in dimensions
        }
        return Evaluation(scores=scores, status="complete")

    monkeypatch.setattr(loop, "evaluate", fake_evaluate)
    result = asyncio.run(loop._evaluate(st))
    assert result is not None
    assert result.status == "continue"
    assert result.weakest == "workflow_fidelity"
    assert result.scores["workflow_fidelity"].level == 1


def test_selected_workflow_gets_second_repair_when_first_attempt_worsens():
    st = _state("journal", "body")
    asyncio.run(WorkflowCriteria().before_run(st))
    repair = Repair()

    async def apply(level: int) -> None:
        st.ev = Evaluation(
            scores={"workflow_fidelity": DimensionScore(level=level, note="still draws conclusions for the user")},
            status="continue", weakest="workflow_fidelity",
        )
        async for _ in repair.after_judge(st):
            pass

    asyncio.run(apply(1))
    assert st.bag["cleanup_only"] is True
    asyncio.run(apply(0))
    assert st.bag["cleanup_only"] is True, "a first repair that made it worse still earns one more targeted revision for the contract"
    asyncio.run(apply(0))
    assert st.bag["cleanup_only"] is False, "after two attempts without improvement, stop spinning"


def test_selected_workflow_repetition_also_gets_second_repair():
    st = _state("journal", "body")
    asyncio.run(WorkflowCriteria().before_run(st))
    repair = Repair()

    async def apply(level: int) -> None:
        st.ev = Evaluation(
            scores={"non_repetition": DimensionScore(level=level, note="two sections repeat the same fact")},
            status="continue", weakest="non_repetition",
        )
        async for _ in repair.after_judge(st):
            pass

    asyncio.run(apply(1))
    asyncio.run(apply(1))
    assert st.bag["cleanup_only"] is True
    asyncio.run(apply(1))
    assert st.bag["cleanup_only"] is False


def test_same_source_repetition_is_advisory_so_repair_can_run():
    # Two journal sections cite the same two facts to describe the same afternoon meeting.
    st = _state("journal", (
        "## \u4eca\u5929\u53d1\u751f\u7684\u4e8b\n\n\u6211\u5728\u4e0b\u5348\u4f8b\u4f1a\u4e0a\u76f4\u63a5\u8bf4\u7248\u672c\u4f1a\u5ef6\u671f\uff0c\u5c0f\u5468\u968f\u540e\u8be2\u95ee\u6700\u665a\u4ec0\u4e48\u65f6\u5019\u80fd\u7ed9\u51fa\u53ef\u6d4b\u8bd5\u7248\u672c\u3002"
        "[note-123456789abc-0F1][note-123456789abc-0F2]\n\n"
        "## \u6211\u5f53\u65f6\u7684\u611f\u53d7\u548c\u5224\u65ad\n\n\u8bf4\u51fa\u5ef6\u671f\u65f6\u6211\u4e00\u76f4\u5728\u8f6c\u7b14\uff0c\u4e5f\u62c5\u5fc3\u5927\u5bb6\u4f1a\u89c9\u5f97\u662f\u6211\u6ca1\u6709\u7ba1\u7406\u597d\u9879\u76ee\uff0c\u5c0f\u5468\u6ca1\u6709\u8ffd\u95ee\u8d23\u4efb\u3002"
        "[note-123456789abc-0F1][note-123456789abc-0F2]\n\n"
        "## \u60f3\u7559\u7ed9\u4e4b\u540e\u7684\u81ea\u5df1\n\n\u6211\u8fd8\u4e0d\u77e5\u9053\u8fd9\u6837\u662f\u5426\u8d1f\u8d23\u3002"))
    verdict = no_same_sources_twice(st)
    assert verdict is not None and verdict.advisory
    assert verdict.dimension == "non_repetition"
