"""Knowledge queries, fact editing, source inspection and entity/topic browsing endpoints."""

import re
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..database import store
from ..database.kb import pages
from ..database.kb import relations as kb_relations
from ..database.kb import search
from memoket_kite.errors import ProviderError

from ..database.kite.kite_memory import ProviderFailed, UserMemory
from ..harness import prompts
from ..util import llm
from .schemas import AskIn, AskOut, CitingNoteOut, FactPeekOut, TraceIn, EntityOut, FactDetailOut, FactOut, FactsPageOut, RecallIn, RecallOut, SourceLineOut, StatsOut, TimelineBucket, TimelineOut, TopicCreateIn, TopicEntityLink, TopicOut
from .deps import current_user


RELATION_SAY_MAX = 120

router = APIRouter(prefix="/api/memory", tags=["memory"])


def rows_to_facts(mem: UserMemory, rows: list[dict]) -> list[FactOut]:
    out = []
    for r in rows:
        out.append(FactOut(
            id=r.get("id", ""),
            text=r.get("text", ""),
            when=r.get("date", ""),
            kind=r.get("kind", ""),
            sources=mem.source_lines(r),
        ))
    return out


@router.post("/recall", response_model=RecallOut)
def recall(body: RecallIn, user: str = Depends(current_user)):
    mem = UserMemory(user)


    rows, terms, took = mem.recall(body.query, limit=body.limit, scope=body.scope,
                                   evidence=not body.relaxed)


    can_expand = False
    if not rows and not body.relaxed:
        try:
            loose, _lt, _lm = mem.recall(body.query, limit=body.limit, scope=body.scope,
                                         evidence=False)
            can_expand = bool(loose)
        except Exception:  # noqa: BLE001
            can_expand = False


    why = ""
    if not rows:
        try:
            why = "no_terms" if not search._terms(mem, search.clean_query(body.query)) else "weak"
        except Exception:      # noqa: BLE001
            why = ""


    try:
        ev: list[dict] | None = mem.recall_evidence(body.query, rows) if rows else []
    except Exception:          # noqa: BLE001
        ev = None
    return RecallOut(facts=rows_to_facts(mem, rows), took_ms=round(took, 3),
                     relaxed=body.relaxed, can_expand=can_expand,


                     terms=search.display_terms(terms, body.query, segment=mem.segment()),
                     kb_empty=mem.is_empty(),
                     evidence=ev, why_empty=why)


@router.get("/stats", response_model=StatsOut)
def stats(user: str = Depends(current_user)):
    return UserMemory(user).stats()


@router.get("/topics", response_model=list[TopicOut])
def topics(user: str = Depends(current_user)):
    return UserMemory(user).topics()


@router.post("/topics", response_model=TopicOut)
def create_topic(body: TopicCreateIn, user: str = Depends(current_user)):
    try:
        return UserMemory(user).add_topic(body.code, parent=body.parent, aliases=body.aliases)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/entities", response_model=list[EntityOut])
def entities(user: str = Depends(current_user)):
    return UserMemory(user).entities()


@router.get("/topic-entity-links", response_model=list[TopicEntityLink])
def topic_entity_links(user: str = Depends(current_user)):
    return UserMemory(user).topic_entity_links()


@router.get("/facts", response_model=FactsPageOut)
def facts(kind: str = "", who: str = "", topic: str = "", entity: str = "",
          conf_min: str = "", limit: int = 20, offset: int = 0,
          user: str = Depends(current_user)):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    mem = UserMemory(user)
    rows, total = mem.facts_page(
        kind=kind, who=who, topic=topic, entity=entity, conf_min=conf_min,
        limit=limit, offset=offset)
    pages.annotate(mem, rows)
    return FactsPageOut(facts=[FactDetailOut(**r) for r in rows], total=total,
                        limit=limit, offset=offset)


PEEK_SOURCE_CHARS = 220


def _clip(s: str) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= PEEK_SOURCE_CHARS else s[:PEEK_SOURCE_CHARS] + "…"


@router.get("/facts/{fact_id}", response_model=FactPeekOut)
def fact_peek(fact_id: str, user: str = Depends(current_user)):
    mem = UserMemory(user)
    fact = mem.fact_by_id(fact_id)
    if not fact:
        raise HTTPException(404, f'Record not found: {fact_id}')
    store_, vocab = mem._index()
    from ..database.kb import entities as entities_mod
    groups = entities_mod.for_store(store_, vocab)
    return FactPeekOut(
        id=fact_id, text=fact.get("text", ""), when=fact.get("when", ""),
        kind=fact.get("kind", ""),
        topics=list(fact.get("topics") or []), entities=list(fact.get("entities") or []),
        entity_names=[groups.name(c) for c in fact.get("entities") or []],


        sources=[_clip(s["text"] if isinstance(s, dict) else str(s))
                 for s in mem.fact_sources(fact_id)][:3],
    )


