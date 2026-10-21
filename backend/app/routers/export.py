"""Export note trees and writing artifacts to supported local and connected destinations."""

from __future__ import annotations

import base64
import binascii
import io
import re
import zipfile
from datetime import datetime, timezone
import os
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from ..database import exporters, store
from ..database import assets as _assets_store
from .deps import current_user

router = APIRouter(prefix="/api/export", tags=["export"])

def build_export(user: str) -> bytes:
    files = exporters.render_tree(user)
    buf = io.BytesIO()
    assets_needed: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.writestr(f.path, f.content)
            assets_needed |= f.assets
        for name in sorted(assets_needed):
            path = _assets_store.assets_dir() / name
            if path.is_file():
                z.write(path, f"_assets/{name}")
        z.writestr("README.txt",
                   f"MEMOKET NOTE export · {datetime.now(timezone.utc).isoformat(timespec='seconds')}\nUser: {user}\nNotes: {sum((1 for f in files if f.note_id))}\n\nEach Markdown file starts with front matter containing its note ID, title and timestamps. The body preserves the original Markdown.\nA note with children is a folder; its own body is in the Markdown file with the same name.\nA *.link.txt file represents a clone and points to the file containing its body.\nReferenced images and audio are in _assets/ with relative links.\n")
    return buf.getvalue()


class ObsidianOut(BaseModel):
    vault_dir: str
    note_ids: list[str] = []
    force: bool = False


class NotionOut(BaseModel):
    token: str
    parent_page_id: str
    note_ids: list[str] = []
    force: bool = False


class FeishuOut(BaseModel):
    app_id: str
    app_secret: str
    folder_token: str = ""
    note_ids: list[str] = []
    force: bool = False


class MermaidIn(BaseModel):
    note_ids: list[str] = []


class RendersIn(BaseModel):
    renders: dict[str, str] = {}


_RENDERS: dict[str, dict[str, bytes]] = {}
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_KEY_RE = re.compile(r"^[a-f0-9]{24}$")


def png_from_data_url(url: str) -> bytes | None:
    if not isinstance(url, str) or not url.startswith("data:image/png;base64,"):
        return None
    try:
        data = base64.b64decode(url[len("data:image/png;base64,"):], validate=True)
    except (ValueError, binascii.Error):
        return None
    if not data.startswith(_PNG_MAGIC) or len(data) > exporters.MERMAID_RENDER_MAX:
        return None
    return data


@router.post("/mermaid")
def export_mermaid(body: MermaidIn, user: str = Depends(current_user)) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in _pick(user, body.note_ids):
        out.update(exporters.mermaid_blocks(f.content))
    return out


@router.post("/renders")
def export_renders(body: RendersIn, user: str = Depends(current_user)) -> dict:
    stored: dict[str, bytes] = {}
    rejected: list[str] = []
    for key, url in list(body.renders.items())[:exporters.MERMAID_RENDERS_MAX]:
        data = png_from_data_url(url) if _KEY_RE.match(str(key)) else None
        if data is None:
            rejected.append(str(key)[:40])
            continue
        stored[key] = data
    _RENDERS[user] = stored
    return {"stored": len(stored), "rejected": rejected}


def obsidian_url(vault: Path, rel_path: str) -> str:
    return "obsidian://open?path=" + quote(str(vault / rel_path), safe="/")


def _missing(user: str, note_ids: list[str], files: list[exporters.ExportFile]) -> list[str]:
    have = {f.note_id for f in files}
    return [i for i in note_ids if i not in have]


