"""Shared character-count rules used by storage, UI contracts and completion checks."""
from __future__ import annotations

import re

_CITE = re.compile(r"\[[A-Za-z][\w-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+\]")
_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", re.M)
_LINE_MARK = re.compile(r"^\s*(#{1,6}|[-*>+]|\d+\.)\s+", re.M)
_INLINE_MARK = re.compile(r"[*_`|~]")
_WS = re.compile(r"\s+")


def word_count(content: str) -> int:
    s = content or ""
    s = _IMG.sub("", s)
    s = _LINK.sub(r"\1", s)
    s = _CITE.sub("", s)
    s = _TABLE_SEP.sub("", s)
    s = _LINE_MARK.sub("", s)
    s = _INLINE_MARK.sub("", s)
    s = _WS.sub("", s)
    return len(s)
