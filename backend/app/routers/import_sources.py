"""Read external note formats and batch sources into local import jobs, with cancellation and explicit progress."""

from __future__ import annotations

import hashlib
import os
import re
import json
import shutil
import subprocess
import sys
import time

import httpx
from dataclasses import asdict
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from ..database import store
from ..util.config import get_settings
from ..database.ingest import feishu, importers
from memoket_kite import StorageError

from ..database.kite.kite_memory import UserMemory
from ..database.kb import inbox
from ..harness.conflict_confirm import confirm_conflicts
from .schemas import IngestItemOut, IngestOut
from .deps import current_user
from ..database.ingest.chunking import chunks as _chunks

router = APIRouter(prefix="/api/import", tags=["import"])

_TERMINAL = {"done", "failed", "cancelled"}

MAX_FILES = 2000
NOTION_VERSION = "2026-03-11"


JOB_BUDGET_SECONDS: float | None = (
    float(os.environ["KITE_IMPORT_BUDGET_SECONDS"])
    if os.getenv("KITE_IMPORT_BUDGET_SECONDS") else None)


BUDGET_SLACK = 2.0


BUDGET_FLOOR_SECONDS = 600.0


def job_budget_seconds(user: str, n_chunks: int) -> float:
    if JOB_BUDGET_SECONDS is not None:
        return JOB_BUDGET_SECONDS
    return max(BUDGET_FLOOR_SECONDS,
               n_chunks * store.avg_chunk_ms(user) / 1000.0 * BUDGET_SLACK)


_ICON_RE = re.compile(r"bxs?-[a-z0-9-]{1,40}")


def _icon_of(meta: dict) -> str:
    v = str(meta.get("icon") or "").strip()
    return v if _ICON_RE.fullmatch(v) else ""


