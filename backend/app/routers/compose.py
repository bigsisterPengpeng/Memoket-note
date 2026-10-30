"""Single-action writing routes for planning, continuation, revision, verification and digests."""

from __future__ import annotations

import time
import uuid
from datetime import date as _date
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException

from ..harness import prompts
from ..harness.events import sse
from ..harness.params import CONTINUE_TAIL_TOKENS
from ..harness.middleware.compact import compact_context


TAP_KEEP_LAST = 6000
TAP_SUMMARY_MAX = 2000
from ..database import retrieval
from ..editor import profile
from ..editor.preconditions import note_precondition
from ..editor import intent as doc_intent
from ..harness import tray as tray_mod
from ..util import llm
from ..harness.checks import grounding_rules as grounding_check
from ..harness.checks import citations as citation_check
from ..harness.checks.skeleton import beats_budget, check_skeleton, skeleton_length_rule, verify_beats
from ..harness.checks.tap import check_tap
from ..harness.checks.slides import check_slides
from ..database import store
from ..database.kite.kite_memory import UserMemory
from .schemas import DigestIn, DigestOut, SlidesIn, EditOut, ExpandIn, MagicTapIn, Revision, RewriteIn, SkeletonIn, SkeletonOut, VerifyFinding, VerifyIn, VerifyOut
from .deps import current_user, sse_response

router = APIRouter(prefix="/api", tags=["compose"])


TAIL_CHARS = 600


PROFILE_LIMIT = 20


def _profile(user: str) -> list[str]:
    """Kept as a thin alias while the routers migrate; the implementation
    moved to ``app/profile.py`` so routers stop importing each other."""
    return profile.entries(user)


TAIL_CHARS_FOR_HARNESS = 300


def _fact_exists(user: str):
    mem = UserMemory(user)

    def exists(fid: str) -> bool:
        try:
            return mem.fact_by_id(fid) is not None
        except Exception:      # noqa: BLE001
            return False
    return exists


def why_no_facts(user: str, content: str, scope: str) -> str:
    from ..database.kb.scope import SCOPE_LABEL
    try:
        mem = UserMemory(user)
        if mem.is_empty():
            return 'The knowledge base is empty. Import meeting records or notes to provide evidence for continuation.'
        if scope not in ("", "all"):
            texts, _ids, _took = _retrieve(user, content, "", [], limit=6, scope="all")
            label = SCOPE_LABEL.get(scope, scope)
            if texts:
                return (f'The memory scope is "{label}" and contains no usable records; All has {len(texts)} records. Change the scope at the top of the Memory pane.')
            return f'The memory scope is "{label}". Neither this scope nor All contains matching records.'
        return 'No knowledge-base records match the text before the cursor. Add a specific name, date or number before continuing.'
    except Exception:      # noqa: BLE001
        return ""


def _retrieve(user: str, content: str, spine: str, beats: list[str], limit: int = 8,
              title: str = "", anchor_first: bool = False, scope: str = "all"):
    """Thin alias while the routers migrate; implementation moved to
    ``app/retrieval.py`` so routers stop importing each other."""
    return retrieval.retrieve(user, content, spine, beats, limit=limit,
                              title=title, anchor_first=anchor_first, scope=scope)


@router.post("/skeleton", response_model=SkeletonOut)
async def skeleton(body: SkeletonIn, user: str = Depends(current_user)):
    if why := note_precondition("skeleton", body.content, body.title):
        raise HTTPException(400, why)
    t0 = time.perf_counter()


    budget = beats_budget(len(body.content))

    system = doc_intent.block(body.intent) + prompts.compose_system(prompts.SKELETON_SYSTEM, "skeleton", user) + skeleton_length_rule(len(body.content))
    parsed, text = await llm.complete_json_raw(
        [{"role": "system", "content": system},
         {"role": "user", "content": prompts.skeleton_user(
             body.title, body.content, _profile(user))}],
        max_tokens=1600, temperature=0.4)
    spine = ""
    beats: list[str] = []
    if isinstance(parsed, dict):
        spine = str(parsed.get("spine") or "").strip()
        raw_beats = parsed.get("beats")
        if isinstance(raw_beats, list):
            beats = [str(x).strip() for x in raw_beats if str(x).strip()]
    if not spine and not beats and text:

        lines = [ln.lstrip("-*0123456789. ").strip()
                 for ln in text.splitlines() if ln.strip()]
        if lines:
            spine = lines[0]
            beats = lines[1:budget + 1]
    beats = beats[:budget]

    spine, beats = store.clamp_skeleton(spine, beats)

    beats = verify_beats(beats, body.content)


    spine, beats = store.clamp_skeleton(spine, beats)


    return SkeletonOut(spine=spine, beats=beats,
                       notes=check_skeleton(spine, beats).notes(),
                       took_ms=round((time.perf_counter() - t0) * 1000, 1))


