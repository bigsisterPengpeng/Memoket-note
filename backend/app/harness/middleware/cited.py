"""Attach source identifiers and preserve citation metadata across writing rounds."""

from __future__ import annotations

import re

from ..state import State

_HEAD = re.compile(r"^\[([A-Za-z0-9_\-]+)\]")


def cited_lines(content: str, facts: list[str], pool: list[str], lookup,
                cache: dict[str, str]) -> list[str]:
    from ..checks.citations import cited_ids, supplied_ids

    have = supplied_ids(facts)
    by_id: dict[str, str] = {}
    for f in pool:
        m = _HEAD.match(f or "")
        if m and m.group(1) not in by_id:
            by_id[m.group(1)] = f
    out: list[str] = []
    for fid in cited_ids(content):
        if fid in have:
            continue
        line = by_id.get(fid)
        if line is None:
            if fid not in cache:
                fact = lookup(fid) or {}
                text = str(fact.get("text") or "").strip()
                when = str(fact.get("when") or "").strip()
                cache[fid] = f"[{fid}] {text}" + (f"（{when}）" if when else "") if text else ""
            line = cache[fid]
        if line:
            out.append(line)
    return out


class Cited:
    name = "cited"
    hooks = ("after_prepare",)
    after: tuple[str, ...] = ("facts",)

    async def after_prepare(self, st: State) -> None:
        cache: dict[str, str] = st.bag.setdefault("cited_cache", {})
        lookup = _lookup_for(st)
        st.bag["cited_facts"] = cited_lines(
            st.content, list(st.facts), list(st.bag.get("facts_all") or []),
            lookup, cache)


def _lookup_for(st: State):
    user = getattr(st.ctx, "user", "")
    if not user:
        return lambda _fid: None
    try:
        from ...database.kite.kite_memory import UserMemory
        mem = UserMemory(user)
    except Exception:                                   # noqa: BLE001


        return lambda _fid: None

    def look(fid: str):
        try:
            return mem.fact_by_id(fid)
        except Exception:                               # noqa: BLE001
            return None
    return look
