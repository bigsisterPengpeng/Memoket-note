"""Store and present ingestion conflict candidates; model confirmation is supplied by higher layers."""

from __future__ import annotations

from .. import store
from . import relations


Confirm = "Callable[[str, list[dict], dict[str, dict]], list[dict]]"


def scan_session(mem, user_id: str, session_id: str, *, source: str = "",
                 confirm=None) -> int:
    new_facts = [f for f in mem.facts_for_prefix(session_id) if f.get("unit") == session_id]
    if not new_facts:
        return 0
    stem = session_id.rsplit("-", 1)[0] + "-"
    superseded = mem.fact_attrs("superseded_by")


    common = mem.common_term()
    added = 0
    for nf in new_facts:
        text = nf.get("text") or ""
        if not any(ch.isdigit() for ch in text):
            continue
        rows, _terms, _took = mem.recall(text, limit=8)
        others = [r for r in rows
                  if r["id"] != nf["id"] and not (r.get("unit") or "").startswith(stem) and r["id"] not in superseded]
        cands = [c for c in relations.detect(text, others, common=common) if c["relation"] == "conflict"]
        if not cands:
            continue
        if confirm is not None:
            cands = confirm(text, cands, {r["id"]: r for r in others})
        for c in cands:
            for old_id in c["fact_ids"]:
                if store.add_conflict(user_id, nf["id"], old_id, c.get("unit") or "", c["say"], source):
                    added += 1
    return added
