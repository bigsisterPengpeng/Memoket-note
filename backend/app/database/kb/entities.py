"""Canonical entity presentation, variant grouping and deduplicated fact counts."""

from __future__ import annotations

import re
from collections import Counter

_STRIP = re.compile(r"[\s_\-\.·'’]+")


def norm_key(s: str) -> str:
    return _STRIP.sub("", (s or "").lower())


class EntityGroups:
    def __init__(self, canon_of: dict[str, str], members_of: dict[str, list[str]],
                 names: dict[str, str], dropped: "set[str] | None" = None):
        self.canon_of = canon_of
        self.members_of = members_of
        self._names = names


        self.dropped = dropped or set()

    def is_dropped(self, code: str) -> bool:
        return self.canon(code) in self.dropped or code in self.dropped

    def canon(self, code: str) -> str:
        return self.canon_of.get(code, code)

    def members(self, code: str) -> list[str]:
        return self.members_of.get(self.canon(code), [code])

    def name(self, code: str) -> str:
        c = self.canon(code)
        return self._names.get(c, c)

    def variants(self, code: str) -> list[str]:
        c = self.canon(code)
        return [self._names.get(m, m) for m in self.members_of.get(c, []) if m != c]


def build(vocab, entity_count: Counter | dict,
          extra_pairs: "list[tuple[str, str]] | tuple" = (),
          dropped: "set[str] | None" = None) -> EntityGroups:
    codes = list(vocab.entities.keys())
    parent = {c: c for c in codes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    seen: dict[str, str] = {}
    for code in codes:
        e = vocab.entities[code]
        keys = {norm_key(code), norm_key(getattr(e, "name", "") or code)}
        keys |= {norm_key(a) for a in (getattr(e, "aliases", None) or ())}
        keys.discard("")
        for k in keys:
            if k in seen:
                union(code, seen[k])
            else:
                seen[k] = code
    for a, b in extra_pairs or ():
        if a in parent and b in parent:
            union(a, b)

    groups: dict[str, list[str]] = {}
    for code in codes:
        groups.setdefault(find(code), []).append(code)
    canon_of: dict[str, str] = {}
    members_of: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for members in groups.values():
        members.sort(key=lambda c: (-int(entity_count.get(c, 0)), len(c), c))
        canon = members[0]
        for m in members:
            canon_of[m] = canon
            e = vocab.entities[m]
            names[m] = getattr(e, "name", "") or m
        members_of[canon] = members
    return EntityGroups(canon_of, members_of, names, set(dropped or ()))


def user_decisions(user_id: str) -> tuple[list[tuple[str, str]], set[str]]:
    if not user_id:
        return [], set()
    try:
        from .. import store as store_mod
        rows = store_mod.entity_decisions(user_id)
    except Exception:      # noqa: BLE001
        return [], set()
    same = [(d["code_a"], d["code_b"]) for d in rows if d["decision"] == "same"]
    drop = {d["code_a"] for d in rows if d["decision"] == "drop_a"}
    drop |= {d["code_b"] for d in rows if d["decision"] == "drop_b"}
    return same, drop


def for_store(store, vocab) -> EntityGroups:
    n = len(getattr(store, "facts", {}) or {})
    cached = getattr(store, "_memoket_entity_groups", None)
    if cached and cached[0] == n:
        return cached[1]
    pairs, drop = user_decisions(getattr(store, "_memoket_user", "") or "")
    count = Counter(c for f in store.facts.values() for c in f.entities)
    g = build(vocab, count, pairs, drop)
    try:
        store._memoket_entity_groups = (n, g)
    except Exception:      # noqa: BLE001
        pass
    return g
