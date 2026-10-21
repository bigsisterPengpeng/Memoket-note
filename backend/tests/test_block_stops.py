"""`stop_when` of the six block modes (plan 4.6 / [EVAL] issue 3).

Before this they had **none at all**: note had 4, section had 2, block had 0, and the only
way to finish early was `complete` / `blocked`, otherwise it ran the full 3 rounds.

[EVAL] then said "look at per-round data before adding". The data is in the 18 real runs / 38 rounds produced by
`scripts/block_rounds_probe.py`, and this test file
**replays the shapes of those real runs verbatim** -- not constructing a nice-looking case, but pinning the three live
trajectories as assertions (`prompt` with three rounds of identical scores, `analysis` with all tools repeated in round 3,
`table` with all tools repeated in round 2 but only reaching complete in round 3).

*The last one is the counter-example, and the most important of this batch*: following [EVAL] literally and adding "stop when tool
calls are all repeats" would stop that `table` run on an output that missed the target.
"""

from __future__ import annotations

from app.harness import modes
from app.harness.middleware.ledger import Ledger
from app.harness.state import State
from app.harness.tools import ToolContext
from app.harness.types import DimensionScore, Evaluation


def _st(mode_key: str = "prompt", round_: int = 2) -> State:
    st = State(mode=modes.BLOCK[mode_key],
               ctx=ToolContext(user="u", note_id="n"))
    st.round = round_
    return st


def _score(**levels) -> Evaluation:
    return Evaluation(scores={k: DimensionScore(v, "") for k, v in levels.items()},
                      status="continue", weakest=min(levels, key=levels.get))


# ------------------------------------------------- nothing_changed ---
#
# Live capture: the `prompt` run's score vectors of three rounds are verbatim identical
# (checklist_1/2/3 all 2, fits_context stuck at 1, follows_prompt / no_fabrication 2).

REAL_PROMPT_VECTOR = dict(checklist_1=2, checklist_2=2, checklist_3=2,
                          fits_context=1, follows_prompt=2, no_fabrication=2)


def test_all_six_block_modes_have_these_two_attached():
    """**Building a check is not the same as using a check.** Missing one mode raises no error, it just lets it
    keep running the full three rounds, which is exactly what this is meant to cure."""
    for key, mode in modes.BLOCK.items():
        names = {f.__name__ for f in mode.stop_when}
        assert names == {"nothing_changed", "tools_ran_dry"}, key


def test_stop_when_score_vector_is_identical_to_previous_round():
    st = _st()
    st.bag["score_vectors"] = [dict(REAL_PROMPT_VECTOR), dict(REAL_PROMPT_VECTOR)]
    assert modes.nothing_changed(st) == "nothing_changed"


def test_no_stop_when_one_dimension_moved():
    """Even if only from 1 to 2 -- any score movement shows this round's change fell into the view of some check."""
    st = _st()
    moved = dict(REAL_PROMPT_VECTOR, fits_context=2)
    st.bag["score_vectors"] = [dict(REAL_PROMPT_VECTOR), moved]
    assert modes.nothing_changed(st) is None


def test_no_stop_in_first_round():
    st = _st(round_=1)
    st.bag["score_vectors"] = [dict(REAL_PROMPT_VECTOR)]
    assert modes.nothing_changed(st) is None


def test_check_short_circuited_rounds_do_not_enter_comparison():
    """The `Evaluation` fabricated by a check has only one dimension, score 0, not comparable with real score vectors.
    If mixed in, two consecutive rounds bounced by the same check would be read as "nothing changed", while
    `Checks.STUCK_ROUNDS` makes other arrangements for that tier (blocking two rounds gives the revision a chance)."""
    import asyncio

    st = _st()
    st.ev = _score(table_validity=0)
    st.skip_judge = True
    asyncio.run(Ledger().after_judge(st))
    assert st.bag.get("score_vectors") in (None, [])

    st.ev, st.skip_judge = _score(**REAL_PROMPT_VECTOR), False
    asyncio.run(Ledger().after_judge(st))
    assert st.bag["score_vectors"] == [REAL_PROMPT_VECTOR]


# -------------------------------------------------- tools_ran_dry ---


def test_stop_when_tool_calls_are_all_repeats_and_this_round_is_not_the_best():
    """Live capture: round 3 of those two `analysis` runs -- 4 tool calls, 4 repeats,
    score bounced to 0 by `numbers_from_tools`, round 2 was shipped.
    (Fixture contents: round 3 body = "third round wrote", best = "second round wrote", Chinese data escaped.)"""
    st = _st("analysis", round_=3)
    st.content = '\u7b2c\u4e09\u8f6e\u5199\u7684'
    st.best = ((3, 1.4), '\u7b2c\u4e8c\u8f6e\u5199\u7684')
    st.bag["ledger_round"] = {"tool_calls": 4, "repeat_calls": 4}
    assert modes.tools_ran_dry(st) == "tools_ran_dry"


