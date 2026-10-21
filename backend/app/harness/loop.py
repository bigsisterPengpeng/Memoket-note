"""The loop. One copy, hardcoded, shared by every harness.

All 12 frameworks surveyed hardcode their loop; none makes the step sequence
configurable. We had three hand-copied loops and paid for it four times with
"one harness has it, the other doesn't" bugs.

Read the loop and you'll notice two absences, both deliberate:

* **No middleware is named in here.** The chain is data; the loop only knows
  hook names. Adding a capability never touches this file.
* **No ``if mode.xxx``.** Differences are expressed as Mode fields, hooks and
  middleware. The first branch on a mode key means the design failed.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import functools
import inspect
import uuid
from typing import AsyncIterator, Sequence

from .checks import rubric
from .checks.rubric import evaluate
from .completion import unfinished_reasons

from . import adapter as harness_adapter
from . import score_context, workflows
from .events import CUSTOM_DEDUP, CUSTOM_EVALUATE, CUSTOM_INSERT_AT, CUSTOM_SCRUB, CUSTOM_WARNING, Event
from .middleware import BASE, verify
from .state import COVERAGE_DIMS, State      # noqa: F401
from .types import DimensionScore, Evaluation, Hooks, Middleware


__all__ = ["run", "COVERAGE_DIMS"]

async def run(st: State, hooks: Hooks,
              mw: Sequence[Middleware] | None = None) -> AsyncIterator[Event]:
    """Drive one run to completion.

    Yields AG-UI events throughout; the caller turns them into SSE frames.
    """
    chain = tuple(mw if mw is not None else BASE) + tuple(st.mode.extra_mw)
    chain = tuple(m for m in chain
                  if getattr(m, "name", "") not in st.mode.rails_off)
    verify(chain)       # declared ordering deps hold; fails loudly if not
    reason, committed, after_run_done = "max_rounds", False, False


    st.bag.setdefault("run_id", uuid.uuid4().hex[:12])


    st.bag["content_at_start"] = st.content

    try:


        yield Event.run_started(st.mode.key, st.mode.label)
        async for e in _fire(chain, "before_run", st):
            yield e


        pre_blocked = ""
        if st.round == 0 and st.mode.precheck is not None:
            pre_blocked = st.mode.precheck(st) or ""
        if pre_blocked:
            reason = "blocked"

        # **Counts on from where the run left off**, not from 1. ``st.round``
        # is rounds completed, which is zero for a fresh State and non-zero
        # for a resumed one. Restarting at 1 would re-arm every guard that

        # nothing is written yet, and on a resumed run that is false.
        for st.round in range(st.round + 1, 0 if pre_blocked else st.mode.max_rounds + 1):
            if st.request is not None and await st.request.is_disconnected():
                st.bag["cancel_reason"] = "client_disconnected"
                raise asyncio.CancelledError
            yield Event.step_started(st.round, st.mode.label)
            async for e in _fire(chain, "before_round", st):
                yield e

            # -- 1. gather -------------------------------------------------
            # Each step announces itself. The tool loop and the scoring call
            # each take tens of seconds, and without this the label sits on
            # "writing" through all of it -- the interface looks hung exactly
            # when the run is doing its slowest work.
            yield Event.activity(f"{_who(st)}: Gathering material…")
            with _step("tools"):
                st.facts_new, st.trace = await _wrap_prepare(chain, hooks.prepare, st)
            async for e in _fire(chain, "after_prepare", st):
                yield e

            # -- 2. produce ------------------------------------------------
            # One message per round, START/CONTENT*/END strictly paired: the
            # AG-UI state machine rejects two STARTs in a row, and a retrying
            # wrap_produce has to open a *new* message rather than continue
            # the old one (deltas already sent can't be taken back).
            async for e in _fire(chain, "before_produce", st):
                yield e
            yield Event.activity(f"{_who(st)}: {st.mode.verb}…")
            st.fresh = ""
            mid = f"r{st.round}"
            yield Event.text_start(mid)
            announced = False
            async for piece in _wrap_produce(chain, hooks.produce, st):


                if not announced:
                    announced = True
                    placed = st.bag.get("insert_at")
                    if placed and placed.get("pos") is not None:
                        yield Event.custom(CUSTOM_INSERT_AT, placed)
                st.fresh += piece
                yield Event.text_content(mid, piece)
            yield Event.text_end(mid)

            for sentence in st.bag.pop("scrubbed", None) or []:
                yield Event.custom(CUSTOM_SCRUB, {"round": st.round, "sentence": sentence, "why": 'Meta commentary'})

            for para in st.bag.pop("dedup", None) or []:
                yield Event.custom(CUSTOM_DEDUP, {"round": st.round, "paragraph": para})
            async for e in _fire(chain, "after_produce", st):
                yield e

            # -- 3. judge: cheap first ------------------------------------
            # Checks run in before_judge and may set skip_judge. A scoring
            # call costs tens of seconds; if a deterministic rule already
            # knows the answer, paying for it is pure waste.
            async for e in _fire(chain, "before_judge", st):
                yield e
            if not st.skip_judge:
                yield Event.activity(f"{_who(st)}: Checking…")
                with _step("judge"):
                    st.ev = await _score(st)


                _apply_completion_policy(st)
                if st.ev is None:
                    # An unjudged round counts towards the stall net. A
                    # one-off scoring failure recovers next round; repeated
                    # failure is indistinguishable from being stuck, and one
                    # safety net for both beats inventing a second policy.
                    st.bag["no_change_rounds"] = st.bag.get("no_change_rounds", 0) + 1
            yield Event.custom(CUSTOM_EVALUATE, _ev_payload(st))
            async for e in _fire(chain, "after_judge", st):
                yield e
            async for e in _fire(chain, "after_round", st):
                yield e

            yield Event.step_finished(st.round, st.content)

            hit = _stop(st)
            if hit:
                reason = hit


                if hit in SHIP_BEST_ON and st.best is not None:
                    _ship_best(st)
                break
            # The next round needs last round's diagnosis, and ``st.ev`` is
            # about to be cleared so no stop condition can act on a stale
            # score. Keeping the weak dimension **and the scorer's own words**
            # matters: passing only the name tells the revision pass "watch
            # for repetition" without saying what is repeating, and repetition
            # here is semantic -- difflib finds nothing, so the pass would
            # have no candidate at all.
            st.bag["focus"] = st.ev.weakest if st.ev else ""
            st.bag["focus_note"] = _weak_note(st)


            st.ev, st.skip_judge = None, False
        else:
            # Ran out of rounds without ever meeting the bar. "Never met the
            # bar" is precisely when the last round is least likely to be the
            # best one -- ship the best instead.
            if st.best is not None:
                _ship_best(st)

        st.stopped = reason
        await hooks.commit(st)
        committed = True
        async for e in _fire(chain, "after_run", st):
            yield e
        after_run_done = True
        finish_detail = pre_blocked or (
            st.ev.blocked_reason if st.ev and reason == "blocked" else "")
        if reason == "needs_input":
            finish_detail = "；".join(unfinished_reasons(
                st.content, st.bag.get("beats") or []))
        yield Event.run_finished(st.content, reason, finish_detail, _pause(st, reason))

    except asyncio.CancelledError:


        if not after_run_done:
            reason = await _cancel_reason(st)
            committed = await _finish_without_stream(chain, hooks, st, reason, committed)
        raise
    except GeneratorExit:


        if not after_run_done:
            committed = await _finish_without_stream(
                chain, hooks, st, "client_disconnected", committed)
        raise
    except Exception as exc:        # noqa: BLE001


        from ..util import llm as _llm
        committed = await _finish_without_stream(chain, hooks, st, "error", committed)
        yield Event.run_error(_llm.describe_error(exc))
    finally:
        # Losing five rounds of writing because round six blew up is the
        # worst possible failure. Shield it: after a CancelledError, a plain
        # ``await`` can be cancelled again before it finishes.
        if not committed and st.content:
            with contextlib.suppress(Exception):
                await asyncio.shield(_commit(hooks, st))


async def _commit(hooks: Hooks, st: State) -> None:
    await hooks.commit(st)


async def _cancel_reason(st: State) -> str:
    marked = str(st.bag.get("cancel_reason") or "")
    if marked:
        return marked
    if st.request is not None:
        with contextlib.suppress(Exception, asyncio.CancelledError):
            if await st.request.is_disconnected():
                return "client_disconnected"
    return "interrupted"


async def _finish_without_stream(chain: Sequence[Middleware], hooks: Hooks,
                                 st: State, reason: str, committed: bool) -> bool:
    st.stopped = reason
    if not committed and st.content:
        await _commit(hooks, st)
        committed = True
    async for _event in _fire(chain, "after_run", st):
        pass
    return committed


@contextlib.contextmanager
def _step(name: str):
    from ..util import llm as _llm
    base = _llm.ctx_feature.get() or ""
    token = _llm.ctx_feature.set(f"{base}:{name}" if base else name)
    try:
        yield
    finally:
        _llm.ctx_feature.reset(token)


def _who(st) -> str:
    """Include the round after the first so progress does not look stuck."""
    return st.mode.label if st.round <= 1 else f"{st.mode.label} · Round {st.round}"


def _pause(st: State, reason: str) -> str:
    """Freeze the run if it stopped to wait for the user; return the run id.

    Everything the next round needs is in ``State``, so pausing is one write
    and resuming is one read -- the loop itself has no idea this happened.
    """
    if reason != "awaiting_review":
        return ""
    from ..database import store
    from . import snapshot

    run_id = store.save_snapshot(st.ctx.user, st.ctx.note_id, st.mode.key,
                                 st.round, snapshot.dumps(st))
    store.prune_snapshots(st.ctx.user)
    return run_id


async def _score(st: State):
    try:
        return await _evaluate(st)
    except Exception:                                  # noqa: BLE001


        return None


# Avoid anchoring: never pass preceding-round scores to the judge.
async def _evaluate(st: State):
    """Score the current content against shared run evidence without prior-score anchoring."""


    ctx, tail = score_context.split_for_prompt(
        score_context.with_fresh(
            score_context.with_material(
                st.bag.get("score_context"),
                list(st.facts) + list(st.bag.get("cited_facts") or [])),
            st.content, str(st.bag.get("content_at_start") or "")))
    ev = await evaluate(
        harness_adapter.AppJudgeLLMClient(),
        content=score_context.body_for_scoring(
            st.content, keep_last_chars=st.mode.context_keep_last),
        dimensions=list(st.mode.dims),
        dup_hints=st.bag.get("dup_hints") or [],
        context=ctx,
        tail_context=tail,
    )


    haystack = "\n".join([st.content, str(st.bag.get("content_at_start") or ""),
                          *(st.facts or []), *(st.bag.get("cited_facts") or []),
                          *[str(v) for v in (st.bag.get("score_context") or {}).values()]])
    if ev is None:
        return None
    original_workflow_score = ev.scores.get("workflow_fidelity")
    ev, bad = rubric.drop_hallucinated(ev, haystack)


    required_workflow = any(dim.name == "workflow_fidelity" for dim in st.mode.dims)
    if (ev is not None and required_workflow
            and "workflow_fidelity" not in ev.scores
            and workflows.recipe_of(st.ctx.intent)):
        scores = dict(ev.scores)
        if original_workflow_score is not None and original_workflow_score.level < 2:
            replacement = DimensionScore(
                level=original_workflow_score.level,
                note=(original_workflow_score.note
                      + '(The judgment contains an invalid quotation anchor. Retain the issue type, verify against the full text during revision, and never edit based on a nonexistent quote.)'),
            )
        else:
            replacement = DimensionScore(
                level=1,
                note=('The workflow-quality judgment quoted text absent from the supplied material. This round cannot pass. Recheck the workflow contract next round; revise only sentences that violate it and introduce no new facts.'),
            )
        scores["workflow_fidelity"] = replacement
        ev = Evaluation(scores=scores, status="continue", weakest="workflow_fidelity")
    st.bag["judge_hallucinated"] = bad
    return ev


def _ev_payload(st: State) -> dict:
    bad = st.bag.pop("judge_hallucinated", None) or []
    if not st.ev:
        return {"round": st.round, "status": "unknown", "scores": {}, "judge_hallucinated": bad}
    return {
        "round": st.round,
        "status": st.ev.status,
        "weakest": st.ev.weakest,
        "scores": {k: {"level": s.level, "note": s.note}
                   for k, s in st.ev.scores.items()},
        "judge_hallucinated": bad,
    }


def _weak_note(st: State) -> str:
    """The scorer's sentence about the weakest dimension, on its own."""
    if not st.ev or not st.ev.weakest:
        return ""
    score = st.ev.scores.get(st.ev.weakest)
    return score.note if score else ""


