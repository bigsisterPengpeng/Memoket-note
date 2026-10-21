"""Local asset upload and retrieval routes with bounded file validation."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..database import assets as assets_store
from .deps import current_user

router = APIRouter(prefix="/api/assets", tags=["assets"])

MAX_BYTES = 32 * 1024 * 1024


ALLOWED = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
    "image/webp": ".webp", "image/svg+xml": ".svg",
    "audio/webm": ".webm", "audio/mpeg": ".mp3", "audio/wav": ".wav",
    "audio/x-wav": ".wav", "audio/mp4": ".m4a", "audio/ogg": ".ogg",
}


def _dir() -> Path:
    return assets_store.assets_dir()


@router.post("")
async def upload(file: UploadFile = File(...), user: str = Depends(current_user)) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(400, 'The file is empty')
    if len(data) > MAX_BYTES:
        raise HTTPException(400, f'The file is too large ({len(data) // 1024 // 1024} MB); maximum 32 MB')
    ctype = (file.content_type or "").split(";")[0].strip().lower()
    ext = ALLOWED.get(ctype)
    if not ext:

        guess = mimetypes.guess_type(file.filename or "")[0] or ""
        ext = ALLOWED.get(guess)
        ctype = guess
    if not ext:
        raise HTTPException(400, f"Unsupported type {file.content_type or 'unknown'}; only images and audio are accepted")
    name = hashlib.sha256(data).hexdigest()[:24] + ext
    path = _dir() / name
    if not path.exists():
        path.write_bytes(data)
    return {"url": f"/api/assets/{name}", "name": file.filename or name,
            "content_type": ctype, "bytes": len(data),
            "kind": "image" if ctype.startswith("image/") else "audio"}


@router.get("/{name}")
def fetch(name: str):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, 'Invalid filename')
    path = _dir() / name
    if not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path)
