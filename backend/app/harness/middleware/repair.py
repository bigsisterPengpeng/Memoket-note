"""Turn this round's reading into next round's plan.

There are two kinds of weak score and they call for opposite responses:

  * a *coverage* dimension is weak -> not enough has been written -> write more
  * an *inner quality* dimension is weak (repetition, incoherence) -> what is
    already written has a defect -> fix it, and add nothing

Continuing when the problem is repetition cannot work: text that already
repeats does not stop repeating by growing. The earlier version of this rule
keyed on a single dimension name (``non_repetition``) and oscillated
visibly in real runs -- the cleanup round fixed it, the weakest dimension
became something else, the next round wrote more and broke it again, back and
forth until the round cap. Both long-form harnesses now read the whole score
vector instead of the weakest name, and read it the same way.
"""

from __future__ import annotations

from typing import AsyncIterator

from .. import workflows
from ..events import CUSTOM_POLICY, Event
from ..state import State

# Dimensions that describe a defect in the existing text rather than an
# absence of text.


INNER_QUALITY = ("non_repetition", "coherence", "topic_fidelity", "prose_quality",
                 "workflow_fidelity")


STOP_ONLY = ("coherence",)
_REPAIRABLE = tuple(d for d in INNER_QUALITY if d not in STOP_ONLY)


class Repair:
    name = "repair"
    hooks = ("after_judge",)
    after: tuple[str, ...] = ()

    async def after_judge(self, st: State) -> AsyncIterator[Event]:
        pending: dict[str, int] = st.bag.setdefault("repair_pending", {})
        failed: dict[str, int] = st.bag.setdefault("repair_failed", {})
        attempts: dict[str, int] = st.bag.setdefault("repair_attempts", {})

        weak: list[str] = []
        gave_up: list[str] = []


        for d in _REPAIRABLE:
            if not st.ev or st.skip_judge:
                break
            s = st.ev.scores.get(d)
            if not s:
                continue
            if s.level >= 2:
                pending.pop(d, None)
                failed.pop(d, None)
                attempts.pop(d, None)
                continue
            if d in pending:
                previous = pending.pop(d)
                if s.level <= previous:


                    template_repair = (
                        workflows.recipe_of(st.ctx.intent)
                        and d in {"workflow_fidelity", "non_repetition", "prose_quality"}
                    )
                    if template_repair and attempts.get(d, 0) < 2:
                        weak.append(d)
                        continue
                    failed[d] = s.level
                else:
                    attempts[d] = 0
            if d in failed and s.level <= failed[d]:
                gave_up.append(d)
                continue
            weak.append(d)


        stop_only = [d for d in STOP_ONLY
                     if st.ev and not st.skip_judge
                     and (s := st.ev.scores.get(d)) and s.level < 2]

        st.bag["cleanup_only"] = bool(weak)
        for d in weak:
            pending[d] = st.ev.scores[d].level     # type: ignore[union-attr]
            attempts[d] = attempts.get(d, 0) + 1
        if weak or gave_up or stop_only:
            yield Event.custom(CUSTOM_POLICY, {
                "round": st.round,
                "note": "next round repairs what is written instead of "
                        "adding to it" if weak else
                        "repairing these did not move the score; writing instead"
                        if gave_up else
                        "these have no position-level probe: the score can only "
                        "stop the loop, not drive a repair round",
                "dimensions": weak,
                **({"gave_up": gave_up} if gave_up else {}),
                **({"stop_only": stop_only} if stop_only else {}),
            })
