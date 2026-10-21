"""Keep the strongest eligible round and restore it when later output regresses."""

from __future__ import annotations

from ..state import State


NOT_A_VETO = ("done_criteria", "citations_present")


class BestOf:
    name = "best_of"
    hooks = ("after_judge",)
    after: tuple[str, ...] = ()

    async def after_judge(self, st: State) -> None:
        was = st.best[0] if st.best is not None else None
        rank = st.rank()
        unmet = st.coverage_unmet()
        if st.skip_judge and st.bag.get("short_circuit") in NOT_A_VETO and st.bag.get("prev_rank") is not None:

            rank = tuple(st.bag["prev_rank"])
            unmet = bool(st.bag.get("prev_coverage_unmet"))
        if st.best is None or rank >= st.best[0]:
            st.best = (rank, st.content)


            if st.ev is not None and not st.skip_judge:
                st.best_ev = st.ev


            st.bag["best_coverage_unmet"] = unmet


        now = st.best[0] if st.best is not None else None
        st.bag["best_stall"] = (int(st.bag.get("best_stall", 0)) + 1
                                if was is not None and now is not None and now == was else 0)
        st.bag["prev_rank"] = rank
        st.bag["prev_coverage_unmet"] = unmet
