"""Track token and request budgets, including nested tool/model calls."""

from __future__ import annotations

from typing import AsyncIterator

from ...util import llm
from .. import params
from ..events import CUSTOM_COST, CUSTOM_WARNING, Event
from ..state import State


def spent(st: State) -> int:
    sink = st.bag.get("cost") or {}
    return int(sink.get("prompt_tokens", 0)) + int(sink.get("completion_tokens", 0))


def over_cap(st: State) -> bool:
    cap = int(st.bag.get("token_cap") or 0)
    return cap > 0 and spent(st) >= cap


class Cost:
    name = "cost"
    hooks = ("before_run", "after_round")
    after: tuple[str, ...] = ()

    async def before_run(self, st: State) -> None:
        sink = st.bag.setdefault("cost", {"calls": 0, "prompt_tokens": 0,
                                          "completion_tokens": 0, "cached_tokens": 0})
        llm.bind_usage_sink(sink)


        st.bag.setdefault("token_cap", params.RUN_TOKEN_CAP)

    async def after_round(self, st: State) -> AsyncIterator[Event]:
        sink = st.bag.get("cost") or {}
        if sink.get("tally_error"):

            yield Event.custom(CUSTOM_WARNING, {
                "middleware": self.name, "hook": "after_round",
                "error": f"Usage was not recorded for {sink['tally_error']} calls; reported cost is lower than actual usage.",
            })
        if not over_cap(st):
            return
        yield Event.custom(CUSTOM_COST, {
            "round": st.round,
            "tokens": spent(st),
            "cap": int(st.bag.get("token_cap") or 0),
            "calls": int(sink.get("calls", 0)),
            "detail": (f"Stopped at round {st.round} after spending {spent(st):,} token（{sink.get('calls', 0)} calls), reaching the per-run token cap of {int(st.bag.get('token_cap') or 0):,}."),
        })
