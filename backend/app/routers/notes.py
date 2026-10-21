"""Note CRUD, branches, revisions, source citations and knowledge-ingestion state."""

from fastapi import APIRouter, Depends, HTTPException

from ..database.wordcount import word_count
from ..database import store
from ..database.kite.kite_memory import UserMemory
from .schemas import ChangeLayersBurnOut, ChangeLayersIn, ChangeLayersOut, ChangeLayersSaveOut, CitingNoteOut, EntityOut, Note, NoteBriefPage, NoteCreateIn, NoteGraphOut, NoteIconIn, NoteIn, NoteIntentIn, NoteLinksOut, NoteRoundsOut, TopicEntityLink, TopicOut, RevisionFullOut, RevisionOut, SkeletonSaveIn, TrayClipIn, TrayIn, TrayOut, WritingFeedbackOut
from .deps import current_user

router = APIRouter(prefix="/api/notes", tags=["notes"])


@router.get("", response_model=list[Note])
def list_notes(q: str = "", user: str = Depends(current_user)):
    return store.list_notes(user, q)


@router.post("", response_model=Note)
def create_note(body: NoteCreateIn, user: str = Depends(current_user)):
    if body.parent_note_id != store.ROOT_ID and not store.get_note(user, body.parent_note_id):
        raise HTTPException(404, 'Parent node not found')
    return store.create_note(user, body.title, body.content, body.parent_note_id)


@router.get("/brief", response_model=NoteBriefPage)
def list_notes_brief(q: str = "", user: str = Depends(current_user)):
    return store.list_notes_brief(user, q)


@router.post("/today", response_model=Note)
def today(day: str = "", user: str = Depends(current_user)):
    from datetime import date as _date
    try:
        d = _date.fromisoformat(day) if day else _date.today()
    except ValueError:
        raise HTTPException(400, f'Use a YYYY-MM-DD date: {day[:20]}')
    return store.today_note(user, d)


@router.get("/trash")
def list_trash(user: str = Depends(current_user)) -> list[dict]:
    return store.list_trash(user)


@router.post("/trash/{note_id}/restore", response_model=Note)
def restore_trash(note_id: str, user: str = Depends(current_user)):
    n = store.restore_from_trash(user, note_id)
    if not n:
        raise HTTPException(404, 'Note not found in Recently deleted')
    return n


@router.delete("/trash/{note_id}")
def purge_trash(note_id: str, user: str = Depends(current_user)) -> dict:
    if not store.purge_trash(user, note_id):
        raise HTTPException(404, 'Note not found in Recently deleted')
    return {"ok": True}


@router.get("/{note_id}", response_model=Note)
def get_note(note_id: str, user: str = Depends(current_user)):
    note = store.get_note(user, note_id)
    if not note:
        raise HTTPException(404, "note not found")
    return note


@router.get("/{note_id}/links", response_model=NoteLinksOut)
def note_links(note_id: str, user: str = Depends(current_user)):
    note = store.get_note(user, note_id)
    if not note:
        raise HTTPException(404, "note not found")
    outgoing, dangling = [], []
    for target in store.note_links_in(note["content"]):
        t = store.get_note(user, target)
        if t:
            outgoing.append(CitingNoteOut(id=t["id"], title=t["title"], updated_at=t["updated_at"],
                                          preview=(t["content"] or "")[:80], icon=t.get("icon") or ""))
        else:
            dangling.append(target)
    return NoteLinksOut(outgoing=outgoing, backlinks=[CitingNoteOut(**r) for r in store.backlinks(user, note_id)],
                        dangling=dangling)