@router.post("/obsidian")
def export_obsidian(body: ObsidianOut, user: str = Depends(current_user)) -> dict:
    if not body.vault_dir.strip():

        raise HTTPException(400, 'A vault directory is required')
    vault = Path(body.vault_dir.strip()).expanduser()
    if not vault.is_absolute():
        raise HTTPException(400, f'The vault directory must be an absolute path: {vault}')
    if vault.is_file():
        raise HTTPException(400, f'This path is a file, not a directory: {vault}')
    if not vault.is_dir():
        raise HTTPException(400, f'Directory not found: {vault}')
    if not os.access(vault, os.W_OK):
        raise HTTPException(400, f'The directory is not writable: {vault}')
    only = set(body.note_ids) or None
    files = exporters.render_tree(user, only)
    written, skipped, conflicts, urls = [], [], [], []
    assets: set[str] = set()
    for f in files:
        target = vault / f.path
        if f.note_id:
            prev = store.get_remote(user, f.note_id, "obsidian")
            current = target.read_text(encoding="utf-8", errors="replace") if target.exists() else None
            if current == f.content:
                skipped.append(f.path)
                store.record_remote(user, f.note_id, "obsidian", remote_id=store.content_sha(f.content), remote_path=f.path)
                continue

            if current is not None and prev and prev.get("remote_id") and store.content_sha(current) != prev["remote_id"] and not body.force:
                conflicts.append(f.path)
                continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.content, encoding="utf-8")
        except OSError as exc:
            raise HTTPException(400, f'Could not write {f.path}：{exc.strerror or exc}')
        written.append(f.path)
        assets |= f.assets
        if f.note_id:
            store.record_remote(user, f.note_id, "obsidian", remote_id=store.content_sha(f.content), remote_path=f.path)
            urls.append({"note_id": f.note_id, "title": f.title, "url": obsidian_url(vault, f.path)})
    for name in sorted(assets):
        src = _assets_store.assets_dir() / name
        if src.is_file():
            dst = vault / "_assets" / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                dst.write_bytes(src.read_bytes())
    return {"written": len(written), "skipped": len(skipped), "conflicts": conflicts, "files": written[:50],
            "missing": _missing(user, body.note_ids, [f for f in files if f.note_id]),
            "urls": urls[:50], "url": urls[0]["url"] if len(urls) == 1 else ""}


def _pick(user: str, note_ids: list[str]) -> list[exporters.ExportFile]:
    only = set(note_ids) or None
    return [f for f in exporters.render_tree(user, only) if f.note_id]


def _need(value: str, msg: str) -> None:
    if not (value or "").strip():
        raise HTTPException(400, msg)


def _needs_create(user: str, files: list, kind: str) -> bool:
    return any(not (store.get_remote(user, f.note_id, kind) or {}).get("remote_id")
               for f in files)


def _probe(fn, what: str) -> None:
    try:
        fn()
    except exporters.RemoteError as exc:
        raise HTTPException(400, str(exc))
    except (httpx.HTTPError, KeyError) as exc:
        raise HTTPException(400, f'Could not connect to {what}：{exc}')


class _Breaker:
    def __init__(self) -> None:
        self.last = ""
        self.tripped = False

    def hit(self, exc: BaseException) -> None:
        key = f"{getattr(exc, 'status', 0)}:{getattr(exc, 'code', '')}" if isinstance(exc, exporters.RemoteError) else exc.__class__.__name__
        if key == self.last:
            self.tripped = True
        self.last = key

    def ok(self) -> None:
        self.last = ""


def _finish(created: list, updated: list, failed: list, conflicts: list, urls: list, missing: list, untried: int) -> dict:
    if not created and not updated and failed:
        raise HTTPException(400, 'No notes were exported: ' + failed[0] + (f' ({untried} additional notes were not attempted)' if untried else ""))
    return {"created": len(created), "updated": len(updated), "failed": failed, "conflicts": conflicts,
            "missing": missing, "untried": untried,
            "urls": urls[:50], "url": urls[0]["url"] if len(urls) == 1 else ""}


