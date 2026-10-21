"""Batch 23 / plan 12.3: the cost cap of a single run.

Before this there was **nothing at all**: `judge` only said continue / complete / blocked, and never asked
"is another dozen seconds worth it" ([MECH] section 7), and how much one run could spend was not constrained at all.

The cap number is in the comment on `params.RUN_TOKEN_CAP`, together with its distribution basis
(the 158 runs measured by `scripts/run_cost_probe.py`). This file watches the **mechanism**:
is the ledger kept correctly, does it really stop when exceeded, which copy is handed back when stopping, can the two persisted columns really be written.

**"After adding a field to the persisted data, ask: can every one of its values really be written?"** (lesson of batch 22:
the `stopped` column could never record `max_rounds` from the day it was added) -- so here there is a case
that runs for real to the end and reads `tokens` / `calls` / `stopped='cost_cap'` back from the database.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from app.database import store
from app.harness import loop, modes, params
from app.harness.events import CUSTOM_COST, CUSTOM_WARNING
from app.harness.middleware import BASE
from app.harness.middleware.cost import Cost, over_cap, spent
from app.harness.state import State
from app.harness.tools import ToolContext
from app.harness.types import DimensionScore, Evaluation, Hooks
from app.util import llm

DIMS = ("beat_coverage", "non_repetition", "factual_grounding")


def _st(cap=1000, **bag):
    st = State(mode=dataclasses.replace(modes.NOTE, dims=DIMS),
               ctx=ToolContext(user="u", note_id="n", note_title="t"))
    st.round = 1
    st.bag.update(bag)
    asyncio.run(Cost().before_run(st))
    # `asyncio.run` always runs in a **copied context**, so the `bind_usage_sink` above
    # bound that copy, which cannot get back to the test's own context. Here we bind again
    # the same dict -- it binds the dict itself, not a snapshot, so both sides record into the same ledger.
    # **The real-run path does not have this problem** (`loop.run`'s `before_run` and the later calls
    # are in the same task) -- the tests `test_exceeding_the_cap_stops_and_ships_the_best_round` / `test_run_cost_is_really_written_to_the_database`
    # below both really run `loop.run`, **never bind by hand**, and the ledger is still recorded.
    llm.bind_usage_sink(st.bag["cost"])
    st.bag["token_cap"] = cap
    return st


def _fire(st) -> list:
    async def go():
        return [e async for e in Cost().after_round(st)]
    return asyncio.run(go())


# ------------------------------------------------------------ is the ledger kept correctly

def test_every_usage_entry_is_added_to_this_runs_ledger():
    """`util/llm._record` is the only place in the whole repo that records usage (so only this one place needs hooking)."""
    st = _st()
    llm._record({"prompt_tokens": 100, "completion_tokens": 20,
                 "prompt_tokens_details": {"cached_tokens": 60}}, "m", 0.0)
    llm._record({"prompt_tokens": 7, "completion_tokens": 3}, "m", 0.0)
    assert st.bag["cost"] == {"calls": 2, "prompt_tokens": 107,
                              "completion_tokens": 23, "cached_tokens": 60}
    assert spent(st) == 130


def test_calls_without_a_bound_ledger_are_not_booked_to_anyone():
    """Background tasks / ingestion paths do not belong to any run at all."""
    token = llm.ctx_usage_sink.set(None)
    try:
        llm._record({"prompt_tokens": 9, "completion_tokens": 1}, "m", 0.0)   # must not blow up
    finally:
        llm.ctx_usage_sink.reset(token)


def test_resuming_a_paused_run_keeps_recording():
    """`bag` goes into the snapshot, so the first half's ledger comes back with it -- if recording restarted from 0, a pause
    would be equivalent to resetting the cap."""
    st = _st(cap=1000, cost={"calls": 5, "prompt_tokens": 400,
                             "completion_tokens": 100, "cached_tokens": 0})
    assert spent(st) == 500


def test_ledger_errors_must_be_loud_instead_of_silently_shrinking_cost():
    st = _st()
    llm._record({"prompt_tokens": "not-a-number"}, "m", 0.0)
    assert st.bag["cost"]["tally_error"] == 1
    events = _fire(st)
    assert any(e.data["name"] == CUSTOM_WARNING for e in events)


# ------------------------------------------------------------ does it stop when exceeded

def test_not_exceeded_neither_reports_nor_stops():
    st = _st(cap=1000)
    llm._record({"prompt_tokens": 500, "completion_tokens": 100}, "m", 0.0)
    assert _fire(st) == []
    assert loop._over_budget(st) is None


def test_exceeded_reports_one_event_with_numbers_and_the_stop_rule_fires():
    st = _st(cap=1000)
    llm._record({"prompt_tokens": 900, "completion_tokens": 200}, "m", 0.0)
    events = [e for e in _fire(st) if e.data["name"] == CUSTOM_COST]
    assert len(events) == 1
    v = events[0].data["value"]
    assert (v["tokens"], v["cap"], v["calls"]) == (1100, 1000, 1)
    assert "1,100" in v["detail"] and "1,000" in v["detail"], \
        "'stop and tell the user' must tell them the numbers, not just say it stopped"
    assert loop._over_budget(st) == "cost_cap"


@pytest.mark.parametrize("cap", [0, -1])
def test_cap_disabled_never_fires(cap):
    st = _st(cap=cap)
    llm._record({"prompt_tokens": 10 ** 9, "completion_tokens": 0}, "m", 0.0)
    assert not over_cap(st)
    assert loop._over_budget(st) is None
    assert _fire(st) == []


def test_cap_is_fixed_at_run_start_env_changes_midway_do_not_count(monkeypatch):
    """Switching the criterion mid-run would make it impossible to answer afterwards "why did this run stop"."""
    st = _st(cap=1000)
    monkeypatch.setattr(params, "RUN_TOKEN_CAP", 1)
    llm._record({"prompt_tokens": 500, "completion_tokens": 0}, "m", 0.0)
    assert not over_cap(st)


def test_default_cap_is_above_the_largest_run_measured_so_far():
    """500,000 is 2x the largest of the 158 runs (248,160). **It is a safety net, not a
    controller** -- a "safety net" that gets hit in normal use is not a safety net
    (the comment on `params.CONTINUE_MAX_TOKENS` was bought with the same thing)."""
    assert params.RUN_TOKEN_CAP >= 2 * 248_160


# ------------------------------------------------------------ which copy is handed back when stopping

class _Hooks(Hooks):
    """Burns a fixed number of tokens each round; the body gets longer and longer."""

    def __init__(self, per_round: int):
        self.per_round = per_round

    async def prepare(self, st):
        return [], None

    async def produce(self, st):
        llm._record({"prompt_tokens": self.per_round, "completion_tokens": 0}, "m", 0.0)
        text = f"Round {st.round}."
        st.content = st.content + text          # same as hooks/note.produce: output is the body
        yield text

    async def commit(self, st):
        return None


def _score_by_round(monkeypatch, levels_by_round: dict[int, dict[str, int]]):
    async def fake(st):
        lv = levels_by_round[st.round]
        return Evaluation(scores={k: DimensionScore(level=v, note="") for k, v in lv.items()},
                          status="continue", weakest=min(lv, key=lv.get))
    monkeypatch.setattr(loop, "_evaluate", fake)


def _run(st, hooks, mw):
    async def go():
        return [e async for e in loop.run(st, hooks, mw)]
    return asyncio.run(go())


def test_exceeding_the_cap_stops_and_ships_the_best_round(monkeypatch):
    """`cost_cap` has the same shape as the `else:` at the end of the loop (max rounds reached): **the reason for stopping
