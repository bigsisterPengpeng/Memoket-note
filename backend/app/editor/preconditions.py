"""Shared preconditions for note and block actions; API and UI contracts use the same cases."""

from __future__ import annotations


EMPTY_NOTE: dict[str, str] = {
    "skeleton": 'Write some content (or a title) before generating an outline',
    "tap": 'Write some content (or a title) before continuing',
    "harness": 'Write a title or a few sentences so Smart Continue has something to build on',
    "polish": 'The note is empty — nothing to polish',
    "restructure": 'The note is empty — nothing to restructure',
    "slides": 'This note has no body yet — nothing to turn into slides',
    "ingest": 'The note is empty — write something before saving it to the knowledge base',
}


_BODY_ONLY = {"polish", "restructure", "slides", "ingest"}


def note_precondition(action: str, content: str, title: str = "") -> str:
    if action not in EMPTY_NOTE:
        return ""
    has_body = bool((content or "").strip())
    has_title = bool((title or "").strip()) and action not in _BODY_ONLY
    if has_body or has_title:
        return ""
    return EMPTY_NOTE[action]
