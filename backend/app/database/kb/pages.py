"""Read-only knowledge-page payloads. Month windows include empty calendar months and bound future dates."""

from __future__ import annotations

from ...util.i18n import msg


from collections import Counter, defaultdict
from datetime import date as _date

from .who import is_speaker_tag, norm_who
from . import entities as entities_mod
from .units import materials, part_labels, parts_of
from . import extract_check
from .scope import classify

MONTHS_ON_DASHBOARD = 12
MONTHS_ON_PAGE = 24
TOP_N = 8
FACT_PAGE = 50


def _speakers(facts, top_n: int) -> list[dict]:
    by_key: Counter = Counter()
    spelling: dict[str, Counter] = defaultdict(Counter)
    for f in facts:
        k = norm_who(f.who)
        by_key[k] += 1
        spelling[k][f.who or ""] += 1
    return [{"who": (spelling[k].most_common(1)[0][0] or "?"), "facts": n} for k, n in by_key.most_common(top_n)]


def _fact(f, vocab=None, groups=None) -> dict:
    d = {"id": f.id, "text": f.text, "when": f.when or "", "kind": f.kind or "",
         "who": f.who or "", "conf": f.conf or "", "topics": list(f.topics),
         "entities": list(f.entities), "unit": f.unit or ""}

    if vocab is not None:
        d["entity_names"] = [_entity_name(vocab, c, groups) for c in f.entities]

    nid = note_id_of_unit(f.unit)
    if nid:
        d["note_id"] = nid
        d["manual"] = f.unit.endswith("-manual")
    return d


def note_id_of_unit(unit: str) -> str:
    if not unit.startswith("note-"):
        return ""
    rest = unit[5:]
    return rest.rsplit("-", 1)[0] if "-" in rest else ""


FUTURE_MONTHS = 3


def _month_add(ym: str, delta: int) -> str:
    y, m = (int(x) for x in ym.split("-"))
    n = y * 12 + (m - 1) + delta
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


TRIM = 0.02


def _span(dates: list[str]) -> dict:
    if not dates:
        return {"start_date": "", "end_date": "", "full_start": "", "full_end": ""}
    dates = sorted(dates)
    k = int(len(dates) * TRIM)
    return {"start_date": dates[k], "end_date": dates[-1 - k] if k else dates[-1],
            "full_start": dates[0], "full_end": dates[-1]}


def _months(facts, last: int | None = None, today: str | None = None) -> list[dict]:
    c = Counter(f.when[:7] for f in facts if f.when)
    if not c:
        return []
    if not last:
        return [{"month": m, "facts": n} for m, n in sorted(c.items())]
    now = today or _date.today().strftime("%Y-%m")
    y, m = (int(x) for x in min(max(c), _month_add(now, FUTURE_MONTHS)).split("-"))
    months = []
    for _ in range(last):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    rows = [{"month": mo, "facts": c.get(mo, 0)} for mo in months]

    while rows and rows[0]["facts"] == 0:
        rows.pop(0)
    return rows


def _page(facts, limit: int, offset: int, vocab=None) -> tuple[list[dict], int]:
    rows = sorted(facts, key=lambda f: (f.when or "", f.id), reverse=True)
    return [_fact(f, vocab) for f in rows[offset:offset + limit]], len(rows)


def annotate(mem, rows: list[dict]) -> list[dict]:
    if rows:

        try:
            store, vocab = mem._index()
            g = entities_mod.for_store(store, vocab)
            for r in rows:
                if r.get("entities"):
                    r["entity_names"] = [g.name(c) for c in r["entities"]]
        except Exception:      # noqa: BLE001
            pass
    if not rows or not hasattr(mem, "fact_attrs"):
        return rows
    superseded = mem.fact_attrs("superseded_by")
    merged = mem.fact_attrs("merged")
    for row in rows:
        by = superseded.get(row["id"])
        if by:
            row["superseded_by"] = by
            if merged.get(row["id"]):
                row["merged"] = True
    return rows


def _entity_name(vocab, code: str, groups=None) -> str:
    if groups is not None:
        return groups.name(code)
    e = vocab.entities.get(code)
    return (e.name or e.code) if e else code


