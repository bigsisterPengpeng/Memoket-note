"""Merge segments that **keep saying the same thing** into one block.

The frontend has an identical copy (`frontend/src/util/journeyRuns.ts`); the two sides use it for
different things:
  - the frontend lays out the timeline with it - one continuous activity spread over eight
    near-duplicate rows would make that page read like a running log;
  - the backend feeds the daily report with it - **feed the model the same thing eight times and it
    weighs it as eight things**, and what the day actually moved forward gets drowned out by
    those eight repeats.

**The two implementations must agree**, so they are pinned by the parity script
`frontend/scripts/check-journey-merge.mts` (which exists precisely to keep the shell's and the
backend's two segmentation implementations from drifting).
How the criterion was chosen and why the threshold is .45: see the comment in the TS copy - the
numbers were measured on real output.
"""

from __future__ import annotations

from datetime import datetime

SIM = 0.45
GAP_MIN = 15


def similar(a: str, b: str) -> float:
    """How alike two sentences are. Bigram Dice - **Chinese has no word boundaries**, and cutting
    bigrams by character works for Chinese and for the English identifiers mixed into it. No
    `difflib` here: this must match the frontend copy bit for bit, and `SequenceMatcher` cannot be
    reproduced faithfully in TS."""
    def grams(s: str) -> set[str]:
        t = "".join(s.lower().split())
        return {t[i:i + 2] for i in range(len(t) - 1)}
    A, B = grams(a), grams(b)
    if not A or not B:
        return 0.0
    return 2 * len(A & B) / (len(A) + len(B))


def _minutes_between(a: str, b: str) -> float:
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60
    except (TypeError, ValueError):
        return float("inf")          # unreadable time counts as far apart: better not to merge


def group_runs(segs: list[dict]) -> list[dict]:
    """Merge into blocks. Each block is `{"segs": [...], "start", "end", "app", "desc"}`.

    `desc` takes **the longest sentence**: they describe the same thing, so take the one with the
    most information - a concrete file name / error often appears in only one of them.
    """
    runs: list[dict] = []
    for s in segs:
        cur = runs[-1] if runs else None
        lead = cur["segs"][0] if cur else None
        fits = False
        if cur is not None and lead is not None and cur["app"] == s.get("app", ""):
            if _minutes_between(cur["end"], s.get("start", "")) < GAP_MIN:
                ld, sd = (lead.get("desc") or "").strip(), (s.get("desc") or "").strip()
                # Compare with the **block head**, not with the previous one: chaining one by one drifts
                # (a resembles b, b resembles c, yet a and c are already two different things).
                fits = similar(ld, sd) >= SIM if (ld or sd) else True
        if not fits:
            runs.append({"segs": [s], "start": s.get("start", ""), "end": s.get("end", ""),
                         "app": s.get("app", ""), "desc": s.get("desc") or ""})
            continue
        cur["segs"].append(s)
        cur["end"] = s.get("end", "")
        if len((s.get("desc") or "").strip()) > len(cur["desc"].strip()):
            cur["desc"] = s.get("desc") or ""
    return runs
