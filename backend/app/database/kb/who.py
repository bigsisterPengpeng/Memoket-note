"""Normalize speaker names and recognize synthetic speaker tags."""

from __future__ import annotations

import re

_WS = re.compile(r"[\s_]+")


def norm_who(who: str) -> str:
    return _WS.sub(" ", (who or "").strip()).lower()


_SPEAKER_TAG = re.compile('^(speaker(?:[\\s_-][a-z]|[\\s_-]?\\d{1,2})|\u8bf4\u8bdd\u4eba(?:\\s?[a-z]|\\s?\\d{1,2})|\u53d1\u8a00\u4eba(?:\\s?[a-z]|\\s?\\d{1,2}))$', re.I)


def is_speaker_tag(name: str) -> bool:
    return bool(_SPEAKER_TAG.match((name or "").strip()))