@router.post("/notion")
def export_notion(body: NotionOut, user: str = Depends(current_user)) -> dict:
    _need(body.token, 'Notion integration token is required')
    files = _pick(user, body.note_ids)
    missing = _missing(user, body.note_ids, files)
    w = exporters.NotionWriter(body.token)
    _probe(w.probe, " Notion")
    if _needs_create(user, files, "notion"):
        _need(body.parent_page_id, 'A parent page ID is required; notes will be created as its child pages')
        _probe(lambda: w.check_parent(body.parent_page_id), " Notion")
    created, updated, failed, conflicts, urls = [], [], [], [], []
    br = _Breaker()
    untried = 0
    for k, f in enumerate(files):
        if br.tripped:
            untried = len(files) - k
            break
        blocks = exporters.md_to_notion_blocks(f.content)
        try:
            prev = store.get_remote(user, f.note_id, "notion")
            if prev and prev.get("remote_id"):
                pid = prev["remote_id"]
                if prev.get("remote_rev") and not body.force and w.last_edited(pid) != prev["remote_rev"]:
                    conflicts.append(f.title)
                    continue
                r = w.replace_children(pid, f.title, blocks)
                updated.append(f.title)
            else:
                r = w.create_page(body.parent_page_id, f.title, blocks)
                created.append(f.title)
            store.record_remote(user, f.note_id, "notion", remote_id=r["id"], remote_path=r["url"], remote_rev=r["rev"])
            urls.append({"note_id": f.note_id, "title": f.title, "url": r["url"]})
            br.ok()
        except (httpx.HTTPError, KeyError, RuntimeError) as exc:
            failed.append(f"{f.title}: {exc}")
            br.hit(exc)
    return _finish(created, updated, failed, conflicts, urls, missing, untried)


@router.post("/feishu")
def export_feishu(body: FeishuOut, user: str = Depends(current_user)) -> dict:
    _need(body.app_id, 'Feishu App ID is required')
    _need(body.app_secret, 'Feishu App Secret is required')
    files = _pick(user, body.note_ids)
    missing = _missing(user, body.note_ids, files)
    if _needs_create(user, files, "feishu"):
        _need(body.folder_token, 'A folder token is required; new documents will be created inside it')
    w = exporters.FeishuWriter(body.app_id, body.app_secret)
    _probe(w.probe, 'Feishu')
    renders = _RENDERS.pop(user, {})
    created, updated, failed, conflicts, urls = [], [], [], [], []
    br = _Breaker()
    untried = 0
    for k, f in enumerate(files):
        if br.tripped:
            untried = len(files) - k
            break
        children = exporters.md_to_feishu_children(f.content, renders)
        try:
            prev = store.get_remote(user, f.note_id, "feishu")
            if prev and prev.get("remote_id"):
                did = prev["remote_id"]
                if prev.get("remote_rev") and not body.force and w.edited_time(did) != prev["remote_rev"]:
                    conflicts.append(f.title)
                    continue
                w.replace_children(did, children)
                updated.append(f.title)
                url = prev.get("remote_path") or w.doc_url(did)
            else:
                did = w.create_document(body.folder_token, f.title)
                w.replace_children(did, children)
                created.append(f.title)
                url = w.doc_url(did)
            store.record_remote(user, f.note_id, "feishu", remote_id=did, remote_path=url, remote_rev=w.edited_time(did))
            urls.append({"note_id": f.note_id, "title": f.title, "url": url})
            br.ok()
        except (httpx.HTTPError, KeyError, RuntimeError) as exc:
            failed.append(f"{f.title}: {exc}")
            br.hit(exc)
    return _finish(created, updated, failed, conflicts, urls, missing, untried)


@router.get("/remotes/{note_id}")
def note_remotes(note_id: str, user: str = Depends(current_user)) -> list[dict]:
    return store.list_remotes(user, note_id)


@router.get("/markdown")
def export_markdown(user: str = Depends(current_user),
                    user_q: str | None = Query(None, alias="user")):
    who = user_q or user
    data = build_export(who)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="memoket-note-{stamp}.zip"'})