def test_no_stop_when_this_round_became_the_best_round():
    """**This is the one where the data vetoed the literal rule on the spot.**

    Live capture: in that `table` run, round 2 had all tools repeated (1 call, 1 repeat) and the body differed from
    the previous round by only 0.14, yet **round 3 only then reached `complete`**. Following the literal "stop when tools all repeat",
    that run would have been stopped on an output with `fits_context=1`.
    (Fixture: round 2 body = "second round wrote", and best is also "second round wrote".)
    """
    st = _st("table", round_=2)
    st.content = '\u7b2c\u4e8c\u8f6e\u5199\u7684'
    st.best = ((2, 1.67), '\u7b2c\u4e8c\u8f6e\u5199\u7684')          # this round is the best one
    st.bag["ledger_round"] = {"tool_calls": 1, "repeat_calls": 1}
    assert modes.tools_ran_dry(st) is None


def test_no_stop_when_new_queries_remain():
    st = _st("eda", round_=2)
    st.content = '\u8fd9\u4e00\u8f6e'
    st.best = ((1, 0.5), '\u4e0a\u4e00\u8f6e')
    st.bag["ledger_round"] = {"tool_calls": 4, "repeat_calls": 3}   # live capture: round 2 of eda
    assert modes.tools_ran_dry(st) is None


def test_zero_tool_calls_does_not_count_as_search_exhausted():
    """`prompt` / `custom` often call no tool at all (live capture: 9 of 38 rounds had tool_calls=0).
    "Did not search" and "searched to the end" are two different things -- the check prefers to be narrow.
    (Fixture bodies "this round" / "previous round" are Chinese data, escaped.)"""
    st = _st("custom", round_=2)
    st.content = '\u8fd9\u4e00\u8f6e'
    st.best = ((1, 0.5), '\u4e0a\u4e00\u8f6e')
    st.bag["ledger_round"] = {"tool_calls": 0, "repeat_calls": 0}
    assert modes.tools_ran_dry(st) is None


def test_first_round_does_not_count_as_search_exhausted():
    st = _st("eda", round_=1)
    st.bag["ledger_round"] = {"tool_calls": 2, "repeat_calls": 2}
    assert modes.tools_ran_dry(st) is None


# ----------------------------------------------------- order / boundaries ---


def test_round_reaching_target_always_stops_on_complete_first():
    """In the live runs `chart` and `table` each had a round 2 that was **both complete and all-tools-repeated**.
    `loop.BUILTIN_STOPS` (complete / blocked / no_progress / regressed) is ordered **before**
    `mode.stop_when`, so these two new checks cannot reach it -- the stop reason must still be
    `complete`, otherwise the SSE line would tell the user "search exhausted" when in fact the writing was done."""
    from app.harness import loop

    assert loop.BUILTIN_STOPS[0].__name__ == "_complete"
    st = _st("chart", round_=2)
    st.content = '\u8fd9\u4e00\u8f6e'
    st.best = ((4, 2.0), '\u4e0a\u4e00\u8f6e')
    st.bag["ledger_round"] = {"tool_calls": 1, "repeat_calls": 1}
    st.ev = Evaluation(scores={"chart_validity": DimensionScore(2, "")},
                       status="complete")
    assert loop._stop(st) == "complete"


def test_the_long_form_ones_were_not_displaced_by_these_two():
    """Block's stop conditions must not be attached to long-form: `material_used_up` / `stalled` /
    `nothing_left_to_fix` / `pause_for_review` were settled by people over many rounds across two batches."""
    # `check_stuck` (P6 issue 4) belongs to long-form alone: the same check ringing three rounds in a row stops it; block modes,
    # capped at three rounds, cannot reach that tier anyway.
    # `best_stalled` (P55 #4) likewise belongs to long-form alone: `best` not growing for 4 rounds; block's three-round cap cannot reach it either.
    assert {f.__name__ for f in modes.NOTE.stop_when} == {
        "check_stuck", "material_used_up", "stalled", "best_stalled",
        "no_actionable_repair", "nothing_left_to_fix", "pause_for_review"}
    assert {f.__name__ for f in modes.SECTION.stop_when} == {
        "check_stuck", "no_actionable_repair", "material_used_up", "pause_for_review"}


def test_stop_conditions_are_read_only():
    """The comment in `loop.py` spells it out: a stop condition that mutates state turns "why did it stop"
    into an unanswerable question. So "how much the previous round scored" is recorded by `Ledger`."""
    st = _st()
    st.bag["score_vectors"] = [dict(REAL_PROMPT_VECTOR), dict(REAL_PROMPT_VECTOR)]
    st.bag["ledger_round"] = {"tool_calls": 4, "repeat_calls": 4}
    before = repr(sorted(st.bag.items(), key=lambda kv: kv[0]))
    modes.nothing_changed(st)
    modes.tools_ran_dry(st)
    assert repr(sorted(st.bag.items(), key=lambda kv: kv[0])) == before