def _land(user: str, notes: list[importers.ImportedNote], to: str,
          job_id: str, items: list[dict]) -> None:
    folders: dict[str, str] = {}
    folder_body: dict[str, importers.ImportedNote] = {}
    for note in notes:
        if note.folder and note.title == note.folder.rsplit("/", 1)[-1]:
            folder_body.setdefault(note.folder, note)

    def folder_id(path: str) -> str | None:
        if not path:
            return None
        if path not in folders:
            parent = folder_id(path.rsplit("/", 1)[0]) if "/" in path else None
            name = path.rsplit("/", 1)[-1]
            body = folder_body.get(path)
            folders[path] = store.create_note(user, name, body.content if body else "",
                                              parent or store.ROOT_ID)["id"]
            if body and body.icon:
                store.set_icon(user, folders[path], body.icon)
        return folders[path]


    t_job = time.perf_counter()


    budget = job_budget_seconds(user, sum(len(_chunks(n.content)) for n in notes))

    def over_budget() -> bool:
        return budget > 0 and (time.perf_counter() - t_job) >= budget

    done_count = 0
    stopped_at = -1

    for pos, (note, item) in enumerate(zip(notes, items)):
        item_id = item["id"]
        if over_budget():
            stopped_at = pos
            break
        try:
            if store.is_cancel_requested(job_id):
                store.set_item(item_id, "cancelled")
                continue
            store.set_item(item_id, "chunking")
            store.update_job_from_items(job_id)
            store.mark_job_started(job_id)
            sha = store.content_sha(note.content)
            existing = store.find_note_by_source(user, note.source, note.source_id)
            note_state = "new"        # new / same / updated / local-modified

            landed_id = (existing or {}).get("id") or ""
            if to in ("both", "notes"):
                fid = folder_id(note.folder)
                if folder_body.get(note.folder) is note:
                    landed_id = folders.get(note.folder) or landed_id
                elif existing is None:
                    n = store.create_note(user, note.title, note.content, fid or store.ROOT_ID)
                    store.set_note_source(user, n["id"], note.source, note.source_id, sha)
                    landed_id = n["id"]
                    if note.icon:
                        store.set_icon(user, n["id"], note.icon)
                elif existing.get("source_sha") == sha:
                    note_state = "same"
                elif (existing.get("updated_at") or "") > (existing.get("imported_at") or ""):
                    note_state = "local-modified"
                else:
                    store.update_note_from_source(user, existing["id"], note.title, note.content, sha)
                    note_state = "updated"
            facts, skipped = 0, 0
            if to in ("both", "kb"):
                mem = UserMemory(user)


                if note_state in ("updated", "local-modified"):
                    mem.remove_sessions(f"{note.source}-{note.source_id}-")
                    if note_state == "local-modified" and existing:
                        store.set_note_source(user, existing["id"], note.source, note.source_id, sha)


                stem = f"{note.source}-{note.source_id}"
                when = note.date or importers.today()
                chunks = _chunks(note.content)
                store.set_item(item_id, "remembering", chunks_total=len(chunks), chunks_done=0)
                for i, chunk in enumerate(chunks):
                    if store.is_cancel_requested(job_id) or over_budget():
                        break
                    try:
                        t_chunk = time.perf_counter()
                        before_chunk = facts
                        facts += mem.remember([{"role": "user", "content": chunk}],
                                              session_id=f"{stem}-{i}", date=when,
                                              title=note.title)
                        ms = int((time.perf_counter() - t_chunk) * 1000)
                        store.bump_job_chunk(job_id, ms, len(chunk))
                        store.record_extract_estimate(user, len(chunk), facts - before_chunk, ms)
                    except StorageError as exc:


                        if "already exists" not in str(exc):
                            raise
                        skipped += 1
                        store.set_item(item_id, "remembering", facts=facts, chunks_done=i + 1)
                        continue
                    store.set_item(item_id, "remembering", facts=facts, chunks_done=i + 1)
                    store.update_job_from_items(job_id)
                    try:
                        inbox.scan_session(mem, user, f"{stem}-{i}", source=note.source,
                                           confirm=confirm_conflicts)
                    except Exception as exc:      # noqa: BLE001
                        print(f'[import] Conflict scan skipped for {stem}-{i}: {type(exc).__name__}: {exc}')
            state_note = {"same": 'Previously imported; content unchanged', "updated": 'Source changed; body updated',
                          "local-modified": 'Both source and local content changed. Local body preserved; knowledge-base extraction uses the source.'}.get(note_state, "")
            kb_note = (f'Previously imported; skipped {skipped} chunks' if skipped and not facts
                       else (f'Added {facts} facts; {skipped} chunks were previously imported' if skipped else ""))
            store.set_item(item_id, "done", facts=facts,
                           detail="；".join(x for x in (state_note, kb_note) if x),
                           note_id=landed_id)
            done_count += 1
        except Exception as exc:              # noqa: BLE001
            store.set_item(item_id, "failed", detail=f"{type(exc).__name__}: {exc}")
        store.update_job_from_items(job_id)

    if stopped_at >= 0:


        mins = int(budget // 60) or 1
        left = len(items) - stopped_at
        why = (f'This import reached its batch time limit ({mins} minutes) and paused. Of {len(items)} notes, {done_count} are complete and {left} have not started. Choose Continue to resume; completed items will not be imported or charged again.')
        for item in items[stopped_at:]:
            store.set_item(item["id"], "failed", detail=why)
    store.update_job_from_items(job_id)


def _reject_if_busy(user: str, except_job: str = "") -> None:
    for j in store.list_jobs(user, 10):
        if j["id"] == except_job:
            continue


        if any(it["status"] not in _TERMINAL for it in store.get_items(j["id"])):
            raise HTTPException(
                409, 'Another import is still running. Imports run sequentially; wait for it to finish or cancel it.')


def _payload_dir() -> Path:
    d = Path(get_settings().kite_data_dir) / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _queue(user: str, notes: list[importers.ImportedNote], to: str,
           bg: BackgroundTasks) -> IngestOut:
    if not notes:
        raise HTTPException(400, 'No importable content. Files may be empty or below the minimum length.')
    job_id, items = store.create_batch_job(
        user, [{"filename": n.title[:80], "kind": n.source} for n in notes])

    payload = _payload_dir() / f"{job_id}.json"
    payload.write_text(json.dumps({"user": user, "to": to, "notes": [asdict(n) for n in notes],
                                   "items": [it["id"] for it in items]}, ensure_ascii=False),
                       encoding="utf-8")
    store.set_job_payload(job_id, str(payload))

    n_chunks = sum(len(_chunks(n.content)) for n in notes)
    est = store.estimate(n_chunks, sum(len(n.content) for n in notes), store.avg_chunk_ms(user))
    bg.add_task(_land, user, notes, to, job_id, items)
    return IngestOut(job_id=job_id, status="queued",
                     items=[IngestItemOut(**it) for it in items], estimate=est)


@router.post("/jobs/{job_id}/resume", response_model=IngestOut)
def resume_job(job_id: str, bg: BackgroundTasks, user: str = Depends(current_user)):
    job = store.get_job(job_id)
    if not job or job["user_id"] != user:
        raise HTTPException(404, "job not found")
    if not job.get("payload_path") or not Path(job["payload_path"]).exists():
        raise HTTPException(400, 'This job has no persisted content to resume. Batch uploads are not retained.')
    if job["status"] in ("queued", "running", "cancelling"):
        raise HTTPException(409, 'This job is running')
    _reject_if_busy(user, except_job=job_id)
    data = json.loads(Path(job["payload_path"]).read_text(encoding="utf-8"))
    notes = [importers.ImportedNote(**n) for n in data["notes"]]
    by_id = {it["id"]: it for it in store.get_items(job_id)}
    todo_notes, todo_items = [], []
    for n, item_id in zip(notes, data["items"]):
        it = by_id.get(item_id)
        if it and it["status"] not in ("done", "cancelled"):
            store.set_item(item_id, "queued", detail="")
            todo_notes.append(n)
            todo_items.append(it)
    if not todo_notes:
        store.update_job_from_items(job_id)
        raise HTTPException(400, 'No remaining items to continue')
    store.set_job(job_id, "running", facts=job["facts"])
    bg.add_task(_land, user, todo_notes, data["to"], job_id, todo_items)
    return IngestOut(job_id=job_id, status="running", items=[IngestItemOut(**it) for it in todo_items])


@router.post("/files", response_model=IngestOut)
async def import_files(bg: BackgroundTasks,
                       files: list[UploadFile] = File(...),
                       source: str = Form("obsidian"),
                       to: str = Form("both"),
                       min_chars: int = Form(10),
                       user: str = Depends(current_user)):
    _reject_if_busy(user)
    if source not in ("obsidian", "evernote"):
        raise HTTPException(400, f'This endpoint accepts only obsidian or evernote; received {source!r}')
    if len(files) > MAX_FILES:
        raise HTTPException(400, f'At most {MAX_FILES} files per batch')

    notes: list[importers.ImportedNote] = []
    for f in files:
        name = f.filename or "note"
        data = await f.read()
        if not data:
            continue
        if source == "evernote":
            if not name.lower().endswith(".enex"):
                continue
            notes += importers.parse_enex(data)
            continue
        if not name.lower().endswith((".md", ".markdown", ".txt")):
            continue

        rel = name.replace("\\", "/")
        if any(p.startswith(".") for p in rel.split("/")):
            continue
        try:
            raw = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        meta, body = importers.parse_frontmatter(raw)
        body = importers.clean_obsidian(body)
        if not body.strip():
            continue
        stem = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""


        notes.append(importers.ImportedNote(
            title=meta.get("title") or stem, content=body,
            date=importers.normalize_date(meta.get("created") or meta.get("date")),
            source="obsidian",
            source_id=hashlib.sha1(rel.encode()).hexdigest()[:16],
            folder=parent,
            icon=_icon_of(meta)))

    if min_chars:
        notes = [n for n in notes if len(n.content.strip()) >= min_chars]
    return _queue(user, notes, to, bg)


@router.post("/notion", response_model=IngestOut)
def import_notion(bg: BackgroundTasks, token: str = Form(...), to: str = Form("both"),
                  limit: int = Form(0), user: str = Depends(current_user)):
    _reject_if_busy(user)
    nh = {"Authorization": f"Bearer {token.strip()}",
          "Notion-Version": NOTION_VERSION, "Content-Type": "application/json"}
    pages, cursor = [], None
    try:
        while True:
            body = {"filter": {"property": "object", "value": "page"}, "page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            r = httpx.post("https://api.notion.com/v1/search", headers=nh,
                           json=body, timeout=60)
            r.raise_for_status()
            data = r.json()
            pages += data.get("results", [])
            if not data.get("has_more") or (limit and len(pages) >= limit):
                break
            cursor = data["next_cursor"]
            time.sleep(0.34)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(400, f'Notion rejected the token: {exc.response.status_code}') from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f'Could not connect to Notion: {exc}') from exc

    if limit:
        pages = pages[:limit]
    notes: list[importers.ImportedNote] = []
    skipped = 0
    for i, page in enumerate(pages):
        pid = page["id"]
        try:
            m = httpx.get(f"https://api.notion.com/v1/pages/{pid}/markdown",
                          headers=nh, timeout=120)
            m.raise_for_status()
            md = (m.json().get("markdown") or "").strip()
        except httpx.HTTPError:

            skipped += 1
            continue
        if md:
            notes.append(importers.ImportedNote(
                title=_notion_title(page) or 'Untitled', content=md,
                date=importers.normalize_date(page.get("created_time")),
                source="notion", source_id=pid.replace("-", "")))
        if i % 3 == 2:
            time.sleep(0.34)
    if not notes and skipped:
        raise HTTPException(400, f'{skipped} pages could not be read. Connect them to this integration in Notion.')
    return _queue(user, notes, to, bg)


