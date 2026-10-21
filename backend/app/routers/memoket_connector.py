"""Explicit recording reads and incremental source imports from Memoket."""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from ..connectors import memoket
from ..database.ingest.importers import ImportedNote
from .deps import current_user
from .import_sources import _queue, _reject_if_busy
from .schemas import IngestOut

router = APIRouter(prefix="/api/connectors/memoket", tags=["connectors"])


class ReadIn(BaseModel):
    tool: str
    arguments: dict = Field(default_factory=dict)


class ImportIn(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")
    title: str = Field(min_length=1, max_length=200)
    to: Literal["notes", "both", "kb"] = "notes"


@router.get("/status")
def status(user: str = Depends(current_user)):
    return memoket.status()


@router.post("/read")
def read(body: ReadIn, user: str = Depends(current_user)):
    try:
        return memoket.read(body.tool, body.arguments)
    except memoket.ConnectorError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/import", response_model=IngestOut)
def import_recording(body: ImportIn, bg: BackgroundTasks, user: str = Depends(current_user)):
    _reject_if_busy(user)
    if not body.title.strip():
        raise HTTPException(422, "A recording title is required")
    try:
        content = memoket.brief_snapshot(body.conversation_id)
    except memoket.ConnectorError as exc:
        raise HTTPException(502, str(exc)) from exc
    note = ImportedNote(title=body.title.strip(), content=content, source="memoket",
                        source_id=body.conversation_id, icon="bx-microphone")
    return _queue(user, [note], body.to, bg)
