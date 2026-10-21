"""Select and disclose reusable writing skills within the current mode and tool permissions."""

from __future__ import annotations

from typing import AsyncIterator

from .. import skills as skills_store
from ..events import CUSTOM_SKILLS, Event
from ..state import State


class Skills:
    name = "skills"
    # **before_round, not before_produce.** Tools only exist on the gather
    # call, so the menu has to be in context before gather runs -- a model
    # that first reads "these skills are available" while writing has already
    # passed the only point where it could load one. Measured: with this on
    # before_produce, ``load_skill`` was never called.
    hooks = ("before_round",)
    after: tuple[str, ...] = ()

    async def before_round(self, st: State) -> AsyncIterator[Event]:
        # First round only. ``skill_bodies`` also holds whatever the model
        # loaded via ``load_skill``, and recomputing every round would wipe
        # those out -- forcing it to re-load the same skill up to 8 times.
        if st.round > 1:
            return
        injected, listed = skills_store.for_scope(st.ctx.user, st.mode.skill_scope)
        st.skill_bodies = [s.body for s in injected]
        st.skill_menu = [(s.name, s.description) for s in listed]
        # Hand the tool layer the *same list object*, so a load_skill call
        # appends straight into the run's state. The tool pool stays unaware
        # that a harness exists -- it only sees a dict someone left for it.
        st.ctx.scratch["skill_bodies"] = st.skill_bodies
        yield Event.custom(CUSTOM_SKILLS, {
            "round": st.round,
            "scope": st.mode.skill_scope,
            "injected": [s.title for s in injected],
            "menu": [s.title for s in listed],
        })
