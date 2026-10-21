"""Import jobs and streaming progress. Background work retains the request locale and user scope."""

from __future__ import annotations

import asyncio
import json
import hashlib
import time
import uuid
from datetime import date as _date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from ..database import store
from ..database.ingest import asr, extract
from ..database.ingest.chunking import chunks as _chunks, chunks_for as _chunks_for
from ..database.kite.kite_memory import UserMemory
from ..database.kb import inbox
from ..harness.conflict_confirm import confirm_conflicts
from memoket_kite.errors import StorageError
from .schemas import IngestItemOut, IngestOut, IngestTextIn
from ..harness.events import sse
from .deps import current_user, sse_response

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


BATCH_MAX_FILES = 50


def _scan_conflicts(mem: UserMemory, user_id: str, session_id: str, source: str) -> None:
    try:
        inbox.scan_session(mem, user_id, session_id, source=source,
                           confirm=confirm_conflicts)
    except Exception as exc:      # noqa: BLE001
        print(f'[ingest] Conflict scan skipped for {session_id}: {type(exc).__name__}: {exc}')


def _ingest_job(job_id: str, user_id: str, text: str, title: str, source: str,
                date: str = "", source_id: str = "", replace: bool = False) -> None:
    store.set_job(job_id, "running")
    try:
        mem = UserMemory(user_id)
        total = 0
        skipped = 0


        if replace and source == "note" and source_id:
            gone = {f["id"] for f in mem.facts_for_prefix(UserMemory.note_prefix(source_id))}
            mem.remove_sessions(UserMemory.note_prefix(source_id))
            store.drop_conflicts_for_facts(user_id, gone)


        stem = f"{source}-{source_id}" if source_id else f"{source}-{uuid.uuid4().hex[:8]}"
        when = date or _date.today().isoformat()
        chunks = _chunks(text)

        store.set_job_chunks_total(job_id, len(chunks))
        store.mark_job_started(job_id)
        for i, chunk in enumerate(chunks):
            t_chunk = time.perf_counter()
            before_chunk = total
            try:
                total += mem.remember(
                    [{"role": "user", "content": chunk}],
                    session_id=f"{stem}-{i}",
                    date=when,
                    title=title,
                )
            except StorageError as exc:


                if "already exists" not in str(exc):
                    raise
                skipped += 1
                continue


            ms = int((time.perf_counter() - t_chunk) * 1000)
            store.bump_job_chunk(job_id, ms, len(chunk))
            store.record_extract_estimate(user_id, len(chunk), total - before_chunk, ms)
            store.set_job(job_id, "running", facts=total)
            _scan_conflicts(mem, user_id, f"{stem}-{i}", source)
        store.set_job(job_id, "done", facts=total,
                      detail=(f'Content unchanged; {skipped} chunks were already ingested' if skipped and not total else ""))


        if source == "note" and source_id:
            store.mark_ingested(user_id, source_id)
    except Exception as exc:
        store.set_job(job_id, "error", detail=f"{type(exc).__name__}: {exc}")


@router.post("/text", response_model=IngestOut)
def ingest_text(body: IngestTextIn, bg: BackgroundTasks,
                user: str = Depends(current_user)):
    if not body.content.strip():
        raise HTTPException(400, "content is empty")
    job_id = store.create_job(user)
    bg.add_task(_ingest_job, job_id, user, body.content, body.title, body.source,
                body.date, body.source_id, body.replace)
    return IngestOut(job_id=job_id, status="queued")


@router.post("/note/{note_id}/sync", response_model=IngestOut)
def sync_note(note_id: str, bg: BackgroundTasks, user: str = Depends(current_user)):
    n = store.get_note(user, note_id)
    if not n:
        raise HTTPException(404, "note not found")
    if not (n.get("content") or "").strip():
        raise HTTPException(400, "content is empty")
    job_id = store.create_job(user)
    bg.add_task(_ingest_job, job_id, user, n["content"], n.get("title") or 'Untitled', "note",
                "", note_id, True)
    return IngestOut(job_id=job_id, status="queued")


