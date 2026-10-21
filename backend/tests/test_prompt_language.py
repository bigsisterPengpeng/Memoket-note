"""English instructions must preserve multilingual input and parsed output contracts."""

from __future__ import annotations

import importlib
import json
import re

from fastapi.testclient import TestClient
import pytest

from app.harness import prompts
from app.harness.prompts import note, selection, writing
from app.editor.outline import parse_place_directive


HAN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


@pytest.mark.parametrize("name", ["block", "fragments", "note", "plan", "selection", "skills", "slides", "writing"])
def test_static_prompt_instructions_are_english(name):
    module = importlib.import_module(f"app.harness.prompts.{name}")
    values = {key: value for key, value in vars(module).items() if key.isupper() and isinstance(value, str)}
    assert values or name in {"fragments", "skills"}
    for key, value in values.items():
        assert not HAN.search(value), key


def test_prompt_sections_are_english_but_user_content_is_preserved():
    original = '\u7528\u6237\u7684\u539f\u6587'
    output = writing.magic_tap_user("", [], original, [], [], title="Example")
    assert original in output
    assert "[Existing body]" in output
    assert not HAN.search(output.replace(original, ""))
    assert not HAN.search(prompts.skill_generate_system())


@pytest.mark.parametrize("line, expected", [
    ("[Place: Current section]", "Current section"),
    ("[Place: end]", None),
    ("[Place: END]", None),
    ('\u3010\u653e\u5230\uff1aLegacy section\u3011', "Legacy section"),
    ('\u3010\u653e\u5230\uff1a\u6587\u672b\u3011', None),
])
def test_english_and_legacy_placement_responses(line, expected):
    assert parse_place_directive(line) == expected


def test_placement_prompt_emits_the_supported_english_directive():
    assert "[Place: exact heading]" in note.place_directive_block(["Current section"])


def test_following_context_does_not_split_an_english_word():
    text = "A sentence with an ordinary ending. " * 30
    cut = writing._cut_at_boundary(text, 100)
    assert len(cut) <= 100
    assert cut.endswith(".")
    assert "after the selection" in selection.expand_user("Before. Chosen. After.", "Chosen.")


def test_activity_prompts_and_report_headings_use_english():
    from app.journey import prompt
    from app.harness.checks.journey import check_report

    assert not HAN.search(prompt.REPORT_SYSTEM)
    assert not HAN.search(prompt.SPAN_SYSTEM)
    assert not HAN.search(prompt.report_user("2026-10-20", []))
    report = "## What moved forward\n- Updated parser.py to handle empty input."
    check = check_report(report, ["Updated parser.py to handle empty input"])
    assert check.stray_sections == []
    assert check.unsourced_terms == []
    assert check.bullets == 1
    invented = check_report(report.replace("parser.py", "invented.py"), ["Updated parser.py"])
    assert invented.unsourced_terms == ["invented.py"]


def test_auxiliary_model_instructions_are_english():
    from app.harness.checklist import SYNTH_SYSTEM
    from app.routers.compose_block import _TABLE_PROMPT, _RESTRUCTURE_SYSTEM
    from app.routers.journey import DESCRIBE_SYSTEM, pick_answer, worth_keeping

    for prompt in (SYNTH_SYSTEM, _TABLE_PROMPT, _RESTRUCTURE_SYSTEM, DESCRIBE_SYSTEM):
        assert not HAN.search(prompt)
    assert pick_answer("Reasoning first\nAnswer: Editing parser.py") == "Editing parser.py"
    assert pick_answer('\u7b54\u6848\uff1aEditing parser.py') == "Editing parser.py"
    assert not worth_keeping("Unable to read")


def test_mode_tasks_and_scoring_guidance_are_english():
    from app.harness import modes
    from app.harness.checks.rubric import _BINARY_PREFIX

    assert not HAN.search(_BINARY_PREFIX)
    for mode in modes.ALL:
        assert not HAN.search(mode.task), mode.key
        for polish in (False, True):
            configured = modes.for_run(mode, has_profile=True, polish=polish)
            for dimension in configured.dims:
                assert not HAN.search(dimension.guidance), (mode.key, dimension.name)


@pytest.mark.parametrize("verdict, wire_value", [
    ("supports", '\u652f\u6301'),
    ("contradicts", '\u77db\u76fe'),
    ("unknown", '\u65e0\u6cd5\u5224\u65ad'),
])
def test_english_model_verdicts_preserve_the_existing_api_contract(monkeypatch, verdict, wire_value):
    from app.main import app
    from app.routers import compose

    class Memory:
        def __init__(self, user):
            pass

        def recall(self, query, limit=8, scope="all"):
            return ([{"id": "example-1-A1", "text": "The release is Friday", "date": ""}], [], 0)

        def source_lines(self, row):
            return []

    async def complete(messages, **kwargs):
        assert not HAN.search(messages[0]["content"])
        return json.dumps([{"verdict": verdict, "reason": "Compared with the release record", "fact_index": 0}])

    monkeypatch.setattr(compose, "UserMemory", Memory)
    monkeypatch.setattr(compose.llm, "complete", complete)
    with TestClient(app, headers={"X-User-Id": "example"}) as client:
        response = client.post("/api/verify", json={"content": "The release is Friday", "selection": "The release is Friday"})
    assert response.status_code == 200
    finding = response.json()["findings"][0]
    assert finding["verdict"] == wire_value
    assert finding["fact_id"] == "example-1-A1"


def test_policy_and_preference_instructions_are_english():
    from app.harness import feedback
    from app.harness.policy import RoundFeedback, RuntimePolicy, adjust

    for empty in (False, True):
        policy, reasons = adjust(RuntimePolicy(), RoundFeedback(
            scores={"factual_grounding": 0, "material_use": 0, "coherence": 0},
            tool_calls=3, tool_facts=0, tools_used=("search_memory",), kb_empty=empty,
        ))
        assert not HAN.search(policy.steer)
        assert not HAN.search("\n".join(reasons))
    text = feedback.system_block({"items": [{"decision": "reverted",
        "del_text": "Before", "ins_text": "After"}]})
    assert not HAN.search(text)
    assert not HAN.search(feedback.USER_ALIGNMENT.guidance)


def test_block_context_wrappers_are_english():
    from app.harness import modes
    from app.harness.hooks.block import BlockHooks
    from app.harness.state import State
    from app.harness.tools import ToolContext

    state = State(mode=modes.BLOCK["prompt"], ctx=ToolContext(user="test"))
    state.before, state.after = "Earlier paragraph.", "Following paragraph."
    output = BlockHooks(title="Example", prompt="Write a summary")._user(state, facts="[f1] Evidence.")
    assert not HAN.search(output)
    assert "[Text before the cursor]" in output
    assert "Earlier paragraph." in output and "Following paragraph." in output
