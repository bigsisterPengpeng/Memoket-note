"""Helpers for producing read-only progress mirrors of workflow state."""
from __future__ import annotations

import re

from ..checks import grounding_rules as grounding_check


def _scrub_and_record(st, content: str) -> str:
    out, removed = grounding_check.scrub_meta_sentences_v(
        content, str(st.bag.get("content_at_start") or ""))
    if removed:
        st.bag.setdefault("scrubbed", []).extend(removed)
    return grounding_check.fix_bold_punct(out)

def _record_dropped(st, streamed: str, kept: str) -> None:
    def paras(t: str) -> list[str]:
        return [p.strip() for p in re.split(r"\n\s*\n", t or "") if p.strip()]
    kept_paras = set(paras(kept))
    kept_lines = {ln.strip() for ln in (kept or "").split("\n") if ln.strip()}
    gone: list[str] = []
    for p in paras(streamed):
        if p in kept_paras:
            continue

        lines = [ln.strip() for ln in p.split("\n") if ln.strip()]
        if not any(ln in kept_lines for ln in lines):
            gone.append(p)
        else:
            gone.extend(ln for ln in lines if ln not in kept_lines)
    if gone:
        st.bag.setdefault("dedup", []).extend(gone)