@router.post("/magic-tap")
async def magic_tap(body: MagicTapIn, user: str = Depends(current_user)):
    if why := note_precondition("tap", body.content, body.title):
        raise HTTPException(400, why)
    facts, ids, took = _retrieve(user, body.content, body.spine, body.beats, limit=6, scope=body.scope)

    tray_items = store.list_tray(user, body.note_id) if body.note_id else []
    tray = tray_mod.lines_of(tray_items)
    tray_ids = [it["ref_id"] for it in tray_items if it.get("kind") == "fact" and it.get("ref_id")]
    facts = tray + [f for f in facts if f not in tray]
    ids = tray_ids + [i for i in ids if i not in tray_ids]

    system = doc_intent.block(body.intent) + prompts.compose_system(
        prompts.MAGIC_TAP_SYSTEM_LEAN_NOCHART, "magic_tap", user)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompts.magic_tap_user(


            body.spine, body.beats, compact_context(body.content, keep_last_chars=TAP_KEEP_LAST, max_summary_chars=TAP_SUMMARY_MAX),
            facts, _profile(user), following=body.following, title=body.title, tray=tray)},
    ]

    async def gen():
        meta = {"facts": len(facts), "recall_ms": round(took, 3),
                "grounded": bool(facts), "sources": facts[:6], "fact_ids": ids[:6],
                "scope": body.scope,


                "why_empty": "" if facts else why_no_facts(user, body.content, body.scope)}
        yield sse("meta", meta)
        written = ""
        stats: dict = {}
        try:
            async for piece in llm.stream(messages, max_tokens=body.max_tokens,
                                          temperature=0.7, stats=stats):
                written += piece
                yield sse("delta", {"text": piece})
        except Exception as exc:
            yield sse("error", {"detail": str(exc)})


        if stats.get("finish_reason") == "length" and written:
            tail_stats: dict = {}
            tail = messages + [{"role": "assistant", "content": written},
                               {"role": "user", "content": prompts.FINISH_THE_SENTENCE}]
            try:
                async for piece in llm.stream(tail, max_tokens=CONTINUE_TAIL_TOKENS,
                                              temperature=0.7, stats=tail_stats):
                    written += piece
                    yield sse("delta", {"text": piece})
            except Exception as exc:
                yield sse("error", {"detail": str(exc)})
            stats = tail_stats


        used, _u = grounding_check.fact_usage(written, facts)


        yield sse("grounding", {
            "facts": len(facts), "used": used,
            "notes": check_tap(written, body.content).notes(),
            "hint": ("" if used or not facts else
                     'This passage uses generic content instead of retrieved records. Retry, or add a specific detail before continuing.')})


        fake = citation_check.fake_citations(written, facts, _fact_exists(user)) if written else []


        yield sse("done", {"truncated": stats.get("finish_reason") == "length", "fake_citations": fake})

    return sse_response(gen())


@router.post("/slides")
async def slides(body: SlidesIn, user: str = Depends(current_user)):
    if not body.content.strip():
        raise HTTPException(400, note_precondition("slides", ""))
    note = store.get_note(user, body.note_id) if body.note_id else None

    base = prompts.SLIDES_SYSTEM + (prompts.SLIDES_TALK_EXTRA if body.style == "talk" else "")
    messages = [
        {"role": "system", "content": prompts.compose_system(base, "slides", user)},
        {"role": "user", "content": prompts.slides_user(
            body.title or (note or {}).get("title", ""), body.content, body.style)},
    ]

    async def gen():
        md = ""
        stats: dict = {}
        try:
            async for piece in llm.stream(messages, max_tokens=body.max_tokens,
                                          temperature=0.4, stats=stats):
                md += piece
                yield sse("delta", {"text": piece})
        except Exception as exc:                       # noqa: BLE001
            yield sse("error", {"detail": str(exc)})
            yield sse("done", {})
            return

        md = md.strip()
        check = check_slides(md, body.content)
        note_id = ""
        if note and md:


            made = store.upsert_child(user, body.note_id, f"{note['title']} · Slides", md,
                                      source="slides", icon="bx-slideshow")
            note_id = made["id"]
        yield sse("slides", {"pages": check.pages, "cite_coverage": check.cite_coverage,
                             "notes": check.notes(), "note_id": note_id,
                             "truncated": stats.get("finish_reason") == "length"})
        yield sse("done", {})

    return sse_response(gen())


