"""Bound historical round feedback before passing it to later generation and judging."""

from __future__ import annotations

from ..types import RunRecord

from .. import adapter as harness_adapter
from ..state import State


def records_this_run(st: State) -> bool:
    abnormal = st.stopped in {"client_disconnected", "interrupted", "error"}
    return (st.round >= 1 or abnormal) and st.stopped != "awaiting_review"


class History:
    name = "history"
    hooks = ("after_run",)


    after: tuple[str, ...] = ("cross_run",)

    async def after_run(self, st: State) -> None:
        if not records_this_run(st):
            return
        scores = final_scores(st)
        cost = st.bag.get("cost") or {}
        harness_adapter.SqliteRunHistoryStore().record(RunRecord(
            key=f"{st.mode.key}:{st.ctx.note_id}",


            run_id=str(st.bag.get("run_id") or ""),
            tokens=int(cost.get("prompt_tokens", 0)) + int(cost.get("completion_tokens", 0)),
            calls=int(cost.get("calls", 0)),


            status=(st.ev.status if st.ev and not st.skip_judge else "continue"),


            stopped=st.stopped,
            rounds=st.round,
            final_scores=scores,
            weak_dimensions=[n for n, lv in scores.items() if lv < 2],
        ))


def final_scores(st: State) -> dict[str, int]:
    if st.ev is not None and not st.skip_judge:
        return {name: s.level for name, s in st.ev.scores.items()}
    vectors = st.bag.get("score_vectors") or []
    return dict(vectors[-1]) if vectors else {}
