"""English plan generation must agree with saved-note and UI label parsing."""

import json
import re
from pathlib import Path

from app.harness.checks import skeleton


def test_shared_beat_label_cases():
    cases = json.loads((Path(__file__).parents[2] / "shared/beat-label-cases.json").read_text())
    for case in cases["cases"]:
        assert skeleton.split_beat_label(case["input"]) == (case["status"], case["text"])


def test_missing_english_beat_promotes_and_keeps_its_line_on_repeat():
    text = "Project Aurora launches on April 12 with 25 pilot users."
    beats = skeleton.verify_beats(["Missing: " + text], "Opening paragraph.\n\n" + text)
    assert beats == ["Written (from body line 3): " + text]
    assert skeleton.verify_beats(beats, text) == beats
    assert skeleton.verify_beats(["Missing: Budget approval by July 20."], text) == [
        "Missing: Budget approval by July 20."
    ]


def test_english_plan_rule_is_english_and_placeholder_cells_are_not_evidence():
    rule = skeleton.skeleton_length_rule(26714)
    assert "3–12 beats" in rule and "Written:" in rule and "Missing:" in rule
    assert not re.search(r"[\u3400-\u9fff]", rule)
    source = "| Owner | Evidence |\n|---|---|\n| A | Fill in budget evidence |\n| B | TBD |"
    cleaned = skeleton._strip_placeholders(source)
    assert "budget evidence" not in cleaned and "TBD" not in cleaned
    assert cleaned.count("\n") == source.count("\n")


def test_ordinary_english_words_do_not_make_a_plan_concrete():
    beats = ["Written: Establish the context", "Missing: Anticipate reader questions",
             "Missing: Conclude with a useful framework"]
    assert skeleton.check_skeleton("Explain the change in our approach.", beats).all_rhetoric
    beats.append("Missing: Explain the Aurora launch decision on April 12.")
    assert not skeleton.check_skeleton("Explain the change in our approach.", beats).all_rhetoric


def test_shared_english_grammar_does_not_promote_an_unwritten_beat():
    source = "The pilot is on track and the team is ready for the launch."
    beat = "Missing: The budget is pending and the board is responsible for the approval."
    assert skeleton.verify_beats([beat], source) == [beat]


def test_english_scoring_distinguishes_new_sentences_without_splitting_decimals():
    from app.harness.score_context import new_sentences

    before = "Version 2.4 ships today. The pilot has 25 users."
    after = before + " Support approved the rollout."
    assert new_sentences(after, before) == ["Support approved the rollout."]
    assert new_sentences(after, "") == []


def test_english_report_checks_specificity_and_duration_without_flagging_plain_prose():
    from app.harness.checks.journey import check_report

    report = "## What moved forward\n- Continued making progress on development."
    assert check_report(report, []).vague_bullets == ["Continued making progress on development."]
    report = "## What moved forward\n- Fixed `parser.py` in 47 minutes."
    findings = check_report(report, ["Worked on parser.py."])
    assert findings.recomputed_durations == ["47 minutes"]
    assert not findings.unsourced_terms and not findings.vague_bullets