@router.post("/digest", response_model=DigestOut)
async def digest(body: DigestIn, user: str = Depends(current_user)):
    t0 = time.perf_counter()
    date_to = body.date_to or _date.today().isoformat()
    date_from = body.date_from or (_date.today() - timedelta(days=body.days)).isoformat()

    rows = UserMemory(user).facts_between(date_from, date_to, scope=body.scope)
    if not rows:
        from ..database.kb.scope import SCOPE_LABEL
        empty = ('No records in this period.' if body.scope in ("", "all")
                 else f'No records in this period within "{SCOPE_LABEL.get(body.scope, body.scope)}". Try the All memory scope.')
        return DigestOut(summary=empty, fact_count=0,
                         date_from=date_from, date_to=date_to,
                         took_ms=round((time.perf_counter() - t0) * 1000, 1))

    facts = [f"[{r['when']}] {r['text']}" for r in rows]
    system = prompts.compose_system(prompts.DIGEST_SYSTEM, "digest", user)
    text = await llm.complete(
        [{"role": "system", "content": system},
         {"role": "user", "content": prompts.digest_user(facts)}],
        max_tokens=1200, temperature=0.3)
    return DigestOut(summary=text.strip(), fact_count=len(rows),
                     date_from=date_from, date_to=date_to,
                     took_ms=round((time.perf_counter() - t0) * 1000, 1))


@router.post("/rewrite", response_model=EditOut)
async def rewrite(body: RewriteIn, user: str = Depends(current_user)):
    if not body.selection.strip():
        raise HTTPException(400, 'No text selected')
    t0 = time.perf_counter()
    if body.selection not in body.content:
        return EditOut(revisions=[], took_ms=round((time.perf_counter() - t0) * 1000, 1))
    base = prompts.POLISH_SYSTEM if body.intent == "polish" else prompts.REWRITE_SYSTEM
    scope = "polish" if body.intent == "polish" else "rewrite"
    system = doc_intent.block(body.doc_intent) + prompts.compose_system(base, scope, user)
    stats: dict = {}
    text = await llm.complete(
        [{"role": "system", "content": system},
         {"role": "user", "content": prompts.rewrite_user(
             body.content, body.selection, body.spine, body.beats)}],
        max_tokens=600, temperature=0.4, stats=stats)
    parsed = llm.extract_json(text)
    revisions: list[Revision] = []
    if isinstance(parsed, dict):
        new_text = str(parsed.get("text") or "").strip()
        if new_text:
            leading = body.selection[:len(body.selection) - len(body.selection.lstrip())]
            trailing = body.selection[len(body.selection.rstrip()):]
            new_text = leading + new_text + trailing
            default_reason = 'Polish' if body.intent == "polish" else 'Rewrite'
            revisions.append(Revision(
                id=uuid.uuid4().hex[:8], op="replace", anchor=body.selection,
                text=new_text, reason=str(parsed.get("reason") or default_reason),
            ))
    note = _truncated_note(stats, revisions)


    return EditOut(revisions=revisions, note=note,
                   unparsed=_unparsed(parsed, "text") and not note,
                   took_ms=round((time.perf_counter() - t0) * 1000, 1))


def _unparsed(parsed, *keys: str) -> bool:
    if not isinstance(parsed, dict):
        return True
    return not any(k in parsed for k in keys)


def _truncated_note(stats: dict, revisions: list) -> str:
    if stats.get("finish_reason") != "length":
        return ""
    revisions.clear()
    return "The selection exceeded the model's output limit. Select a shorter passage and retry."


