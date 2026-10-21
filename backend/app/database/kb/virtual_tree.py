"""Read-only knowledge-tree rows. Categories load eagerly; facts expand on demand. Branch IDs preserve multiple topic parents."""

from __future__ import annotations

import re

from collections import Counter, defaultdict
from ...util.i18n import msg
from . import entities as entities_mod
from .who import is_speaker_tag
from .units import materials, parts_of
from .scope import classify

KB_ROOT = "kb"
ROOT_POSITION = 1_000_000

CATEGORIES = [
    ("kb:topics", 'Topics'),
    ("kb:entities", 'Entities'),
    ("kb:timeline", 'Timeline'),
    ("kb:recent", 'Recently ingested'),
]


TOOLS = [
    ("kb:facts", 'Fact table'),
    ("kb:graph", 'Topic map'),
    ("kb:digest", 'Periodic review'),
]

ETYPE_LABELS = {
    "person": 'People', "org": 'Organizations', "product": 'Products', "place": 'Places',
    "event": 'Events', "project": 'Projects', "": 'Other',
}

RECENT_UNITS = 15
FACT_TITLE_CHARS = 60
MAX_CHILDREN = 300


def _row(note_id: str, parent: str, title: str, *, position: int = 0,
         preview: str = "", child_count: int = 0, branch_count: int = 1,
         updated_at: str = "", branch_id: str = "", fact_count: int = 0) -> dict:
    return {
        "id": branch_id or f"kbb:{note_id[3:]}:{parent}",
        "note_id": note_id, "parent_note_id": parent, "position": position,
        "is_expanded": False, "title": title, "preview": preview,
        "cite_count": 0, "ingested_at": "", "pinned": False,
        "updated_at": updated_at, "child_count": child_count,
        "branch_count": branch_count, "fact_count": fact_count,
    }


def _clip(s: str, n: int = FACT_TITLE_CHARS) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _fact_row(f, parent: str, position: int) -> dict:
    return _row(f"kb:fact:{f.id}", parent, _clip(f.text), position=position,
                preview=f.text, updated_at=f.when or "",
                branch_id=f"kbb:fact:{f.id}:{parent}")


ENTITY_EAGER_MAX = 200


def build(mem) -> list[dict]:
    store, vocab = mem._index()
    facts = list(store.facts.values())

    topic_direct = Counter(c for f in facts for c in f.topics)

    by_topic: dict[str, set[str]] = defaultdict(set)
    for f in facts:
        for c in f.topics:
            by_topic[c].add(f.id)
    entity_count = Counter(c for f in facts for c in f.entities)
    month_count = Counter(f.when[:7] for f in facts if f.when)
    unit_count = Counter(f.unit for f in facts if f.unit)

    rows: list[dict] = []


    topic_rows: list[dict] = []


    n_in_closure: dict[str, int] = {}
    for t in vocab.topics.values():
        closure = vocab.downset(t.code, include_candidates=True) or {t.code}
        n_in_closure[t.code] = len(set().union(*(by_topic.get(c, set()) for c in closure)))
    live = {code for code, n in n_in_closure.items() if n > 0}
    children_of: Counter = Counter()
    for t in vocab.topics.values():
        if t.code not in live:
            continue
        parents = [p for p in sorted(t.parents) if p in live] or [""]
        for p in parents:
            children_of[p] += 1
    for t in sorted(vocab.topics.values(), key=lambda t: t.code):
        if t.code not in live:
            continue
        parents = [p for p in sorted(t.parents) if p in live] or [""]
        n_facts = n_in_closure[t.code]
        for p in parents:
            parent_id = f"kb:topic:{p}" if p else "kb:topics"
            topic_rows.append(_row(
                f"kb:topic:{t.code}", parent_id, t.code,
                preview=" / ".join(sorted(t.aliases)),
                child_count=children_of.get(t.code, 0) + topic_direct.get(t.code, 0),
                branch_count=len(parents), fact_count=n_facts,
                branch_id=f"kbb:topic:{t.code}:{parent_id}"))


    etype_rows, entity_rows, grouped = _entity_rows(vocab, entity_count, facts)


    lazy_entities = len(entity_rows) > ENTITY_EAGER_MAX
    n_entities = len(entity_rows)
    if lazy_entities:
        entity_rows = []


    month_rows = [
        _row(f"kb:month:{m}", "kb:timeline", m, position=i, child_count=n,
             fact_count=n)
        for i, (m, n) in enumerate(sorted(month_count.items(), reverse=True))
    ]


    mats = materials(u for u in store.units.values()
                     if u.date and classify(u.id) != "screen")[:RECENT_UNITS]
    unit_rows = []
    for i, m in enumerate(mats):
        first, n = m["parts"][0], len(m["parts"])
        total = sum(unit_count.get(p.id, 0) for p in m["parts"])
        label = msg("{title} ({n} parts)", title=m["title"], n=n) if n > 1 else m["title"]


        nid = f"kb:material:{first.id}" if n > 1 else f"kb:unit:{first.id}"
        unit_rows.append(_row(nid, "kb:recent", _unit_tree_title(m["date"], label),
                              position=i, child_count=n if n > 1 else total,
                              fact_count=total, updated_at=m["date"]))

    rows.append(_row(KB_ROOT, "root", msg('Knowledge base'), position=ROOT_POSITION,
                     child_count=len(CATEGORIES) + len(TOOLS), fact_count=len(facts),
                     branch_id="kbb:root"))
    counts = {
        "kb:topics": children_of.get("", 0),
        "kb:entities": len(etype_rows) if grouped else n_entities,
        "kb:timeline": len(month_rows),
        "kb:recent": len(unit_rows),
    }
    for i, (cid, label) in enumerate(CATEGORIES):
        rows.append(_row(cid, KB_ROOT, msg(label), position=i, child_count=counts[cid]))
    for i, (cid, label) in enumerate(TOOLS):
        rows.append(_row(cid, KB_ROOT, msg(label), position=len(CATEGORIES) + i))
    rows += topic_rows + etype_rows + entity_rows + month_rows + unit_rows
    return rows


