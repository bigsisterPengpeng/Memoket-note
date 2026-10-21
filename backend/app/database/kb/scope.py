"""Classify source identifiers into note, meeting, import and screen scopes."""

from __future__ import annotations

SCOPES = ("all", "notes", "meetings", "imports", "screen")


SCOPE_LABEL = {"all": 'All (excluding screen)', "notes": 'Notes only', "meetings": 'Meeting records only',
               "imports": 'Imports only', "screen": 'Screen activity only'}
_IMPORT_PREFIXES = ("obsidian-", "notion-", "feishu-", "apple-", "evernote-", "md-", "import-", "file-")


def classify(unit: str) -> str:
    u = unit or ""
    if u.startswith("note-"):
        return "notes"
    if u.startswith(_IMPORT_PREFIXES):
        return "imports"


    if u.startswith("screen-"):
        return "screen"
    return "meetings"


def filter_rows(rows: list[dict], scope: str) -> list[dict]:
    if scope not in SCOPES or scope in ("", "all"):
        return [r for r in rows if classify(r.get("unit") or "") != "screen"]
    return [r for r in rows if classify(r.get("unit") or "") == scope]
