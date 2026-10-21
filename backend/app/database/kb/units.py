"""Group source units and label split materials while preserving original unit identifiers."""

from __future__ import annotations

import re
from collections import defaultdict

_PART = re.compile(r"^(.*)-(\d+)$")


def part_labels(units) -> dict[str, str]:
    groups: dict[tuple, list[tuple[int, str]]] = defaultdict(list)
    for u in units:
        m = _PART.match(u.id)
        stem, idx = (m.group(1), int(m.group(2))) if m else (u.id, 0)
        groups[(stem, u.date or "", u.title or "")].append((idx, u.id))
    out: dict[str, str] = {}
    for (stem, _date, title), members in groups.items():

        base = title or (f'Meeting record · {_date}' if _date else stem)
        if len(members) == 1:
            out[members[0][1]] = base
            continue
        members.sort()
        n = len(members)
        for k, (_idx, uid) in enumerate(members, 1):
            out[uid] = f"{base}（{k}/{n}）"
    return out


def material_key(u) -> tuple:
    m = _PART.match(u.id)
    return ((m.group(1) if m else u.id), u.date or "", u.title or "")


def part_index(uid: str) -> int:
    m = _PART.match(uid)
    return int(m.group(2)) if m else 0


def materials(units) -> list[dict]:
    groups: dict[tuple, list] = defaultdict(list)
    for u in units:
        groups[material_key(u)].append(u)
    out = []
    for key, members in groups.items():
        members.sort(key=lambda u: part_index(u.id))
        out.append({"key": key, "date": key[1], "title": key[2] or key[0], "parts": members})
    out.sort(key=lambda m: (m["date"], m["key"][0]), reverse=True)
    return out


def parts_of(units, unit_id: str) -> list[str]:
    me = next((u for u in units if u.id == unit_id), None)
    if me is None:
        return [unit_id]
    k = material_key(me)
    return [u.id for u in sorted((u for u in units if material_key(u) == k), key=lambda u: part_index(u.id))]
