"""Record proposed and applied edits for review and recovery."""

from __future__ import annotations

from ...database import store
from ..state import State
from .save import writes_note


class Edits:
    name = "edits"
    hooks = ("after_run",)

    after: tuple[str, ...] = ("history",)

    async def after_run(self, st: State) -> None:
        from .history import records_this_run

        if not writes_note(st):


            return
        if not records_this_run(st):
            return


        if (st.stopped in {"client_disconnected", "interrupted", "error"}
                and st.content == str(st.bag.get("content_at_start") or "")):
            return
        if not st.ctx.note_id or not (st.content or "").strip():
            return
        run_id = str(st.bag.get("run_id") or "")
        if not run_id:
            return


        rev = store.snapshot_note(st.ctx.user, st.ctx.note_id,
                                  store.REVISION_REASON_HARNESS, run_id=run_id, round_no=st.round)
        if not rev:
            return
        store.open_harness_edit(
            st.ctx.user, st.ctx.note_id,
            run_id=run_id, key=f"{st.mode.key}:{st.ctx.note_id}",
            revision_id=rev["id"],
            base_chars=len(str(st.bag.get("content_at_start") or "")),
            ai_chars=len(st.content or ""))
