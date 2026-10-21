"""Extract short user-written style examples without turning retrieved facts into style instructions."""

from __future__ import annotations

import re

from ..database import store

MAX_ANCHORS = 3


def _paragraphs(text: str) -> list[str]:
    out: list[str] = []
    for raw in re.split(r"\n\s*\n", text or ""):
        p = raw.strip()
        if (not 24 <= len(p) <= 420 or p.startswith(("#", "|", "```"))
                or re.search(r"\[[A-Za-z][A-Za-z0-9_-]*-\d+-[0-9A-Fa-f]+\]", p)):
            continue
        out.append(p)
    return out


def entries(user: str, note: dict, workflow: str = "") -> list[str]:
    anchors = _paragraphs(str(note.get("content") or ""))[:MAX_ANCHORS]
    if len(anchors) >= MAX_ANCHORS:
        return anchors
    for other in store.list_notes(user):
        if other.get("id") == note.get("id"):
            continue
        if workflow and (other.get("intent") or {}).get("workflow") != workflow:
            continue
        for p in _paragraphs(str(other.get("content") or "")):
            if p not in anchors:
                anchors.append(p)
            if len(anchors) >= MAX_ANCHORS:
                return anchors
    return anchors
