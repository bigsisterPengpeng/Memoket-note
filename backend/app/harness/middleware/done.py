"""Install completion checks from the current note task; user-confirmed criteria are not rejudged."""

from __future__ import annotations

import dataclasses

from ...editor import intent as doc_intent
from ..checks import done as done_checks
from ..state import State


class DoneCriteria:
    name = "done_criteria"
    hooks = ("before_run",)
    after: tuple[str, ...] = ()

    async def before_run(self, st: State) -> None:
        done = doc_intent.done_of(st.ctx.intent)
        if not done:
            return
        checked = tuple(getattr(st.ctx, "intent_checked", ()) or ())
        if not done_checks.judgeable(done, checked, polish=bool(st.bag.get("polish"))):
            return
        if done_checks.done_criteria not in st.mode.checks:
            st.mode = dataclasses.replace(st.mode, checks=insert_done(st.mode.checks))


_AFTER = "material_used"


def insert_done(checks: tuple) -> tuple:
    names = [getattr(c, "__name__", "") for c in checks]
    pos = names.index(_AFTER) + 1 if _AFTER in names else len(checks)
    return checks[:pos] + (done_checks.done_criteria,) + checks[pos:]