# -- stop conditions --------------------------------------------------------
# Composable and OR-ed, like Vercel AI SDK's ``stopWhen``. Pure functions,
# read-only -- a stop condition that mutates state would make "why did it
# stop" unanswerable.


def _apply_completion_policy(st: State) -> None:
    if (st.ev is not None and st.ev.status == "complete"
            and st.bag.get("completion_policy") == "open"):
        st.bag["open_quality_ready"] = True
        st.ev = dataclasses.replace(st.ev, status="continue")

def _complete(st: State) -> str | None:
    if st.bag.get("completion_policy") == "open":
        return None
    if not (st.ev and st.ev.status == "complete"):
        return None
    # Block tools may intentionally generate templates or snippets containing
    # placeholders. This contract is for the two long-form writing harnesses:
    # they are the paths that claim an entire note/section is finished.
    if st.mode.key in {"note", "section"} and unfinished_reasons(
            st.content, st.bag.get("beats") or []):
        return "needs_input"
    return "complete"


def _blocked(st: State) -> str | None:
    return "blocked" if st.ev and st.ev.status == "blocked" else None


def _open_handoff(st: State) -> str | None:
    if st.bag.get("completion_policy") != "open":
        return None
    limit = max(1, int(st.bag.get("handoff_rounds") or 1))
    if st.bag.get("open_quality_ready") or st.round >= limit:
        return "open_handoff"
    return None


