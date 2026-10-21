"""Persist authoritative round and final bodies, run state and citations for writing modes that update a note."""

from __future__ import annotations

from ...database import store
from ..state import State


def persist(st: State) -> bool:
    if "save" in st.mode.rails_off:
        return False
    if not st.content.strip():
        return False


    store.update_note(st.ctx.user, st.ctx.note_id, st.ctx.note_title, st.content,
                      source="harness")


    st.bag["saved_content"] = st.content
    return True


def persist_if_changed(st: State) -> bool:
    if str(st.bag.get("saved_content") or "") == st.content:
        return False
    return persist(st)


def writes_note(st: State) -> bool:
    return (any(getattr(m, "name", "") == "save" for m in st.mode.extra_mw)
            and "save" not in st.mode.rails_off)


class Save:
    name = "save"


    hooks = ("after_produce", "after_round")
    after: tuple[str, ...] = ()

    async def after_produce(self, st: State) -> None:
        persist(st)

    async def after_round(self, st: State) -> None:
        persist_if_changed(st)
