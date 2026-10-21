"""Freeze a run between rounds, and thaw it when the user comes back.

A run pauses at the end of a round so the user can accept or reject what it
just wrote. That only works if the run's memory survives the gap: the
material it gathered, the charts the tools produced, which passages it has
already rewritten, what the last round scored. Losing any of it means the
resumed run repeats work it already did -- and re-gathering costs a model
call per round.

**The hard part is ``bag``.** It is deliberately untyped -- middleware keeps
whatever it needs there -- so it holds a ``RuntimePolicy`` dataclass, a set
of edited anchors, and plain JSON besides. Rather than teach this module
about each middleware (which would put the coupling back that ``bag`` exists
to avoid), values are tagged on the way out and reconstructed on the way in.
Anything that still cannot be encoded is **dropped loudly**: the snapshot
records what it lost, so a resumed run missing a capability is visible
instead of mysterious.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from .types import DimensionScore, Evaluation

from .tools import ToolContext
from .state import State

# Bag values are tagged so a set doesn't come back as a list and a policy
# doesn't come back as a dict. The tag is a two-key object rather than a
# bare marker string, so a user's own dict can never be mistaken for one.
_TAG = "__t"
_VAL = "v"


def dumps(st: State) -> str:
    """Serialise a paused run. Returns JSON."""
    dropped: list[str] = []
    return json.dumps({
        "mode": st.mode.key,
        "round": st.round,
        "ctx": {"user": st.ctx.user, "note_id": st.ctx.note_id,
                "note_title": st.ctx.note_title,
                "content": st.ctx.content, "cursor": st.ctx.cursor,
                "intent": st.ctx.intent,
                "intent_checked": list(st.ctx.intent_checked),

                "tray": list(st.ctx.tray or [])},
        "before": st.before, "after": st.after,
        "content": st.content,
        "facts": st.facts, "charts": st.charts,
        "skill_bodies": st.skill_bodies,
        "skill_menu": [list(x) for x in st.skill_menu],


        "best": [list(st.best[0]), st.best[1]] if st.best else None,
        "best_ev": _ev_out(st.best_ev),
        "ev": _ev_out(st.ev),
        "bag": {k: _encode(v, k, dropped) for k, v in st.bag.items()},
        "dropped": dropped,
    }, ensure_ascii=False)


def loads(text: str, mode) -> State:
    """Rebuild a State. ``mode`` comes from ``modes.BLOCK``/``ALL``, not from
    the snapshot -- Mode is code, and a run resumed after a deploy should get
    the current checks and dimensions, not the ones frozen last week."""
    raw = json.loads(text)
    ctx = raw.get("ctx") or {}
    st = State(
        mode=mode,
        ctx=ToolContext(user=ctx.get("user", ""), note_id=ctx.get("note_id", ""),
                        note_title=ctx.get("note_title", ""),
                        content=ctx.get("content", ""),
                        cursor=int(ctx.get("cursor") or 0),
                        intent=str(ctx.get("intent") or ""),
                        intent_checked=tuple(str(x) for x in (ctx.get("intent_checked") or [])),
                        tray=[dict(t) for t in (ctx.get("tray") or []) if isinstance(t, dict)]),
        before=raw.get("before", ""), after=raw.get("after", ""),
        content=raw.get("content", ""),
    )
    st.round = int(raw.get("round") or 0)
    st.facts = list(raw.get("facts") or [])
    st.charts = list(raw.get("charts") or [])
    st.skill_bodies = list(raw.get("skill_bodies") or [])
    st.skill_menu = [tuple(x) for x in (raw.get("skill_menu") or [])]
    best = raw.get("best")
    st.best = ((tuple(best[0]), best[1]) if best else None)
    st.best_ev = _ev_in(raw.get("best_ev"))
    st.ev = _ev_in(raw.get("ev"))
    st.bag = {k: _decode(v) for k, v in (raw.get("bag") or {}).items()}
    # The tool pool writes skill bodies through this; without re-linking it a
    # resumed run's load_skill calls would append into a list nobody reads.
    st.ctx.scratch["skill_bodies"] = st.skill_bodies
    return st


def dropped_keys(text: str) -> list[str]:
    try:
        return list(json.loads(text).get("dropped") or [])
    except (ValueError, AttributeError):
        return []


# ------------------------------------------------------------------ codec ---


def _encode(value: Any, key: str, dropped: list[str]) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, set):
        return {_TAG: "set", _VAL: sorted(value)}
    if isinstance(value, tuple):
        return {_TAG: "tuple", _VAL: [_encode(v, key, dropped) for v in value]}
    if isinstance(value, list):
        return [_encode(v, key, dropped) for v in value]
    if isinstance(value, dict):
        return {str(k): _encode(v, key, dropped) for k, v in value.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {_TAG: "dc", "m": type(value).__module__,
                "n": type(value).__name__,
                _VAL: {f.name: _encode(getattr(value, f.name), key, dropped)
                       for f in dataclasses.fields(value)}}
    dropped.append(key)
    return None


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    tag = value.get(_TAG)
    if tag == "set":
        return set(value.get(_VAL) or [])
    if tag == "tuple":
        return tuple(_decode(v) for v in value.get(_VAL) or [])
    if tag == "dc":
        return _rebuild_dataclass(value)
    return {k: _decode(v) for k, v in value.items()}


def _rebuild_dataclass(value: dict) -> Any:
    """Reconstruct a dataclass by module and name.

    Falls back to the plain dict when the class no longer exists -- a
    middleware removed between pausing and resuming should not make the
    snapshot unloadable, and the dict still reads correctly through
    ``.get()``-style access.
    """
    import importlib

    fields = {k: _decode(v) for k, v in (value.get(_VAL) or {}).items()}
    try:
        cls = getattr(importlib.import_module(value["m"]), value["n"])
        return cls(**fields)
    except Exception:                                  # noqa: BLE001
        return fields


def _ev_out(ev: Evaluation | None) -> dict | None:
    if not ev:
        return None
    return {"status": ev.status, "weakest": ev.weakest,
            "blocked_reason": getattr(ev, "blocked_reason", "") or "",
            "scores": {k: {"level": s.level, "note": s.note}
                       for k, s in ev.scores.items()}}


def _ev_in(raw: dict | None) -> Evaluation | None:
    if not raw:
        return None
    return Evaluation(
        scores={k: DimensionScore(level=v["level"], note=v["note"])
                for k, v in (raw.get("scores") or {}).items()},
        status=raw.get("status", "continue"),
        weakest=raw.get("weakest"),
        blocked_reason=raw.get("blocked_reason", ""))