@router.post("/feishu", response_model=IngestOut)
def import_feishu(bg: BackgroundTasks, app_id: str = Form(...), app_secret: str = Form(...),
                  scope: str = Form("wiki"), to: str = Form("both"), limit: int = Form(0),
                  docs: str = Form(""),
                  user: str = Depends(current_user)):
    _reject_if_busy(user)
    if scope not in ("wiki", "drive"):
        raise HTTPException(400, 'scope must be wiki or drive')
    client = feishu.FeishuClient(app_id, app_secret)
    refs = [x.strip() for x in re.split(r"[\s,;]+", docs or "") if x.strip()]
    try:
        client.token()
        if refs:
            found = [client.resolve_doc(r) for r in refs]
        else:
            found = client.list_wiki_docs(limit) if scope == "wiki" else client.list_drive_docs(limit)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(400, f'Feishu rejected the request: {exc.response.status_code}') from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f'Could not connect to Feishu: {exc}') from exc
    if not found:
        raise HTTPException(400, 'The app cannot see any documents. Add it as a collaborator to the documents or wiki, or change scope (wiki or drive). If only an individual document is shared, paste its link directly.')
    notes: list[importers.ImportedNote] = []
    skipped = 0
    for i, d in enumerate(found):
        try:
            blocks = client.document_blocks(d["document_id"])
        except (RuntimeError, httpx.HTTPError):
            skipped += 1
            continue
        md = feishu.blocks_to_markdown(blocks).strip()
        if not md:
            skipped += 1
            continue
        notes.append(importers.ImportedNote(
            title=d.get("title") or feishu.page_title(blocks) or 'Untitled', content=md,
            date=feishu.epoch_to_date(d.get("created")), source="feishu", source_id=d["document_id"]))
        if i % 5 == 4:
            time.sleep(0.2)
    if not notes:
        raise HTTPException(400, f'{skipped} documents could not be read. Check docx:document:readonly permission and add the app as a collaborator.')
    return _queue(user, notes, to, bg)