def dashboard(mem) -> dict:
    store, vocab = mem._index()
    facts = list(store.facts.values())
    units = list(store.units.values())
    dates = sorted(f.when for f in facts if f.when)


    by_topic: dict[str, set[str]] = defaultdict(set)
    for f in facts:
        for c in f.topics:
            by_topic[c].add(f.id)
    roots = [t for t in vocab.topics.values() if not any(p in vocab.topics for p in t.parents)]
    top_topics = []
    for t in roots:
        closure = vocab.downset(t.code, include_candidates=True) or {t.code}
        n = len(set().union(*(by_topic.get(c, set()) for c in closure)))
        if n:
            top_topics.append({"code": t.code, "facts": n,
                               "children": sum(1 for x in vocab.topics.values() if t.code in x.parents)})
    top_topics.sort(key=lambda r: -r["facts"])

    groups = entities_mod.for_store(store, vocab)
    ent = Counter(groups.canon(c) for f in facts for c in set(groups.canon(x) for x in f.entities))


    top_entities = [{"code": c, "name": groups.name(c), "facts": n}
                    for c, n in ent.most_common()
                    if not is_speaker_tag(c) and not is_speaker_tag(groups.name(c))
                    and not groups.is_dropped(c)][:TOP_N]

    unit_facts = Counter(f.unit for f in facts if f.unit)
    recent_units = []

    for m in materials(u for u in units if u.date and classify(u.id) != "screen")[:6]:
        n = len(m["parts"])
        recent_units.append({"id": m["parts"][0].id, "date": m["date"],
                             "title": msg("{title} ({n} parts)", title=m["title"], n=n) if n > 1 else m["title"],
                             "facts": sum(unit_facts.get(p.id, 0) for p in m["parts"])})

    return {
        "stats": {"facts": len(facts), "topics": len(vocab.topics), "entities": sum(1 for c, e in vocab.entities.items() if not is_speaker_tag(c) and not is_speaker_tag(getattr(e, "name", ""))),
                  "units": len(units), "lines": len(store.lines),
                  **_span(dates)},


        "quality": extract_check.shapes(facts),
        "months": _months(facts, MONTHS_ON_DASHBOARD),
        "top_topics": top_topics[:TOP_N],
        "top_entities": top_entities,
        "recent_units": recent_units,
        "kinds": [{"kind": k or "?", "facts": n} for k, n in Counter(f.kind for f in facts).most_common()],
        "speakers": _speakers(facts, 6),
    }


def topic_page(mem, code: str, limit: int = FACT_PAGE, offset: int = 0) -> dict | None:
    store, vocab = mem._index()
    t = vocab.topics.get(code)
    if t is None:
        return None
    closure = vocab.downset(code, include_candidates=True) or {code}
    facts = [f for f in store.facts.values() if set(f.topics) & closure]
    direct = Counter(c for f in facts for c in f.topics)
    children = []
    for x in vocab.topics.values():
        if code in x.parents:
            sub = vocab.downset(x.code, include_candidates=True) or {x.code}
            children.append({"code": x.code, "facts": sum(direct.get(c, 0) for c in sub)})
    children.sort(key=lambda r: -r["facts"])
    _g = entities_mod.for_store(store, vocab)
    ents = Counter(c for f in facts for c in {_g.canon(x) for x in f.entities})
    page, total = _page(facts, limit, offset, vocab)
    annotate(mem, page)
    return {
        "code": code, "aliases": sorted(t.aliases), "parents": [p for p in sorted(t.parents) if p in vocab.topics],
        "status": t.status, "facts_total": total, "facts": page, "limit": limit, "offset": offset,
        "months": _months(facts, MONTHS_ON_PAGE), "children": children,
        "entities": [{"code": c, "name": _entity_name(vocab, c), "facts": n} for c, n in ents.most_common(TOP_N)],
        "kinds": [{"kind": k or "?", "facts": n} for k, n in Counter(f.kind for f in facts).most_common()],
    }


def resolve_entity_code(vocab, code: str) -> str | None:
    if code in vocab.entities:
        return code
    norm = code.strip().lower().replace(" ", "_")
    if norm in vocab.entities:
        return norm
    for c, e in vocab.entities.items():
        if (e.name or "").strip().lower() == code.strip().lower():
            return c
        if any(a.strip().lower() == code.strip().lower() for a in (e.aliases or ())):
            return c
    return None


