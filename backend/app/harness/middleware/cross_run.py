"""Carry bounded run context across writing actions without overwriting pre-run user text."""

from __future__ import annotations

from typing import AsyncIterator

from .. import adapter as harness_adapter
from ..events import CUSTOM_CROSS_RUN, Event
from ..state import State


def _rank(scores: dict[str, int]) -> tuple[int, float]:
    levels = list(scores.values())
    if not levels:
        return (-1, -1.0)
    return (sum(1 for v in levels if v >= 2), sum(levels) / len(levels))


def compare(now: dict[str, int], last: dict[str, int]) -> dict | None:
    if not now or not last or set(now) != set(last):
        return None
    a, b = _rank(now), _rank(last)
    if a >= b:
        return None
    worse = sorted(d for d in now if now[d] < last[d])
    return {
        "met": a[0], "last_met": b[0],
        "mean": round(a[1], 2), "last_mean": round(b[1], 2),
        "dimensions": worse,
    }


class CrossRun:
    name = "cross_run"
    hooks = ("after_run",)
    after: tuple[str, ...] = ()

    async def after_run(self, st: State) -> AsyncIterator[Event]:
        from .history import records_this_run, final_scores

        if not records_this_run(st):


            return
        now = final_scores(st)
        if not now:
            return
        recent = harness_adapter.SqliteRunHistoryStore().recent(
            f"{st.mode.key}:{st.ctx.note_id}", limit=1)
        if not recent:
            return
        diff = compare(now, recent[0].final_scores or {})
        if diff is None:
            return
        names = "、".join(diff["dimensions"])
        yield Event.custom(CUSTOM_CROSS_RUN, {
            **diff,
            "detail": (f"This run regressed from {diff['last_met']} satisfied dimensions to {diff['met']} ({names} declined). The previous body remains available in Version history."),
        })