@router.get("/facts/{fact_id}/citing", response_model=list[CitingNoteOut])
def citing_notes(fact_id: str, user: str = Depends(current_user)):
    return store.notes_citing(user, fact_id)


@router.get("/facts/{fact_id}/sources", response_model=list[SourceLineOut])
def fact_sources(fact_id: str, user: str = Depends(current_user)):
    return UserMemory(user).fact_sources(fact_id)


@router.get("/timeline", response_model=TimelineOut)
def timeline(user: str = Depends(current_user)):
    return TimelineOut(buckets=[TimelineBucket(**b) for b in UserMemory(user).timeline()])


class _RelationsIn(TraceIn):
    confirm: bool = True
    scope: str = "all"


def _has_facts(mem: UserMemory) -> bool:
    try:
        return mem.stats()["facts"] > 0
    except Exception:      # noqa: BLE001
        return False


def _live(mem: UserMemory, rows: list[dict]) -> list[dict]:
    gone = mem.fact_attrs("superseded_by")
    return [r for r in rows if r["id"] not in gone]


@router.post("/relations")
async def relations(body: _RelationsIn, user: str = Depends(current_user)) -> dict:
    passage = body.passage.strip()
    if not passage:
        return {"relations": [], "took_ms": 0.0}
    t0 = time.perf_counter()
    mem = UserMemory(user)
    if not _has_facts(mem):
        return {"relations": [], "took_ms": round((time.perf_counter() - t0) * 1000, 1)}
    rows, _terms, _took = mem.recall(passage, limit=8, scope=body.scope)
    rows = _live(mem, rows)
    cands = kb_relations.detect(passage, rows, common=mem.common_term())
    by_id = {r["id"]: r for r in rows}
    if body.confirm and any(c["relation"] == "conflict" for c in cands):
        try:
            verdict = await llm.complete_json(
                [{"role": "system", "content": prompts.RELATIONS_SYSTEM},
                 {"role": "user", "content": prompts.relations_user(passage, cands, by_id)}],
                max_tokens=600, temperature=0.1)
            if isinstance(verdict, list):
                keep = {}
                for v in verdict:
                    if isinstance(v, dict) and isinstance(v.get("index"), int):
                        keep[v["index"]] = v

                cands = [dict(c, say=" ".join(str(keep[i].get("say") or c["say"]).split())[:RELATION_SAY_MAX])
                         for i, c in enumerate(cands)
                         if i not in keep or keep[i].get("keep", True)]
        except Exception:      # noqa: BLE001
            pass
    facts = rows_to_facts(mem, rows)
    fmap = {f.id: f for f in facts}
    return {
        "relations": [dict(c, facts=[fmap[i].model_dump() for i in c.get("fact_ids", []) if i in fmap]) for c in cands],
        "took_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


class _RelationsBatchIn(BaseModel):
    passages: list[str]
    scope: str = "all"


@router.post("/relations/batch")
def relations_batch(body: _RelationsBatchIn, user: str = Depends(current_user)) -> dict:
    mem = UserMemory(user)
    t0 = time.perf_counter()
    if not _has_facts(mem):
        return {"marks": [None] * len(body.passages[:80]), "took_ms": 0.0}

    common = mem.common_term()
    out = []
    for p in body.passages[:80]:
        p = (p or "").strip()
        if len(p) < 8 or not any(ch.isdigit() for ch in p):
            out.append(None)
            continue
        rows, _terms, _took = mem.recall(p, limit=8, scope=body.scope)
        cands = kb_relations.detect(p, _live(mem, rows), common=common)


        top = cands[0] if cands else None
        if not top:
            out.append(None)
            continue


        by_id = {r["id"]: r for r in rows}
        facts = [f.model_dump() for f in rows_to_facts(mem, [by_id[i] for i in top["fact_ids"] if i in by_id])]


        out.append({"relation": top["relation"], "say": top["say"], "fact_ids": top["fact_ids"],
                    "kinds": len({c["relation"] for c in cands}), "facts": facts,
                    **({"why": top["why"]} if top.get("why") else {})})
    return {"marks": out, "took_ms": round((time.perf_counter() - t0) * 1000, 1)}


_NO_INFO = re.compile(r"^\s*(no|not enough|insufficient)\s+information\b.*$", re.I | re.S)


TRACE_RECALL_LIMIT = 6


def _no_info_message(text: str, has_facts: bool = True, recalled: int | None = None) -> str:
    if _NO_INFO.match(text or ""):
        if has_facts:
            return 'The records do not establish a timeline for this event. The closest records below may be only loosely related.'
        if recalled:
            return (f'No timeline could be established from this passage. The knowledge base contains {recalled} related records, but this step could not establish their sequence.')
        return 'No knowledge-base records match this passage.'
    return text


@router.post("/trace", response_model=AskOut)
def trace(body: TraceIn, user: str = Depends(current_user)):
    passage = body.passage.strip()
    if not passage:
        raise HTTPException(400, 'No text selected')

    head = passage[:400]
    t0 = time.perf_counter()
    mem = UserMemory(user)
    if not _has_facts(mem):

        return AskOut(answer='The knowledge base is empty. Import records or save a note to the knowledge base first.',
                      facts=[], recalled=0,
                      took_ms=round((time.perf_counter() - t0) * 1000, 1))


    prefetched: list[dict] = []
    recalled_base = 0
    try:
        prefetched, _terms, _ms = mem.recall(
            passage, limit=min(body.limit, TRACE_RECALL_LIMIT), evidence=True)
        recalled_base = len(prefetched)


        if prefetched and hasattr(mem, "recall_evidence"):
            evidence_terms = mem.recall_evidence(passage, prefetched) or []
            probes = sorted(
                (e for e in evidence_terms if len(str(e.get("term", ""))) >= 2),
                key=lambda e: (int(e.get("units") or 10**9), str(e.get("term", ""))),
            )[:2]
            seen = {f.get("id") for f in prefetched}
            for ev in probes:
                extra, _extra_terms, _extra_ms = mem.recall(
                    str(ev["term"]), limit=3, evidence=True)
                for f in extra:
                    if f.get("id") not in seen:
                        prefetched.append(f)
                        seen.add(f.get("id"))
    except Exception:  # noqa: BLE001
        prefetched = []
        recalled_base = 0
    candidates = "\n".join(
        f"- [{f.get('date') or 'Date unknown'}] [{f.get('id', '')}] {f.get('text', '')}"
        for f in prefetched if f.get("id") and f.get("text")
    )
    question = (f'Explain how the event in the selected passage developed, in chronological order. Put each event on its own line with its date and supporting fact ID at the end. Cite fact IDs containing F, not raw line IDs containing L. Exclude unrelated candidates and retain dates, decisions and changes explicitly recorded in relevant candidates. Respond in the language of the selected passage:\n\n{head}'
                + (f'\n\nHigh-confidence lexical candidates (use only when relevant):\n{candidates}' if candidates else ""))
    try:
        text, facts = mem.ask(question, limit=body.limit)
    except ProviderError as exc:


        if "no JSON" not in str(exc):
            raise


        raise HTTPException(
            502, 'The provider responded, but the model output did not match the required format. Try again or choose another model.') from exc
    except ProviderFailed as exc:

        raise HTTPException(502, f"Timeline lookup failed: {exc} ({store.get_active_llm_config()['base_url']}). Check the model provider in Settings.") from exc


    source_to_fact = {
        source_id: f.get("id", "")
        for f in facts for source_id in (f.get("_source_ids") or [])
        if source_id and f.get("id")
    }
    for source_id, fact_id in source_to_fact.items():
        text = text.replace(f"[{source_id}]", f"[{fact_id}]")
        text = text.replace(f"({source_id})", f"({fact_id})")
    for f in facts:
        f.pop("_source_ids", None)

    combined = {f.get("id", ""): f for f in facts if f.get("id")}
    for f in prefetched:
        fact_id = f.get("id", "")
        if fact_id and fact_id not in combined:
            combined[fact_id] = {
                "id": fact_id, "text": f.get("text", ""),
                "date": f.get("date") or f.get("when", ""), "kind": f.get("kind", ""),
                "sources": (mem.source_lines(f) if hasattr(mem, "source_lines") else []),
            }
    cited_ids = [fact_id for fact_id in combined if fact_id in text]
    if cited_ids:
        facts = [combined[fact_id] for fact_id in sorted(cited_ids, key=text.index)]

    recalled = None if facts else (recalled_base if prefetched else len(mem.recall(passage, limit=TRACE_RECALL_LIMIT)[0]))
    text = _no_info_message(text, bool(facts), recalled)
    return AskOut(
        answer=text,
        facts=[FactOut(id=f["id"], text=f["text"], when=f["date"],
                       kind=f["kind"], sources=f["sources"]) for f in facts],
        recalled=recalled,
        took_ms=round((time.perf_counter() - t0) * 1000, 1),
    )


@router.post("/ask", response_model=AskOut, include_in_schema=False)
def ask(body: AskIn, user: str = Depends(current_user)):
    t0 = time.perf_counter()
    text, facts = UserMemory(user).ask(body.question, limit=body.limit)
    return AskOut(
        answer=text,
        facts=[FactOut(id=f["id"], text=f["text"], when=f["date"],
                       kind=f["kind"], sources=f["sources"]) for f in facts],
        took_ms=round((time.perf_counter() - t0) * 1000, 1),
    )