@router.get("/{note_id}/graph", response_model=NoteGraphOut)
def note_graph(note_id: str, user: str = Depends(current_user)):
    from collections import Counter
    from ..database.kb import entities as entities_mod
    from ..database.kb.who import is_speaker_tag
    n = store.get_note(user, note_id)
    if not n:
        raise HTTPException(404, "note not found")
    mem = UserMemory(user)
    ids = list(store.cited_fact_ids(n["content"] or ""))
    if n.get("ingested_at"):
        ids += [f["id"] for f in mem.facts_for_prefix(UserMemory.note_prefix(note_id))]
    seen: set[str] = set()
    facts = []
    for fid in ids:
        if fid in seen:
            continue
        seen.add(fid)
        f = mem.fact_by_id(fid)
        if f:
            facts.append(f)
    if not facts:
        return NoteGraphOut()
    store_, vocab = mem._index()
    groups = entities_mod.for_store(store_, vocab)
    tcount: Counter = Counter()
    ecount: Counter = Counter()
    pair: Counter = Counter()
    for f in facts:
        ts = list(dict.fromkeys(f.get("topics") or []))
        es = [groups.canon(c) for c in (f.get("entities") or [])]
        es = [c for c in dict.fromkeys(es) if not is_speaker_tag(groups.name(c))]
        tcount.update(ts)
        ecount.update(es)
        for t in ts:
            for e in es:
                pair[(t, e)] += 1
    top_t = [c for c, _ in tcount.most_common(12)]
    top_e = [c for c, _ in ecount.most_common(20)]
    tset, eset = set(top_t), set(top_e)
    topics = [TopicOut(code=c, parents=sorted(p for p in (vocab.topics[c].parents if c in vocab.topics else ()) if p in tset),
                       status=vocab.topics[c].status if c in vocab.topics else "candidate",
                       aliases=sorted(vocab.topics[c].aliases) if c in vocab.topics else [], fact_count=tcount[c]) for c in top_t]
    entities = [EntityOut(code=c, name=groups.name(c), type=(vocab.entities[c].etype if c in vocab.entities else "") or "",
                          aliases=sorted(vocab.entities[c].aliases) if c in vocab.entities else [], fact_count=ecount[c]) for c in top_e]
    links = [TopicEntityLink(topic=t, entity=e, weight=w) for (t, e), w in pair.most_common() if t in tset and e in eset]
    return NoteGraphOut(facts=len(facts), topics=topics, entities=entities, links=links)