@router.post("/expand", response_model=EditOut)
async def expand(body: ExpandIn, user: str = Depends(current_user)):
    if not body.selection.strip():
        raise HTTPException(400, 'No text selected')
    t0 = time.perf_counter()
    if body.selection not in body.content:
        return EditOut(revisions=[], took_ms=round((time.perf_counter() - t0) * 1000, 1))


    facts, _ids, _took = _retrieve(user, body.selection, "", [], limit=6, scope=body.scope)

    tray = tray_mod.lines_of(store.list_tray(user, body.note_id)) if body.note_id else []
    facts = tray + [f for f in facts if f not in tray]
    system = doc_intent.block(body.intent) + prompts.compose_system(prompts.EXPAND_SYSTEM, "expand", user)
    stats: dict = {}
    text = await llm.complete(
        [{"role": "system", "content": system},
         {"role": "user", "content": prompts.expand_user(body.content, body.selection, facts)}],
        max_tokens=500, temperature=0.5, stats=stats)
    parsed = llm.extract_json(text)
    revisions: list[Revision] = []
    if isinstance(parsed, dict):


        sources = [str(s) for s in (parsed.get("sources") or [])][:3]
        before = str(parsed.get("before") or "").strip()
        after = str(parsed.get("after") or "").strip()
        if before:
            revisions.append(Revision(
                id=uuid.uuid4().hex[:8], op="insert_before", anchor=body.selection,
                text=before, reason='Added preceding context', sources=sources,
            ))
        if after:
            revisions.append(Revision(
                id=uuid.uuid4().hex[:8], op="insert", anchor=body.selection,
                text=after, reason='Added following context', sources=sources,
            ))
    note = _truncated_note(stats, revisions)


    return EditOut(revisions=revisions, note=note,
                   unparsed=_unparsed(parsed, "before", "after") and not note,
                   took_ms=round((time.perf_counter() - t0) * 1000, 1))


def _cited_near(content: str, selection: str) -> list[str]:
    i = content.find(selection) if selection else -1
    if i < 0:
        scope = selection
    else:
        start = content.rfind("\n\n", 0, i) + 2 if content.rfind("\n\n", 0, i) >= 0 else 0
        end = content.find("\n\n", i + len(selection))
        scope = content[start:end if end >= 0 else len(content)]
    return citation_check.cited_ids(scope)[:6]


@router.post("/verify", response_model=VerifyOut)
async def verify(body: VerifyIn, user: str = Depends(current_user)):
    if not body.selection.strip():
        raise HTTPException(400, 'No text selected')
    t0 = time.perf_counter()
    mem = UserMemory(user)


    hits: list[dict] = []
    for fid in _cited_near(body.content, body.selection):
        f = mem.fact_by_id(fid)
        if f and f.get("text"):
            f = dict(f, date=f.get("date") or f.get("when", ""))
            hits.append(f)
    rows, _terms, _took = mem.recall(body.selection, limit=6, scope=body.scope)
    seen = {h["id"] for h in hits}
    hits += [r for r in rows if r.get("text") and r["id"] not in seen]
    facts = [r["text"] for r in hits]

    tray = tray_mod.lines_of(store.list_tray(user, body.note_id)) if body.note_id else []
    facts = tray + [f for f in facts if f not in tray]

    system = doc_intent.block(body.intent) + prompts.compose_system(prompts.VERIFY_SYSTEM, "verify", user)
    text = await llm.complete(
        [{"role": "system", "content": system},
         {"role": "user", "content": prompts.verify_user(body.content, body.selection, facts)}],
        max_tokens=800, temperature=0.1)
    parsed = llm.extract_json(text)
    findings: list[VerifyFinding] = []
    if isinstance(parsed, list):
        for item in parsed[:4]:
            if not isinstance(item, dict):
                continue
            verdict = str(item.get("verdict") or "")
            # Model prompts use English; preserve the existing API wire values.
            verdict = {
                "contradicts": '\u77db\u76fe',
                "supports": '\u652f\u6301',
                "unknown": '\u65e0\u6cd5\u5224\u65ad',
            }.get(verdict, verdict)
            if verdict not in ('\u77db\u76fe', '\u652f\u6301', '\u65e0\u6cd5\u5224\u65ad'):
                continue
            idx = item.get("fact_index")
            fact_id = fact_text = ""
            sources: list[str] = []
            if isinstance(idx, int) and 0 <= idx < len(hits):
                fact_id = hits[idx].get("id", "")
                fact_text = hits[idx].get("text", "")
                sources = mem.source_lines(hits[idx])
            findings.append(VerifyFinding(
                verdict=verdict, reason=str(item.get("reason") or ""),
                fact_id=fact_id, fact_text=fact_text, sources=sources,
            ))


    unparsed = (not isinstance(parsed, list)) or (bool(parsed) and not findings)
    return VerifyOut(findings=findings, checked=len(facts), unparsed=unparsed,
                     took_ms=round((time.perf_counter() - t0) * 1000, 1))
