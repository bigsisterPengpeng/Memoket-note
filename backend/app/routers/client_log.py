"""Bounded client diagnostic logging for the local desktop application."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .deps import current_user

router = APIRouter(prefix="/api/client-log", tags=["client-log"])
log = logging.getLogger("client")


class ClientLogIn(BaseModel):
    level: str = "error"
    message: str
    stack: str = ""
    where: str = ""


@router.post("")
def client_log(body: ClientLogIn, user: str = Depends(current_user)) -> dict:
    text = f"[client:{body.level}] user={user} {body.where} {body.message}"
    if body.stack:
        text += "\n" + body.stack[:4000]
    print(text, flush=True)

    (log.error if body.level == "error" else log.warning if body.level == "warn" else log.info)(text)
    return {"ok": True}