def _no_progress(st: State) -> str | None:
    """Nothing changed this round.

    A round can make progress without producing text: a cleanup round writes
    nothing and repairs what is already there. Counting that as no progress
    would stop the run exactly when the repair is working.
    """
    if (st.fresh.strip() or st.bag.get("revisions_applied")
            or st.bag.get("cleanup_only")):


        return None
    return "no_progress"


def _regressed(st: State) -> str | None:
    best = st.best
    if st.skip_judge:
        return None


    if st.ev is None:
        return None
    if st.bag.get("cleanup_only"):


        return None
    if st.coverage_unmet():
        return None


    if st.bag.get("best_coverage_unmet"):
        return None
    if best is None or not st.mode.dims or st.round >= st.mode.max_rounds:
        return None
    best_rank, _content = best
    if best_rank[0] < max(1, len(st.mode.dims) - 1):
        return None
    return "regressed" if st.rank() < best_rank else None


def _over_budget(st: State) -> str | None:
    from .middleware.cost import over_cap

    return "cost_cap" if over_cap(st) else None


# `middleware/best_of.BestOf.after_judge`。
SHIP_BEST_ON = ("regressed", "cost_cap", "check_stuck", "best_stalled", "material_used_up", "open_handoff")


def _ship_best(st: State) -> None:
    """Restore the highest-ranked retained round for delivery."""
    if st.best is None:
        return
    st.content = st.best[1]
    if st.best_ev is not None:
        st.ev = st.best_ev
        st.skip_judge = False

