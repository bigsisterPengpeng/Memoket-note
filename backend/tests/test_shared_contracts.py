"""Run synthetic contracts shared with the frontend implementation."""
import json
from pathlib import Path
import pytest
from app.editor.preconditions import note_precondition
from app.harness.checks import done, skeleton

TABLE = json.loads((Path(__file__).parents[2] / "shared/contracts.json").read_text())

@pytest.mark.parametrize("case", TABLE["done"], ids=lambda c: c["name"])
def test_completion_criteria(case):
    result = done.check_done_item(case["item"], TABLE["contents"][case["content"]])
    assert ({"status": result["status"], "why": result["why"]} if result else None) == case["expect"]

@pytest.mark.parametrize("case", TABLE["note"], ids=lambda c: c["name"])
def test_note_preconditions(case):
    assert note_precondition(case["action"], case["content"], case["title"]) == case["expect"]

@pytest.mark.parametrize("case", TABLE["split"])
def test_criterion_splitting(case):
    assert done.split_done(case["done"]) == case["items"]

@pytest.mark.parametrize("case", TABLE["beat_labels"], ids=lambda c: c["input"])
def test_saved_beat_labels(case):
    assert skeleton.split_beat_label(case["input"]) == (case["status"], case["text"])