_PART_SUFFIX = re.compile(r"（\d+/\d+）$")


def _unit_tree_title(date: str, label: str) -> str:
    short = date[5:] if len(date) == 10 else date
    m = _PART_SUFFIX.search(label)
    if m:
        return f"{short} {m.group(0)[1:-1]} · {label[:m.start()]}"
    return f"{short} · {label}"


def _entity_rows(vocab, entity_count, facts=None) -> tuple[list[dict], list[dict], bool]:
    groups = entities_mod.build(vocab, entity_count)

    if facts is not None:
        merged_count: Counter = Counter(c for f in facts for c in {groups.canon(x) for x in f.entities})
    else:
        merged_count = Counter()
        for code, n in entity_count.items():
            merged_count[groups.canon(code)] += n
    by_type: dict[str, list] = {}
    for e in vocab.entities.values():
        if groups.canon(e.code) != e.code:
            continue
        if groups.is_dropped(e.code):
            continue
        if is_speaker_tag(e.code) or is_speaker_tag(getattr(e, "name", "") or ""):
            continue
        by_type.setdefault(e.etype or "", []).append(e)
    etype_rows: list[dict] = []
    entity_rows: list[dict] = []
    grouped = len(by_type) > 1
    for i, (etype, ents) in enumerate(sorted(by_type.items(), key=lambda kv: -len(kv[1]))):
        eid = f"kb:etype:{etype or 'other'}" if grouped else "kb:entities"
        if grouped:
            etype_rows.append(_row(eid, "kb:entities", msg(ETYPE_LABELS[etype]) if etype in ETYPE_LABELS else etype,
                                   position=i, child_count=len(ents)))
        for j, e in enumerate(sorted(ents, key=lambda e: (-merged_count.get(e.code, 0), e.code))):
            entity_rows.append(_row(
                f"kb:entity:{e.code}", eid, groups.name(e.code), position=j,
                preview=" / ".join(sorted(set(e.aliases) | set(groups.variants(e.code)))),
                child_count=merged_count.get(e.code, 0),
                fact_count=merged_count.get(e.code, 0)))
    return etype_rows, entity_rows, grouped


def children(mem, node: str) -> list[dict]:
    store, vocab = mem._index()
    kind, _, key = node.partition(":")[2].partition(":")
    facts = store.facts.values()

    if kind == "entities" or kind == "etype":
        entity_count = Counter(c for f in facts for c in f.entities)
        _etypes, entity_rows, grouped = _entity_rows(vocab, entity_count, facts)
        if kind == "entities":

            return entity_rows
        return [r for r in entity_rows if r["parent_note_id"] == node]
    if kind == "topic":
        closure = vocab.downset(key, include_candidates=True) or {key}
        picked = [f for f in facts if set(f.topics) & closure]
    elif kind == "entity":
        members = set(entities_mod.for_store(store, vocab).members(key))
        picked = [f for f in facts if members & set(f.entities)]
    elif kind == "month":
        picked = [f for f in facts if (f.when or "").startswith(key)]
    elif kind == "material":

        parts = parts_of(store.units.values(), key)
        cnt = Counter(f.unit for f in facts if f.unit)
        return [_row(f"kb:unit:{pid}", node, msg("Part {part}/{total}", part=k, total=len(parts)), position=k - 1,
                     child_count=cnt.get(pid, 0), fact_count=cnt.get(pid, 0))
                for k, pid in enumerate(parts, 1)]
    elif kind == "unit":
        picked = [f for f in facts if f.unit == key]
    else:
        return []
    picked.sort(key=lambda f: (f.when or "", f.id), reverse=True)
    rows = [_fact_row(f, node, i) for i, f in enumerate(picked[:MAX_CHILDREN])]


    if len(picked) > MAX_CHILDREN and kind in ("topic", "entity"):
        rows.append(_row(f"kb:facts?{kind}={key}", node,
                         msg("{n} more · Open the fact table", n=len(picked) - MAX_CHILDREN), position=MAX_CHILDREN))
    return rows


def is_virtual(note_id: str) -> bool:
    return note_id == KB_ROOT or note_id.startswith("kb:")
