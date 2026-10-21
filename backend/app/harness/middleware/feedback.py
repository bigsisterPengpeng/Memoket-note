"""Apply explicit user edit decisions as constraints for generation, revision and judging."""

from __future__ import annotations

import dataclasses

from .. import feedback
from ..state import State


class UserFeedbackCriteria:
    name = "user_feedback_criteria"
    hooks = ("before_run",)
    after: tuple[str, ...] = ()

    async def before_run(self, st: State) -> None:
        if not feedback.examples(st.bag.get("writing_feedback")):
            return
        dims = st.mode.dims
        checks = st.mode.checks
        if all(d.name != feedback.USER_ALIGNMENT.name for d in dims):
            dims = dims + (feedback.USER_ALIGNMENT,)
        if feedback.repeats_reverted_change not in checks:


            checks = (feedback.repeats_reverted_change,) + checks
        st.mode = dataclasses.replace(st.mode, dims=dims, checks=checks)
