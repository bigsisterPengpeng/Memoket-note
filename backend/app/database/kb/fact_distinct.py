"""Advisory grouping within a bounded retrieval-result screen.

Object and topic codes define comparable facts; only independent source units
can join a family. This does not measure literal similarity or prove factual
equivalence. Coverage counts measurable facts sharing a topic common to that
family. This measurement is not installed as a retrieval gate.

Historical calibration and its limitations are recorded separately in
tests/fixtures/retrieval-provenance.json and docs/retrieval-calibration.md.
"""

from __future__ import annotations

from itertools import combinations


FAMILY_MIN = 3


def measurable(fact) -> bool:
    return bool(getattr(fact, "obj", ())) and bool(getattr(fact, "topics", ()))


def same_thing(a, b) -> bool:
    return (bool(set(a.obj) & set(b.obj))
            and bool(set(a.topics) & set(b.topics))
            and a.unit != b.unit)


def largest_family(facts) -> list[int]:
    idx = [i for i, f in enumerate(facts) if measurable(f)]
    for size in range(len(idx), 0, -1):
        for combo in combinations(idx, size):
            if all(same_thing(facts[a], facts[b]) for a, b in combinations(combo, 2)):
                return list(combo)
    return []


def family_cover(facts, fam) -> int:
    if len(fam) < FAMILY_MIN:
        return 0
    common: set | None = None
    for i in fam:
        t = set(facts[i].topics)
        common = t if common is None else (common & t)
    idx = [i for i, f in enumerate(facts) if measurable(f)]
    best = 0
    for t in (common or set()):
        best = max(best, sum(1 for i in idx if t in facts[i].topics))
    return best


def screen_shape(facts) -> dict:
    fam = largest_family(facts)
    n = sum(1 for f in facts if measurable(f))
    cover = family_cover(facts, fam)
    return {"slots": len(facts), "measurable": n,
            "family": len(fam), "family_idx": fam, "cover": cover,
            "flagged": n >= FAMILY_MIN and len(fam) >= FAMILY_MIN
            and (len(fam) * 2 >= n or cover * 2 >= n)}