@router.post("/audio", response_model=IngestOut)
async def ingest_audio(bg: BackgroundTasks,
                       file: UploadFile = File(...),
                       language: str = Form("auto"),
                       title: str = Form(""),
                       user: str = Depends(current_user)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty audio")
    try:
        text = await asr.transcribe(data, filename=file.filename or "audio.wav",
                                    language=language)
    except Exception as exc:
        raise HTTPException(502, asr.describe_error(exc)) from exc
    if not text:
        return IngestOut(job_id="", status="done", facts=0,
                         detail='The transcript is empty; the audio may be silent')

    job_id = store.create_job(user)
    bg.add_task(_ingest_job, job_id, user, text, title or (file.filename or ""),
                "audio")
    return IngestOut(job_id=job_id, status="queued", detail=text[:2000])


@router.post("/transcribe")
async def transcribe_only(file: UploadFile = File(...),
                          language: str = Form("auto")):
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty audio")
    try:
        text = await asr.transcribe(data, filename=file.filename or "audio.wav",
                                    language=language)
    except Exception as exc:
        raise HTTPException(502, asr.describe_error(exc)) from exc
    return {"text": text}


#            -> remembering -> done | failed | cancelled


def _extract_item_text(filename: str, kind: str, data: bytes, language: str) -> str:
    if kind == "audio":
        return asyncio.run(asr.transcribe(data, filename=filename, language=language))
    return extract.extract_text(data, filename)


def _batch_job(job_id: str, user_id: str, items: list[dict],
               payloads: dict[str, bytes], language: str) -> None:
    store.set_job(job_id, "running")
    store.mark_job_started(job_id)
    mem = UserMemory(user_id)
    for item in items:
        item_id, filename, kind = item["id"], item["filename"], item["kind"]
        if store.is_cancel_requested(job_id):
            store.set_item(item_id, "cancelled")
            store.update_job_from_items(job_id)
            continue
        try:
            store.set_item(item_id, "transcribing" if kind == "audio" else "extracting")
            text = _extract_item_text(filename, kind, payloads[item_id], language)
            store.update_job_from_items(job_id)

            if not text or not text.strip():
                store.set_item(item_id, "done", facts=0, detail='The content is empty')
                store.update_job_from_items(job_id)
                continue

            store.set_item(item_id, "chunking")
            store.update_job_from_items(job_id)
            chunks = _chunks_for(text, kind)
            file_date = _date.today().isoformat()

            store.set_item(item_id, "remembering", chunks_total=len(chunks), chunks_done=0)
            store.update_job_from_items(job_id)
            total = 0
            cancelled_mid_file = False
            content_key = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
            for i, chunk in enumerate(chunks):


                if store.is_cancel_requested(job_id):
                    cancelled_mid_file = True
                    break
                t_chunk = time.perf_counter()
                total += mem.remember(
                    [{"role": "user", "content": chunk}],


                    session_id=f"file-{content_key}-{i}",
                    date=file_date,
                    title=filename,
                )
                store.bump_job_chunk(job_id, int((time.perf_counter() - t_chunk) * 1000), len(chunk))


                store.set_item(item_id, "remembering", facts=total, chunks_done=i + 1)
                store.update_job_from_items(job_id)
            if cancelled_mid_file:
                store.set_item(item_id, "cancelled", facts=total,
                              detail=f'Cancelled after processing {i}/{len(chunks)} chunks')
            else:
                store.set_item(item_id, "done", facts=total)
        except Exception as exc:  # noqa: BLE001
            store.set_item(item_id, "failed", detail=f"{type(exc).__name__}: {exc}")
        store.update_job_from_items(job_id)


@router.post("/batch", response_model=IngestOut)
async def ingest_batch(bg: BackgroundTasks,
                       files: list[UploadFile] = File(...),
                       language: str = Form("auto"),
                       user: str = Depends(current_user)):
    if not files:
        raise HTTPException(400, "no files")
    if len(files) > BATCH_MAX_FILES:
        raise HTTPException(400, f'At most {BATCH_MAX_FILES} files per batch')


    specs: list[dict] = []
    raw: list[bytes] = []
    for f in files:
        try:
            kind = extract.kind_for(f.filename or "")
        except extract.UnsupportedFileType as exc:
            raise HTTPException(400, str(exc)) from exc
        data = await f.read()
        if not data:
            raise HTTPException(400, f'Empty file: {f.filename}')
        specs.append({"filename": f.filename or "file", "kind": kind})
        raw.append(data)

    job_id, items = store.create_batch_job(user, specs)


    keyed_payloads = {item["id"]: raw[item["idx"]] for item in items}
    bg.add_task(_batch_job, job_id, user, items, keyed_payloads, language)
    return IngestOut(job_id=job_id, status="queued",
                     items=[IngestItemOut(**it) for it in items])


@router.get("/jobs", response_model=list[IngestOut])
def list_jobs(user: str = Depends(current_user), limit: int = 20):
    jobs = store.list_jobs(user, limit)
    return [
        IngestOut(job_id=j["id"], status=j["status"], facts=j["facts"],
                  detail=j["detail"],
                  items=[IngestItemOut(**it) for it in store.get_items(j["id"])],
                  **store.job_progress(j["id"]))
        for j in jobs
    ]


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user: str = Depends(current_user)):
    job = store.get_job(job_id)
    if not job or job["user_id"] != user:
        raise HTTPException(404, "job not found")
    store.request_cancel(job_id)


    for it in store.get_items(job_id):
        if it["status"] == "queued":
            store.set_item(it["id"], "cancelled")
    store.update_job_from_items(job_id)
    return {"ok": True, "status": (store.get_job(job_id) or {}).get("status", "")}


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, user: str = Depends(current_user)):
    job = store.get_job(job_id)
    if not job or job["user_id"] != user:
        raise HTTPException(404, "job not found")

    async def gen():
        last = None
        while True:
            j = store.get_job(job_id)
            snap = {
                "job_id": j["id"], "status": j["status"], "facts": j["facts"],
                "detail": j["detail"], "items": store.get_items(job_id),
                **store.job_progress(job_id),
            }


            frame = json.dumps(snap, ensure_ascii=False, sort_keys=True)
            if frame != last:
                last = frame
                yield sse("progress", snap)
            if j["status"] in ("done", "error", "cancelled"):
                yield sse("end", {})
                return
            await asyncio.sleep(0.7)

    return sse_response(gen())


@router.get("/jobs/{job_id}", response_model=IngestOut)
def job_status(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return IngestOut(job_id=job["id"], status=job["status"], facts=job["facts"],
                     detail=job["detail"], items=[
                         IngestItemOut(**it) for it in store.get_items(job_id)],
                     **store.job_progress(job_id))
