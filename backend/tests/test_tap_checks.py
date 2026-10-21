"""Synthetic regression cases for continuation checks and endpoint wiring."""

from __future__ import annotations

import pathlib
import re

from app.harness.checks.tap import (PROMPT_EXAMPLES, RESTATE_RATIO, check_tap,
                                    leaked_prompt_examples, scaffold_headings)

# Invented passages; no production notes or model captures are used here.
SYNTHETIC = "## Library pickup hours\n\nThe neighborhood library will offer evening collection on Tuesdays. Readers can reserve books through the catalog and collect them from a staffed desk. A printed receipt confirms which items were checked out."
PREVIOUS = "## A weekend book exchange\n\nThe community center is organizing a book exchange for local residents. Volunteers will sort donated books by reading level and condition. Visitors can bring up to five books and choose the same number from the shelves."


def test_synthetic_continuation_reports_nothing():
    """A complete, original continuation passes the advisory checks."""
    assert check_tap(SYNTHETIC, PREVIOUS).notes() == []


# ------------------------------------------------- per-check planted cases ---


def test_stopping_mid_sentence_is_reported():
    c = check_tap(SYNTHETIC.rstrip(".") + ", which means", PREVIOUS)
    assert c.unfinished
    assert any('mid-sentence' in n for n in c.notes())


def test_stopping_on_heading_or_code_block_is_not_mid_sentence():
    """The old `needs_tail` rule: stopping on a heading means the next round writes from the body, it is not a broken sentence."""
    assert not check_tap(SYNTHETIC + '\n\n## \u4e0b\u4e00\u6b65\u600e\u4e48\u6392').unfinished
    assert not check_tap("```mermaid\ngraph TD\n  A-->B\n```").unfinished


def test_restating_paragraph_already_before_cursor_is_reported():
    """Check the detector with independently authored passages."""
    restated = PREVIOUS.split("\n\n")[1].replace("community center", "village hall").replace("local residents", "nearby families")
    c = check_tap(restated, PREVIOUS)
    assert c.restated, "if swapping two words defeats it, this check is as good as absent"
    mine, theirs, ratio = c.restated[0]
    assert ratio >= RESTATE_RATIO and "village hall" in mine and "community center" in theirs
    assert any('repeats earlier content' in n for n in c.notes())


def test_continuing_forward_is_not_restatement():
    """Check the detector with independently authored passages."""
    assert not check_tap(SYNTHETIC, PREVIOUS).restated


# Shared context does not imply that the next paragraph repeats the earlier one.
RELATED_PASSAGES = (
    "The library opens the reading room on Saturday mornings. Visitors browse the new titles, register for activities, and use the shared desks while volunteers organize the shelves.",
    "The library closes the reading room for maintenance on Wednesday afternoons. Staff inspect the lighting, replace worn labels, and repair the shared desks before the next public session.",
)


def test_related_synthetic_passages_are_not_restatement():
    from difflib import SequenceMatcher

    before, after = RELATED_PASSAGES
    ratio = SequenceMatcher(None, after, before).ratio()
    assert 0.35 <= ratio < RESTATE_RATIO
    assert check_tap(after, before).restated == []


def test_scaffold_headings_are_reported():
    assert scaffold_headings('## \u6536\u675f\uff1a\u4ece\u4e2a\u6848\u5230\u590d\u76d8\u6846\u67b6\n\u6b63\u6587') == ['\u6536\u675f\uff1a\u4ece\u4e2a\u6848\u5230\u590d\u76d8\u6846\u67b6']
    assert scaffold_headings('## \u6536\u675f\n\u6b63\u6587') == ['\u6536\u675f']
    c = check_tap('## \u603b\u7ed3\n\n' + SYNTHETIC.split("\n\n")[1])
    assert c.scaffold_titles == ['\u603b\u7ed3']
    assert any('self-contained conclusion' in n for n in c.notes())


def test_headings_carrying_information_are_not_scaffolding():
    assert scaffold_headings(SYNTHETIC) == []
    # The word "wrap-up" appearing in the **body** does not count -- the check judges headings
    assert scaffold_headings('## \u628a\u7a97\u53e3\u56fa\u5b9a\u4e0b\u6765\n\n\u8fd9\u4e00\u8282\u6536\u675f\u524d\u9762\u51e0\u70b9\u3002') == []


def test_english_scaffold_labels_and_prefixes_are_reported():
    assert scaffold_headings("## Closure\nText") == ["Closure"]
    assert scaffold_headings("## Summary: what comes next\nText") == ["Summary: what comes next"]
    assert scaffold_headings("## Release moves to Friday\nText") == []


def test_prompt_examples_copied_into_body_are_reported():
    c = check_tap("## Testing\n\nThe plan uses Prototype test as its next milestone.")
    assert c.leaked_examples == ["Prototype test"]
    assert leaked_prompt_examples("## Testing\nA prototype was tested.") == []
    assert c.notes()


# --------------------------------------------------- two gates ---


def test_every_entry_in_example_list_appears_verbatim_in_prompts():
    """**The premise of this check** is that these phrases come from the prompts -- a phrase from elsewhere would not be
    "prompt leakage" but "the model thought up a heading itself", and the two cannot share one diagnosis.

    When moving the list this gate caught an already-drifted entry on the spot. The maintenance convention is unchanged, only
    now enforced by a test: when adding an example with concrete content to `prompts/`, add an entry to the list too.
    """
    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "harness" / "prompts"
    blob = "\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.py"))
    missing = [e for e in PROMPT_EXAMPLES if e not in blob]
    assert not missing, f"these examples no longer exist in the prompts, keeping them only causes false alarms: {missing}"




# ------------------------------------------------- the wiring half ---


def test_judge_but_do_not_block_writing_this_segment_into_body():
    """**Same shape as `slides` / `skeleton`**: the stream has already been sent to the user, the check is only attached."""
    import inspect

    from app.routers import compose

    src = inspect.getsource(compose.magic_tap)
    assert "check_tap" in src, "magic-tap is not wired to the health check"
    after = src.split("check_tap")[1]
    assert "raise HTTPException" not in after and "return" not in after.split("yield sse(\"done\"")[0], (
        "The health-check result must not block this segment from entering the body -- magic tap is a one-shot product")
    # The result is sent to the user together with the product, not just written in a server-side log
    assert '"notes": check_tap' in src
    # **What is judged must be only the segment written this time**: `written` is the output, `body.content` only the
    # "body already existing before the cursor". If the two were concatenated and judged, an old note of the user's own
    # that stops mid-sentence would make every continuation report something unrelated to this one -- and the pure-function
    # cases cannot see how the endpoint calls it (the first version of mutation check 9 slipped through exactly this way).
    assert "check_tap(written, body.content)" in src


def test_health_check_only_looks_at_the_segment_written_this_time():
    """Whatever flaws the user's own body has are not magic tap's business -- if the whole note were judged, an old note
    stopping mid-sentence would make every continuation report something unrelated to this one."""
    dirty = '\u4e0a\u4e00\u6bb5\u505c\u5728\u8fd9\u91cc\uff0c\u7136\u540e'          # the user's own body, stopping mid-sentence
    assert check_tap(SYNTHETIC, dirty).notes() == []
