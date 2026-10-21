"""Batch 22 / plan 11.2: `best_of`'s scalar collapse, and the half it misses.

**The collapse itself: measured, left unchanged** (rationale in the module comment of `middleware/best_of.py`, numbers
reproducible with `scripts/best_of_pareto_probe.py`): across `harness_rounds` 447 rounds /
158 runs, the round `rank()` picked was **never once** Pareto-dominated by another round of the same run.

**What was actually measured** is that `loop._regressed`'s coverage guard only blocks half of it: it lets through
fluctuations where "this round has not been written enough yet", but does not let through the case where
"the best round ranks high precisely because it was not written enough".
"""

from __future__ import annotations

import asyncio
import dataclasses

from app.harness import loop, modes
from app.harness.middleware.best_of import BestOf
from app.harness.state import State
from app.harness.tools import ToolContext
from app.harness.types import DimensionScore, Evaluation

DIMS = ("spine_fidelity", "beat_coverage", "non_repetition",
        "factual_grounding", "coherence", "material_use")


def _st(round_=2, **kw):
    mode = dataclasses.replace(modes.NOTE, dims=DIMS, max_rounds=4, **kw)
    st = State(mode=mode, ctx=ToolContext(user="u", note_id="n", note_title="t"))
    st.round = round_
    return st


def _ev(**levels):
    return Evaluation(
        scores={d: DimensionScore(level=levels[d], note="") for d in DIMS},
        status="continue", weakest=min(levels, key=levels.get))


# Scores of the live capture at rounds 602/605, verbatim from `harness_rounds` run `2d64b594db9b`
# (`note:309f19202309`): round 1 is 537 chars, round 2 is 1092 chars.
ROUND1 = dict(spine_fidelity=2, beat_coverage=1, non_repetition=2,
              factual_grounding=2, coherence=2, material_use=2)
ROUND2 = dict(spine_fidelity=2, beat_coverage=2, non_repetition=1,
              factual_grounding=2, coherence=1, material_use=2)


def _replay(round1: dict, round2: dict) -> tuple[State, str | None]:
    """Run in real order: round 1 judged -> BestOf -> round 2 judged -> BestOf -> stop rule."""
    st = _st(round_=1)
    st.ev, st.content = _ev(**round1), '\u7b2c\u4e00\u8f6e\u5199\u7684'
    asyncio.run(BestOf().after_judge(st))
    st.round, st.ev, st.content = 2, _ev(**round2), '\u7b2c\u4e00\u8f6e\u5199\u7684 \u7b2c\u4e8c\u8f6e\u53c8\u5199\u7684'
    asyncio.run(BestOf().after_judge(st))
    return st, loop._regressed(st)


def test_round_that_just_got_coverage_up_to_target_is_not_a_regression():
    """Live capture: round 1 `beat_coverage=1` got (5, 1.83); round 2 wrote it up to 2,
    at the cost of `non_repetition` / `coherence` each dropping a level, getting (4, 1.67),
    `stopped=regressed` -> what was shipped was round 1's 537 chars."""
    st, hit = _replay(ROUND1, ROUND2)
    assert st.rank() < st.best[0], "premise: after the collapse this round really ranks lower"
    assert hit is None, "the best round had not been written enough at the time, so it does not qualify as the 'regression' baseline"


def test_regression_where_best_round_was_already_fully_written_still_blocked():
    """**Reverse gate**: changing the guard to always-True would also make the one above green. This one pins
    "what should stop must still stop" -- round 1 has all coverage at target, round 2 truly gets worse: that is a regression."""
    good = dict(ROUND1, beat_coverage=2)                 # coverage fully at target
    worse = dict(good, non_repetition=1, coherence=1)    # pure degradation, nothing gained in return
    st, hit = _replay(good, worse)
    assert st.rank() < st.best[0]
    assert hit == "regressed"


def test_best_of_records_whether_best_round_was_written_enough():
    st = _st(round_=1)
    st.ev, st.content = _ev(**ROUND1), '\u6b8b\u7bc7'
    asyncio.run(BestOf().after_judge(st))
    assert st.bag["best_coverage_unmet"] is True

    st.round, st.ev, st.content = 2, _ev(**dict(ROUND1, beat_coverage=2)), '\u5199\u591f\u4e86'
    asyncio.run(BestOf().after_judge(st))
    assert st.best[1] == '\u5199\u591f\u4e86', "premise: this round became the new best"
    assert st.bag["best_coverage_unmet"] is False, "when best changes this flag must change with it"


def test_coverage_flag_survives_snapshot():
    """For a run resumed after an end-of-round pause, `_regressed` must still be able to read it."""
    from app.harness import snapshot

    st = _st(round_=1)
    st.ev, st.content = _ev(**ROUND1), '\u6b8b\u7bc7'
    asyncio.run(BestOf().after_judge(st))
    back = snapshot.loads(snapshot.dumps(st), st.mode)
    assert back.bag["best_coverage_unmet"] is True
    assert back.best_ev is not None
    assert back.best_ev.status == st.ev.status
    assert back.best_ev.scores == st.ev.scores
