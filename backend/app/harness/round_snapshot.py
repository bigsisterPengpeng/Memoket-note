"""Capture the pre-round note revision before new text is committed; routers wrap event streams with this adapter."""

from __future__ import annotations

import uuid
from typing import AsyncIterator

from ..database import store
from .events import Event, EventType
from .middleware.save import writes_note
from .state import State


def _run_id(st: State) -> str:
    if not st.bag.get("run_id"):
        st.bag["run_id"] = uuid.uuid4().hex[:12]
    return str(st.bag["run_id"])


def _save(st: State, reason: str, round_no: int) -> str:
    if not writes_note(st) or not st.ctx.note_id or not (st.content or "").strip():
        return ""
    try:
        return store.snapshot_content(st.ctx.user, st.ctx.note_id, st.ctx.note_title, st.content,
                                      reason, run_id=_run_id(st), round_no=round_no)
    except Exception:                                   # noqa: BLE001
        return ""


async def with_round_snapshots(events: AsyncIterator[Event], st: State) -> AsyncIterator[Event]:
    last_round = 0
    async for event in events:
        if event.type is EventType.STEP_STARTED:
            last_round = int(event.data.get("step") or st.round or 0)
            _save(st, store.REVISION_REASON_ROUND, last_round)
        elif event.type is EventType.RUN_FINISHED and last_round:


            if not (st.ctx.note_id and store.find_run_revision(
                    st.ctx.user, st.ctx.note_id, str(st.bag.get("run_id") or ""), store.REVISION_REASON_HARNESS)):
                _save(st, store.REVISION_REASON_RUN_END, last_round)
        yield event
