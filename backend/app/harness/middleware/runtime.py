"""Turn each round's observations into the next round's run parameters.

Everything a round produces -- the scores, the scorer's own wording, how many
tools were called, how many facts came back, whether revisions applied -- was
being read once and thrown away. This is the feedback path that was missing:
the run reads its own behaviour and changes how it runs.

It also reads *across* runs. ``recent()`` had an implementation and no
callers, so a note that failed the same way three times started the fourth
attempt with exactly the settings that failed before.
"""

from __future__ import annotations

from typing import AsyncIterator

from .. import adapter as harness_adapter
from .. import policy as runtime_policy
from ..tools import memory_tools
from ..events import CUSTOM_POLICY, Event
from ..state import State


class Runtime:
    name = "runtime"
    hooks = ("before_run", "after_judge")
    after: tuple[str, ...] = ()

    async def before_run(self, st: State) -> AsyncIterator[Event]:
        policy, reasons = runtime_policy.from_history(
            harness_adapter.SqliteRunHistoryStore().recent(st.ctx.note_id, limit=3))
        st.bag["policy"] = policy
        if reasons:
            yield Event.custom(CUSTOM_POLICY, {
                "round": 0, "policy": policy.snapshot(), "reasons": reasons})

    async def after_judge(self, st: State) -> AsyncIterator[Event]:
        if not st.ev:
            return
        policy = st.bag.get("policy") or runtime_policy.RuntimePolicy()
        trace = st.trace
        policy, reasons = runtime_policy.adjust(policy, runtime_policy.RoundFeedback(
            scores={n: s.level for n, s in st.ev.scores.items()},
            notes={n: s.note for n, s in st.ev.scores.items()},
            weakest=st.ev.weakest or "",
            status=st.ev.status,
            tool_calls=len(trace.calls) if trace else 0,
            tool_facts=len(st.facts_new),
            tools_used=tuple(sorted({c[0] for c in trace.calls})) if trace else (),
            tool_truncated=bool(trace and trace.truncated),


            tool_stopped_barren=bool(trace and trace.stopped_barren),
            revisions_applied=st.bag.get("revisions_applied", 0),
            stall_rounds=st.bag.get("stall_rounds", 0),
            kb_empty=memory_tools.kb_is_empty(st.ctx.user),
        ))
        st.bag["policy"] = policy
        if reasons:
            yield Event.custom(CUSTOM_POLICY, {
                "round": st.round, "policy": policy.snapshot(), "reasons": reasons})
