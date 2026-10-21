"""Shared request dependencies and user-scoped service construction for API routes."""

from collections.abc import AsyncIterator

import re

from fastapi import Header, HTTPException
from fastapi.responses import StreamingResponse

from ..util import i18n


def sse_response(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


_USER_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def current_user(x_user_id: str = Header(default="default")) -> str:
    uid = (x_user_id or "default").strip() or "default"
    if not _USER_ID.match(uid) or uid in (".", ".."):
        raise HTTPException(400, i18n.msg("user id may only contain letters, digits, _ . - (max 64)"))
    return uid
