"""Show the user what the tools actually returned.

Grounding cannot be the model's own say-so. Every harness already had some
version of this -- each with its own event shape -- because the provenance
panel is what lets a user check a number instead of trusting it. One
implementation, one payload shape, every harness.
"""

from __future__ import annotations

from typing import AsyncIterator

from ..events import CUSTOM_ROUND, Event
from ..state import State


class Provenance:
    """Report what this round gathered: every tool call, then a summary.

    Named for what it is rather than for the object it reads. It was ``Trace``
    once, which collided with ``State.trace`` -- the tool trace itself -- and
    made "is this the middleware or the field" a question you had to answer by
    reading. Grounding that the user can check is the capability; ToolTrace is
    just where the data comes from.

    The summary is what the round counter and the sources panel read. It has
    to come *after* prepare rather than at the round's start, because before
    prepare there is nothing to report -- and a round header reading "0 facts"
    that never updates is worse than none.
    """

    name = "provenance"
    hooks = ("after_prepare",)
    after: tuple[str, ...] = ("facts",)   # Facts is what decides a call counted

    async def after_prepare(self, st: State) -> AsyncIterator[Event]:
        if st.trace is not None and st.trace.used:
            for name, args, result in st.trace.calls[st.trace.reported:]:
                yield Event.tool_result(name, args, result or "")
            st.trace.reported = len(st.trace.calls)

        yield Event.custom(CUSTOM_ROUND, {
            "round": st.round,
            "max_rounds": st.mode.max_rounds,
            "facts": len(st.facts_new),


            "tool_calls": (len(st.trace.calls) if st.trace is not None else 0),
            "sources": st.facts_new[:6],
            "revisions_applied": st.bag.get("revisions_applied", 0),
            "skipped_continue": bool(st.bag.get("cleanup_only")),


            "kb_empty": _kb_empty(st),


            **_steer_payload(st),


            "checks_total": len(st.mode.checks),


            **_cite_payload(st.bag.get("cite_cover_run")),


            "depth_dropped": int(getattr(st.trace, "dropped_depth", 0) or 0),
            "depth_dropped_all": bool(getattr(st.trace, "stopped_all_dropped", False)),


            **_irrelevant_payload(st.bag.pop("facts_irrelevant", None),
                                  bool(st.bag.pop("facts_irrelevant_dropped", False))),
        })


def _cite_payload(run) -> dict:
    located, marked, matched = (run or (0, 0, 0))
    return {"cite_located": int(located), "cite_marked": int(marked),
            "cite_matched": int(matched)}


def _irrelevant_payload(dropped, really_dropped: bool) -> dict:
    items = list(dropped or [])
    from ..checks.relevance import fact_body
    return {
        "facts_irrelevant": len(items),
        "irrelevant_dropped": really_dropped,
        "irrelevant_sample": [fact_body(f)[:60] for f, _n in items[:3]],
    }


def _steer_payload(st: State) -> dict:
    from ..policy import MATERIAL_DIMS
    dim = str(st.bag.get("focus") or "")
    return {
        "steer": (st.steer or "")[:300],
        "steer_dim": dim,


        "steer_material": bool(dim) and dim in MATERIAL_DIMS,
        "steer_in_plan": st.bag.pop("steer_in_plan", None),
    }


def _kb_empty(st) -> bool:
    try:
        from ..tools.memory_tools import kb_is_empty
        return kb_is_empty(st.ctx.user)
    except Exception:      # noqa: BLE001
        return False