def _notion_title(page: dict) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", [])).strip()
    return ""


# ---------------------------------------------------------------- Apple Notes


_APPLESCRIPT = r"""
set out to {}
tell application "Notes"
    repeat with f in folders
        set fname to name of f
        repeat with n in notes of f
            try
                set end of out to ((id of n) & "\t" & (name of n) & "\t" & ((modification date of n) as string) & "\t" & fname & "\t" & (body of n))
            end try
        end repeat
    end repeat
end tell
set AppleScript's text item delimiters to "\n<<<REC>>>\n"
return out as string
"""


def _apple_available() -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, 'The backend must run on macOS to export Apple Notes locally.'
    if not shutil.which("osascript"):
        return False, 'osascript is unavailable'
    return True, ""


@router.get("/apple/available")
def apple_available(user: str = Depends(current_user)) -> dict:
    ok, why = _apple_available()
    return {"available": ok, "reason": why}


@router.post("/apple", response_model=IngestOut)
def import_apple(bg: BackgroundTasks, to: str = Form("both"), limit: int = Form(0),
                 user: str = Depends(current_user)):
    _reject_if_busy(user)
    ok, why = _apple_available()
    if not ok:
        raise HTTPException(400, why)
    try:
        r = subprocess.run(["osascript", "-e", _APPLESCRIPT],
                           capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, 'Export timed out. Try a smaller batch with --limit.') from exc
    if r.returncode != 0:


        raise HTTPException(
            400, f'Could not read Apple Notes. Allow control of Notes when macOS asks, or enable it under System Settings > Privacy & Security > Automation. Error: {r.stderr.strip()[:200]}')

    notes: list[importers.ImportedNote] = []
    for rec in r.stdout.split("\n<<<REC>>>\n"):
        parts = rec.split("\t", 4)
        if len(parts) < 5:
            continue
        nid, title, mdate, folder, body_html = parts
        body = importers.html_to_markdown(body_html)
        if not body.strip():
            continue
        notes.append(importers.ImportedNote(
            title=title.strip() or 'Untitled', content=body,
            date=importers.normalize_date(mdate), source="apple",
            source_id=hashlib.sha1(nid.encode()).hexdigest()[:16],
            folder=folder.strip()))
        if limit and len(notes) >= limit:
            break
    return _queue(user, notes, to, bg)
