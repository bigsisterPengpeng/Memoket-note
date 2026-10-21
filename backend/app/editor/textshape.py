"""Normalize generated text shape before it enters the editor."""

from __future__ import annotations

import re


_LEADING = re.compile(r"^[ \t]*(?:#{1,6}[ \t]+|>[ \t]?|[-*+][ \t]+|\d+[.)][ \t]+)")
_FENCE = re.compile(r"^[ \t]*(?:`{3,}|~{3,})")

_INLINE = re.compile(r"\*\*|__|[*_`~]|\[|\]\([^)]*\)")

_TABLE_SEP = re.compile(r"^[ \t]*\|[\s:|-]+\|[ \t]*$")


def plain_text(md: str) -> str:
    out: list[str] = []
    in_code = False
    for line in (md or "").splitlines():
        if _FENCE.match(line):
            in_code = not in_code
            continue
        if in_code:
            out.append(line)
            continue
        if _TABLE_SEP.match(line):
            continue
        s = _LEADING.sub("", line)
        s = s.replace("|", " ")
        s = _INLINE.sub("", s)
        out.append(s)
    text = "\n".join(out)


    text = re.sub(r"[（(]\s*\d{1,2}\s*[）)]|[①-⑳]", "", text)
    return re.sub(r"[\s、；;，,。．.：:！!？?]+", "", text)


def _headings(md: str) -> str:
    out = []
    in_code = False
    for line in (md or "").splitlines():
        if _FENCE.match(line):
            in_code = not in_code
            continue
        if not in_code and re.match(r"^[ \t]*#{1,6}[ \t]+", line):
            out.append(_LEADING.sub("", line))
    return re.sub(r"[\s、；;，,。．.：:！!？?]+", "", "".join(out))


def content_drift(before: str, after: str, *, sample: int = 3) -> str:
    a, b = plain_text(before), plain_text(after)
    if a == b:
        return ""

    import difflib

    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    lost: list[str] = []
    added: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace") and i2 > i1:
            lost.append(a[i1:i2][:60])
        if tag in ("insert", "replace") and j2 > j1:
            added.append(b[j1:j2][:60])


    if not lost and added:
        heads = _headings(after)
        if all(chunk in heads for chunk in added):
            return ""
    parts = []
    if lost:
        parts.append('Deleted or rewritten: ' + "；".join(lost[:sample]))
    if added:
        parts.append('Added without a source: ' + "；".join(added[:sample]))
    return ('This round changed content, but restructuring may only change heading levels, lists, quotations and paragraph boundaries. Do not add or remove wording.' + " ".join(parts)
            + ' Preserve every sentence exactly and change only its structure.')