def evolution_chains(facts, vocab=None, *, min_len: int = 2, top: int = 5) -> list[dict]:
    by_obj: dict[str, list] = defaultdict(list)
    for f in facts:
        if not f.when:
            continue
        for o in f.obj:
            by_obj[o].append(f)
    chains = []
    for o, fs in by_obj.items():
        if len(fs) < min_len:
            continue
        fs = sorted(fs, key=lambda f: (f.when, f.id))
        chains.append({"obj": o, "facts": [_fact(f, vocab) for f in fs[-8:]], "total": len(fs)})
    chains.sort(key=lambda c: -c["total"])
    return chains[:top]


def entity_page(mem, code: str, limit: int = FACT_PAGE, offset: int = 0) -> dict | None:
    store, vocab = mem._index()
    code = resolve_entity_code(vocab, code) or code
    e = vocab.entities.get(code)
    if e is None:
        return None
    groups = entities_mod.for_store(store, vocab)
    code = groups.canon(code)
    e = vocab.entities.get(code) or e
    members = set(groups.members(code))
    facts = [f for f in store.facts.values() if members & set(f.entities)]
    topics = Counter(c for f in facts for c in f.topics)
    page, total = _page(facts, limit, offset, vocab)
    annotate(mem, page)
    return {
        "code": code, "name": groups.name(code), "type": e.etype or "", "aliases": sorted(e.aliases),
        "variants": groups.variants(code),
        "relations": [{"rel": r, "target": tgt, "target_name": _entity_name(vocab, tgt)} for r, tgt in sorted(e.rels)],
        "facts_total": total, "facts": page, "limit": limit, "offset": offset,
        "chains": evolution_chains(facts, vocab),
        "months": _months(facts, MONTHS_ON_PAGE),
        "topics": [{"code": c, "facts": n} for c, n in topics.most_common(TOP_N)],
    }


def timeline(mem) -> list[dict]:
    store, _vocab = mem._index()
    by_day: dict[str, dict] = defaultdict(lambda: {"facts": 0, "units": 0})
    for f in store.facts.values():
        if f.when:
            by_day[f.when]["facts"] += 1
    for u in store.units.values():
        if u.date:
            by_day[u.date]["units"] += 1
    months: dict[str, dict] = {}
    for day in sorted(by_day):
        m = months.setdefault(day[:7], {"month": day[:7], "facts": 0, "units": 0, "days": []})
        d = by_day[day]
        m["facts"] += d["facts"]; m["units"] += d["units"]
        m["days"].append({"date": day, "facts": d["facts"], "units": d["units"]})
    return list(months.values())


def unit_page(mem, unit_id: str, limit: int = FACT_PAGE, offset: int = 0) -> dict | None:
    store, vocab = mem._index()
    u = store.units.get(unit_id)
    if u is None:
        return None
    facts = [f for f in store.facts.values() if f.unit == unit_id]
    page, total = _page(facts, limit, offset, vocab)
    annotate(mem, page)
    label = part_labels(list(store.units.values())).get(unit_id) or u.title or ""
    topics = Counter(c for f in facts for c in f.topics)
    _g = entities_mod.for_store(store, vocab)
    ents = Counter(c for f in facts for c in {_g.canon(x) for x in f.entities})
    parts = parts_of(store.units.values(), unit_id)


    raw_lines = []
    if total == 0:
        raw_lines = [{"who": getattr(ln, "who", "") or "", "text": getattr(ln, "text", "") or ""}
                     for ln in store.lines.values() if getattr(ln, "unit", "") == unit_id][:50]
    return {
        "id": u.id, "date": u.date or "", "title": label,
        "lines": raw_lines,

        "parts": [{"id": pid, "k": k} for k, pid in enumerate(parts, 1)],
        "part_index": parts.index(unit_id) + 1, "part_total": len(parts),
        "speakers": sorted(s["who"] for s in _speakers([f for f in facts if f.who], 50)),
        "facts_total": total, "facts": page, "limit": limit, "offset": offset,
        "topics": [{"code": c, "facts": n} for c, n in topics.most_common(TOP_N)],
        "entities": [{"code": c, "name": _entity_name(vocab, c), "facts": n} for c, n in ents.most_common(TOP_N)],
    }


def day_facts(mem, date: str, limit: int = FACT_PAGE) -> list[dict]:
    store, vocab = mem._index()
    page, _ = _page([f for f in store.facts.values() if f.when == date], limit, 0, vocab)
    return annotate(mem, page)