is unrelated to whether this round was well written**, which is exactly when "the last round is the least likely to be the best".
The list is `loop.SHIP_BEST_ON`."""
    _score_by_round(monkeypatch, {
        1: {"beat_coverage": 2, "non_repetition": 2, "factual_grounding": 1},
        2: {"beat_coverage": 1, "non_repetition": 1, "factual_grounding": 1},
    })
    mode = dataclasses.replace(modes.NOTE, dims=DIMS, max_rounds=5,
                               extra_mw=(), rails_off=("save", "edits"))
    st = State(mode=mode, ctx=ToolContext(user="u", note_id="n", note_title="t"))
    st.bag["token_cap"] = 900
    events = _run(st, _Hooks(500), [m for m in BASE
                                    if getattr(m, "name", "") in ("cost", "best_of")])
    done = [e for e in events if e.type.value == "RUN_FINISHED"][0]
    assert done.data["reason"] == "cost_cap"
    assert st.round == 2, "judged at round end, so at most one round of cost overshoot"
    assert done.data["content"] == "Round 1.", "what is shipped must be the best round"
    assert any(e.data.get("name") == CUSTOM_COST for e in events if e.data)


def test_a_run_that_can_complete_is_not_overridden_by_cost(monkeypatch):
    """`complete` / `blocked` are the run's real outcomes; spending up to the cap only means "could not finish
within budget", and should not override a good outcome."""
    async def fake(st):
        lv = {k: 2 for k in DIMS}
        return Evaluation(scores={k: DimensionScore(level=v, note="") for k, v in lv.items()},
                          status="complete", weakest="")
    monkeypatch.setattr(loop, "_evaluate", fake)
    mode = dataclasses.replace(modes.NOTE, dims=DIMS, max_rounds=5,
                               extra_mw=(), rails_off=("save", "edits"))
    st = State(mode=mode, ctx=ToolContext(user="u", note_id="n", note_title="t"))
    st.bag["token_cap"] = 1
    events = _run(st, _Hooks(500), [m for m in BASE
                                    if getattr(m, "name", "") in ("cost", "best_of")])
    assert [e for e in events if e.type.value == "RUN_FINISHED"][0].data["reason"] == "complete"


# ------------------------------------------------------------ the two persisted columns

def test_run_cost_is_really_written_to_the_database(monkeypatch):
    """Lesson of batch 22: the `stopped` column could never record `max_rounds` from the day it was added.
    **After adding a persisted field, ask "can every one of its values really be written"** -- so here
    we run once for real, then read the three things back from the database."""
    _score_by_round(monkeypatch, {
        1: {"beat_coverage": 2, "non_repetition": 2, "factual_grounding": 1},
        2: {"beat_coverage": 2, "non_repetition": 1, "factual_grounding": 1},
    })
    mode = dataclasses.replace(modes.NOTE, dims=DIMS, max_rounds=5,
                               extra_mw=(), rails_off=("save", "edits"))
    st = State(mode=mode, ctx=ToolContext(user="u", note_id="n", note_title="t"))
    st.bag["token_cap"] = 900
    _run(st, _Hooks(500), [m for m in BASE if getattr(m, "name", "")
                           in ("cost", "ledger", "best_of", "cross_run", "history")])

    rows = store.recent_harness_runs("note:n", limit=3)
    assert len(rows) == 1
    assert rows[0]["stopped"] == "cost_cap", "the new stop reason must really land in that column"
    with store.connect() as c:
        row = c.execute("SELECT id, tokens, calls FROM harness_runs").fetchone()
    assert row["tokens"] == 1000 and row["calls"] == 2
    assert row["id"] == st.bag["run_id"], \
        "harness_runs.id must be the same as harness_rounds.run_id (the three tables get a join key for the first time)"
    assert [r["run_id"] for r in store.rounds_of_run(st.bag["run_id"])] == \
        [st.bag["run_id"]] * 2
