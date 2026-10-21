"""Render explicitly selected note, import and excerpt materials for a writing run."""

from __future__ import annotations

from typing import Iterable

KINDS = ("note", "fact", "import", "selection")


PLACEHOLDER_TITLES = frozenset({"", '\u672a\u547d\u540d', "Untitled", "note"})
TITLE_FALLBACK_MAX = 24


def display_title(title: str, excerpt: str) -> str:
    t = " ".join((title or "").split())
    if t not in PLACEHOLDER_TITLES:
        return t
    first = next((ln.strip().lstrip("#").strip() for ln in (excerpt or "").splitlines() if ln.strip()), "")
    if not first:
        return "Untitled"
    for i, ch in enumerate(first):
        if ch in "。！？；，,：:" and i >= (2 if ch in "。！？" else 8):
            first = first[:i]
            break
    return first[:TITLE_FALLBACK_MAX]


def lines_of(items: Iterable[dict] | None) -> list[str]:
    out: list[str] = []
    for it in items or ():
        kind = str((it or {}).get("kind") or "")
        ref = str(it.get("ref_id") or "").strip()
        title = " ".join(str(it.get("title") or "").split())
        excerpt = " ".join(str(it.get("excerpt") or "").split())
        if kind == "fact" and ref:
            when = f"[{title}] " if title and _looks_like_date(title) else ""
            line = f"[{ref}] {when}{excerpt}".rstrip()
        elif kind == "note" and ref:
            line = f"[Note: {display_title(title, str(it.get('excerpt') or ''))}](note://{ref}) {excerpt}".rstrip()
        elif kind == "import" and excerpt:
            line = f"[Import: {title}] {excerpt}" if title else f"[Import] {excerpt}"
        elif kind == "selection" and excerpt:
            line = f"[Excerpt] {excerpt}"
        else:
            continue
        if line not in out:
            out.append(line)
    return out


def _looks_like_date(s: str) -> bool:
    return len(s) >= 7 and s[:4].isdigit() and s[4] == "-"


def is_tray_line(line: str, tray: Iterable[str] | None) -> bool:
    return bool(tray) and line in set(tray)
