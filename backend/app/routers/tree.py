"""Note-tree routes, branch operations and read-only knowledge-tree navigation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..database import store
from .deps import current_user
from .schemas import BranchAttachIn, BranchExpandIn, BranchMoveIn, BranchReorderIn, TreeRow

router = APIRouter(prefix="/api/tree", tags=["tree"])


@router.get("", response_model=list[TreeRow])
def get_tree(user: str = Depends(current_user)):
    return store.tree(user)


@router.post("/branches", response_model=TreeRow)
def attach(body: BranchAttachIn, user: str = Depends(current_user)):
    if not store.get_note(user, body.note_id):
        raise HTTPException(404, 'Note not found')
    if body.parent_note_id != store.ROOT_ID and \
            not store.get_note(user, body.parent_note_id):
        raise HTTPException(404, 'Parent node not found')
    if body.note_id == body.parent_note_id:
        raise HTTPException(400, 'A note cannot be its own parent')
    try:
        store.attach(user, body.note_id, body.parent_note_id)
    except ValueError as exc:
        raise HTTPException(400, f'Could not clone note: {exc}')
    row = next((r for r in store.tree(user)
                if r["note_id"] == body.note_id
                and r["parent_note_id"] == body.parent_note_id), None)
    if not row:
        raise HTTPException(500, 'The attached note could not be read back')
    return row


@router.delete("/branches")
def detach(note_id: str, parent_note_id: str, user: str = Depends(current_user)):
    if not store.detach(user, note_id, parent_note_id):
        raise HTTPException(
            400, "This is the note's last position in the tree. Use Delete note to delete it.")
    return {"detached": note_id, "from": parent_note_id}


@router.patch("/branches/reorder")
def reorder(body: BranchReorderIn, user: str = Depends(current_user)):
    return {"parent": body.parent_note_id,
            "count": store.reorder(user, body.parent_note_id, body.order)}


@router.patch("/branches/move")
def move(body: BranchMoveIn, user: str = Depends(current_user)):
    if body.to_parent_id != store.ROOT_ID and not store.get_note(user, body.to_parent_id):
        raise HTTPException(404, 'Target parent node not found')
    ok = store.move_branch(user, body.note_id, body.from_parent_id,
                           body.to_parent_id, body.position)
    if not ok:
        raise HTTPException(400, 'Cannot move a note into its own subtree')
    return {"moved": body.note_id, "to": body.to_parent_id}


@router.patch("/branches/expanded")
def set_expanded(body: BranchExpandIn, user: str = Depends(current_user)):
    store.set_expanded(user, body.note_id, body.parent_note_id, body.expanded)
    return {"note_id": body.note_id, "expanded": body.expanded}


@router.get("/paths/{note_id}")
def paths(note_id: str, user: str = Depends(current_user)) -> list[list[str]]:
    if not store.get_note(user, note_id):
        raise HTTPException(404, 'Note not found')
    return store.note_paths(user, note_id)
