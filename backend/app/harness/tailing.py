"""Bound continuation after token limits and reject fragments that do not form a safe continuation."""
from __future__ import annotations

import re


_SENTENCE_TAIL = set(".。！？!?…；;：:」』）】》”’")
_CJK = re.compile('[\u4e00-\u9fff\u3040-\u30ff]')


def needs_tail(text: str) -> bool:
    t = (text or "").rstrip()
    if not t:
        return False
    if t.count("```") % 2 == 1:
        return True
    if t.endswith("```") or t.endswith("~~~"):
        return False
    last_line = t.rsplit("\n", 1)[-1].strip()
    if last_line.startswith("|") and last_line.endswith("|"):
        return False
    if last_line.startswith("#"):
        return False
    return t[-1] not in _SENTENCE_TAIL


def acceptable_tail(text: str, tail: str) -> bool:
    t = (tail or "").strip()
    if not t:
        return False


    if _CJK.search((text or "")[-30:]) and not _CJK.search(t):
        if not any(ch in _SENTENCE_TAIL for ch in t):
            return False
    return True