BUILTIN_STOPS = (_complete, _blocked, _open_handoff, _over_budget, _no_progress, _regressed)


def _stop(st: State) -> str | None:
    for cond in (*BUILTIN_STOPS, *st.mode.stop_when):
        reason = cond(st)
        if reason:
            return reason
    return None


# -- middleware plumbing ----------------------------------------------------

async def _fire(chain: Sequence[Middleware], hook: str,
                st: State) -> AsyncIterator[Event]:
    """Run one hook across the chain.

    **One middleware failing must not kill the run** -- that's the whole
    isolation benefit of packaging capabilities separately. But it must not
    be silent either: a failure becomes a CUSTOM warning event.
    """
    for m in chain:
        fn = getattr(m, hook, None)
        if fn is None:
            continue
        try:
            result = fn(st)
            if inspect.isasyncgen(result):
                async for event in result:
                    yield event
            else:
                await result
        except Exception as exc:                       # noqa: BLE001
            yield Event.custom(CUSTOM_WARNING, {
                "middleware": getattr(m, "name", type(m).__name__),
                "hook": hook,
                "error": f"{type(exc).__name__}: {exc}"[:200],
            })


async def _wrap_prepare(chain: Sequence[Middleware], handler, st: State):
    """Onion: the first middleware in the list wraps all the others.

    A wrapper can call the handler more than once (retry), not at all
    (short-circuit with a cached result), or rewrite what goes in and comes out.
    """
    call = handler
    for m in reversed([x for x in chain if hasattr(x, "wrap_prepare")]):
        call = functools.partial(m.wrap_prepare, handler=call)
    return await call(st)


def _wrap_produce(chain: Sequence[Middleware], handler, st: State) -> AsyncIterator[str]:
    """Same onion, for the streaming step.

    **A retry here has to be decided before the first delta goes out.** Once
    text has streamed to the client it can't be recalled; the only honest
    recovery is to end that message and open a new one.
    """
    call = handler
    for m in reversed([x for x in chain if hasattr(x, "wrap_produce")]):
        call = functools.partial(m.wrap_produce, handler=call)
    return call(st)
