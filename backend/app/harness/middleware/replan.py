"""Request and validate plan updates when the current skeleton no longer fits the draft."""

from __future__ import annotations

from typing import AsyncIterator

from .. import prompts
from ...util import llm
from .. import replan_rules
from ..events import CUSTOM_POLICY, CUSTOM_REPLAN, CUSTOM_SKELETON, Event
from ..state import State

MAX_REPLANS_PER_RUN = 2


class Replan:
    name = "replan"
    hooks = ("after_judge",)
    after: tuple[str, ...] = ("runtime",)   # reads policy.stuck_dims

    async def after_judge(self, st: State) -> AsyncIterator[Event]:
        if not st.ev or st.bag.get("outline_mode"):
            return
        used = st.bag.get("replans_used", 0)
        beats = beats_of(st)
        if used >= MAX_REPLANS_PER_RUN or not beats:
            return
        policy = st.bag.get("policy")
        do, why = replan_rules.should_replan(
            scores={n: s.level for n, s in st.ev.scores.items()},
            stuck_dims=getattr(policy, "stuck_dims", {}) or {},
            tool_facts=len(st.facts_new),
            replans_used=used)
        if not do:
            return

        spine = st.bag.get("spine", "")
        try:
            ops = await llm.complete_json(
                [{"role": "system", "content": prompts.REPLAN_SYSTEM},
                 {"role": "user", "content": prompts.replan_user(
                     st.ctx.note_title, spine, beats, st.content, st.facts, why)}],
                max_tokens=600, temperature=0.2)
        except Exception as exc:                       # noqa: BLE001
            yield Event.custom(CUSTOM_POLICY,
                               {"round": st.round, "reasons": [f"replan failed: {exc}"[:200]]})
            return
        if not isinstance(ops, list):
            return

        new_beats, changes = replan_rules.apply_beat_ops(beats, ops)


        if new_beats == beats:
            return
        st.bag["beats"] = new_beats
        st.bag["replans_used"] = used + 1
        yield Event.custom(CUSTOM_REPLAN, {
            "round": st.round, "why": why, "changes": changes, "beats": new_beats})
        # The skeleton panel has to follow: the run's goal just changed and
        # the user must be able to see what it changed to.
        yield Event.custom(CUSTOM_SKELETON, {"spine": spine, "beats": new_beats})


def beats_of(st: State) -> list[str]:
    """No beats means nothing to replan -- and an empty list would let the
    model invent a skeleton here, which is a different operation entirely."""
    return list(st.bag.get("beats") or [])