@router.get("/{note_id}/revisions", response_model=list[RevisionOut])
def list_revisions(note_id: str, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    return store.list_revisions(user, note_id)


@router.post("/{note_id}/revisions", response_model=RevisionOut)
def snapshot_note(note_id: str, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    r = store.snapshot_note(user, note_id)
    if not r:
        raise HTTPException(409, 'The body is empty; there is nothing to save')
    return r


@router.get("/{note_id}/revisions/{rev_id}", response_model=RevisionFullOut)
def get_revision(note_id: str, rev_id: str, user: str = Depends(current_user)):
    r = store.get_revision(user, note_id, rev_id)
    if not r:
        raise HTTPException(404, "revision not found")
    r["chars"] = word_count(r["content"])
    return r


@router.post("/{note_id}/revisions/{rev_id}/restore", response_model=Note)
def restore_revision(note_id: str, rev_id: str, user: str = Depends(current_user)):
    n = store.restore_revision(user, note_id, rev_id)
    if not n:
        raise HTTPException(404, "revision not found")
    return n


@router.get("/{note_id}/change-layers", response_model=ChangeLayersOut)
def list_change_layers(note_id: str, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    return ChangeLayersOut(layers=store.list_change_layers(user, note_id))


@router.get("/{note_id}/writing-feedback", response_model=WritingFeedbackOut)
def note_writing_feedback(note_id: str, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    return WritingFeedbackOut(**store.writing_feedback(user, note_id))


@router.get("/{note_id}/rounds", response_model=NoteRoundsOut)
def note_rounds(note_id: str, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    return NoteRoundsOut(**store.last_note_run_rounds(note_id))


@router.put("/{note_id}/change-layers", response_model=ChangeLayersSaveOut)
def save_change_layers(note_id: str, body: ChangeLayersIn, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    layers = [l.model_dump(by_alias=True) for l in body.layers]
    return ChangeLayersSaveOut(**store.save_change_layers(user, note_id, layers))


@router.delete("/{note_id}/change-layers", response_model=ChangeLayersBurnOut)
def burn_change_layers(note_id: str, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    return ChangeLayersBurnOut(dropped=store.burn_change_layers(user, note_id))


@router.put("/{note_id}", response_model=Note)
def update_note(note_id: str, body: NoteIn, user: str = Depends(current_user)):
    note = store.update_note(user, note_id, body.title, body.content)
    if not note:
        raise HTTPException(404, "note not found")
    return note


@router.put("/{note_id}/skeleton", response_model=Note)
def save_skeleton(note_id: str, body: SkeletonSaveIn, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    try:
        store.set_skeleton(user, note_id, body.spine.strip(),
                           [b for b in (x.strip() for x in body.beats) if b])
    except ValueError as exc:

        raise HTTPException(400, str(exc)) from exc
    return store.get_note(user, note_id)


@router.put("/{note_id}/intent", response_model=Note)
def save_intent(note_id: str, body: NoteIntentIn, user: str = Depends(current_user)):
    updated = store.set_intent(user, note_id, body.model_dump())
    if not updated:
        raise HTTPException(404, "note not found")
    return updated


@router.get("/{note_id}/tray", response_model=TrayOut)
def get_tray(note_id: str, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    return TrayOut(items=store.list_tray(user, note_id))


@router.put("/{note_id}/tray", response_model=TrayOut)
def put_tray(note_id: str, body: TrayIn, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    return TrayOut(items=store.replace_tray(user, note_id, [i.model_dump() for i in body.items]))


@router.post("/{note_id}/tray/clip", response_model=TrayOut)
def clip_to_tray(note_id: str, body: TrayClipIn, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    url = (body.url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, 'Enter an HTTP or HTTPS URL')
    title, text = fetch_page(url)
    if not text:
        raise HTTPException(400, "Could not extract text from this page. It may require login or JavaScript. Copy the relevant text and add it to this note's material.")


    items = [{k: it[k] for k in ("id", "kind", "ref_id", "title", "excerpt")} for it in store.list_tray(user, note_id)]
    items.append({"kind": "import", "ref_id": url, "title": title or url, "excerpt": text})
    return TrayOut(items=store.replace_tray(user, note_id, items))


CLIP_MAX_BYTES = 2_000_000
CLIP_TIMEOUT_S = 10.0


def fetch_page(url: str) -> tuple[str, str]:
    import httpx
    from ..database.ingest.importers import html_to_markdown
    try:
        with httpx.Client(follow_redirects=True, timeout=CLIP_TIMEOUT_S,
                          headers={"User-Agent": "Mozilla/5.0 memoket-note"}) as c:
            r = c.get(url)
    except httpx.HTTPError as exc:
        raise HTTPException(400, f'Could not connect to this URL: {type(exc).__name__}') from exc
    if r.status_code >= 400:
        raise HTTPException(400, f'The page returned {r.status_code}; could not retrieve its content')
    ctype = (r.headers.get("content-type") or "").lower()
    if "html" not in ctype and "text" not in ctype:
        raise HTTPException(400, f"The URL is not a web page ({ctype.split(';')[0] or 'unknown type'}）")
    html = r.content[:CLIP_MAX_BYTES].decode(r.encoding or "utf-8", errors="replace")
    return page_title(html), page_text(html, html_to_markdown)


def page_title(html: str) -> str:
    import html as _html
    import re
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return " ".join(_html.unescape(m.group(1)).split())[:store.TRAY_TITLE_MAX] if m else ""


def page_text(html: str, to_md) -> str:
    import re
    body = re.sub(r"<head\b.*?</head>", "", html, flags=re.I | re.S)
    body = re.sub(r"<(script|style|nav|footer|header|noscript)\b.*?</\1>", "", body, flags=re.I | re.S)
    m = re.search(r"<(article|main)\b.*?</\1>", body, flags=re.I | re.S)
    if m:
        body = m.group(0)
    try:
        text = to_md(body)
    except Exception:      # noqa: BLE001
        text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:store.TRAY_EXCERPT_MAX]


@router.delete("/{note_id}/tray/{item_id}", response_model=TrayOut)
def delete_tray_item(note_id: str, item_id: str, user: str = Depends(current_user)):
    if not store.get_note(user, note_id):
        raise HTTPException(404, "note not found")
    if not store.delete_tray_item(user, note_id, item_id):
        raise HTTPException(404, "tray item not found")
    return TrayOut(items=store.list_tray(user, note_id))


@router.delete("/{note_id}")
def delete_note(note_id: str, user: str = Depends(current_user)):
    removed = store.delete_note(user, note_id)
    if not removed:
        raise HTTPException(404, "note not found")
    return {"deleted": removed}


@router.post("/{note_id}/icon", response_model=Note)
def set_icon(note_id: str, body: NoteIconIn, user: str = Depends(current_user)):
    updated = store.set_icon(user, note_id, body.icon)
    if not updated:
        raise HTTPException(404, "note not found")
    return updated


@router.post("/{note_id}/pin", response_model=Note)
def pin_note(note_id: str, user: str = Depends(current_user)):
    note = store.get_note(user, note_id)
    if not note:
        raise HTTPException(404, "note not found")
    updated = store.set_pinned(user, note_id, not note["pinned"])
    if not updated:
        raise HTTPException(404, "note not found")
    return updated


@router.get("/{note_id}/kb")
def note_kb(note_id: str, user: str = Depends(current_user)) -> dict:
    n = store.get_note(user, note_id)
    if not n:
        raise HTTPException(404, "note not found")
    ingested_at = n.get("ingested_at") or ""
    updated_at = n.get("updated_at") or ""
    facts = UserMemory(user).facts_for_prefix(UserMemory.note_prefix(note_id)) if ingested_at else []
    return {
        "note_id": note_id,
        "ingested_at": ingested_at,
        "updated_at": updated_at,

        "stale": bool(ingested_at) and updated_at > ingested_at,
        "facts": facts,
        "manual_session": f"note-{note_id}-manual",
    }
