"""User writing preferences and memory-derived profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..database import store
from .schemas import ProfileEntry, ProfileEntryIn
from .deps import current_user

router = APIRouter(prefix="/api/profile", tags=["profile"])


MAX_CHARS = 400


@router.get("", response_model=list[ProfileEntry])
def list_profile(user: str = Depends(current_user)):
    return store.list_profile(user)


@router.post("", response_model=ProfileEntry)
def add_profile(body: ProfileEntryIn, user: str = Depends(current_user)):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "content is empty")
    if len(text) > MAX_CHARS:
        raise HTTPException(400, f'Each preference must not exceed {MAX_CHARS} characters. Split it into smaller preferences or save a note to the knowledge base.')

    for e in store.list_profile(user):
        if e["text"] == text:
            return e
    return store.add_profile_entry(user, text)


@router.delete("/{entry_id}")
def delete_profile(entry_id: str, user: str = Depends(current_user)):
    if not store.delete_profile_entry(user, entry_id):
        raise HTTPException(404, "entry not found")
    return {"ok": True}
