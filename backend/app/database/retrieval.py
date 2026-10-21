"""Zero-LLM keyword retrieval, used as the fallback when the tool loop fails.

Defined in ``routers/compose`` and imported by two other routers. It touches
the store and the knowledge base, which makes it a capability rather than
part of any endpoint.

Why a fallback exists at all: an occasional tool-loop failure must not mean
writing with no material. "Never continue empty-handed" was learned from a
run that did.
"""

from __future__ import annotations

from .kb.recall import recall_clustered
from .kite.kite_memory import UserMemory

# Retrieve against the tail of what's written -- where the user is now is
# what's relevant, not the top of a long note.
TAIL_CHARS = 600

# The harness path uses a much shorter tail: there, stable anchors (title,
# spine, beats) lead the query and the prose tail only says "this is where
# we're up to". Letting the tail dominate made every round retrieve the same
# facts regardless of which section was being written.
TAIL_CHARS_FOR_HARNESS = 300


def format_fact(r: dict) -> str:
    d = (r.get("date") or r.get("when") or "").strip()
    fid = (r.get("id") or "").strip()
    entities = [str(x) for x in (r.get("entities") or []) if str(x).strip()]
    subject = f"[Subjects: {'、'.join(entities[:3])}] " if entities else ""
    head = (f"[{fid}] " if fid else "") + (f"[{d}] " if d else "") + subject
    return head + r["text"]


def retrieve(user: str, content: str, spine: str, beats: list[str], limit: int = 8,
              title: str = "", anchor_first: bool = False, scope: str = "all"):
    mem = UserMemory(user)
    if anchor_first:


        anchors = [a for a in (title, spine, " ".join(beats[-3:])) if a]
        query = "\n".join(anchors + [content[-TAIL_CHARS_FOR_HARNESS:]])
    else:


        query = content[-TAIL_CHARS:]
        hint = " ".join([spine] + beats[-3:]) if spine or beats else ""
        if hint:
            query = hint + "\n" + query
    # The harness writes whole sections, so it reads the codebook at cluster
    # grain; magic tap answers a cursor and reads it at topic grain. Same
    # data, two views -- see kb/clusters.py for why the fine topics stay.
    if anchor_first:
        rows, _terms, took = recall_clustered(
            mem, query, limit=limit, scope=scope,
            evidence=True, entity_guard=True)
    else:
        rows, _terms, took = mem.recall(query, limit=limit, scope=scope)
    hits = [r for r in rows if r.get("text")]


    texts = []
    for r in hits:


        if r.get("id") and not r.get("entities"):
            r = {**r, **(mem.fact_by_id(r["id"]) or {})}
        texts.append(format_fact(r))
    return texts, [r.get("id", "") for r in hits], took
