"""Validate model-proposed heading reorganizations against the existing note body."""

from __future__ import annotations

import re


_MARKER = re.compile(r"^[ \t]*(?:#{1,6}[ \t]+|>[ \t]?|[-*+][ \t]+|\d+[.)][ \t]+)")
_FENCE = re.compile(r"^[ \t]*(?:`{3,}|~{3,})")

OPS = ("heading", "list", "ordered", "quote", "paragraph", "insert_heading", "split")


_ENUM = re.compile(r"[（(]\s*(\d{1,2})\s*[）)]|([①-⑳])|"
                   r"(?:^|(?<=[。；;：:\s]))\s*(\d{1,2})\s*[、.]\s*(?=[^\d])")
MIN_SPLIT_ITEMS = 3
MAX_HEADING_CHARS = 40


MAX_HEADING_LINE = 60


_SENTENCE_END = re.compile(r"[。！？.!?]\s*$")
_PAUSES = re.compile(r"[，,；;]")


_PAREN = re.compile(r"[（(][^）)]*[）)]")


def looks_like_sentence(text: str) -> bool:
    core = _PAREN.sub("", text).strip()

    core = re.sub(r"^\d+\s*[.、)）]\s*", "", core)


    if len(core) > 12 and _SENTENCE_END.search(core):
        return True
    return len(_PAUSES.findall(core)) >= 2 and len(core) > MAX_HEADING_LINE // 2


def numbered(md: str) -> str:
    out = []
    in_code = False
    for i, line in enumerate(md.splitlines(), 1):
        if _FENCE.match(line):
            in_code = not in_code
            out.append(f"{i:>4}│ {line}    <- Code-block boundary; do not change")
            continue
        out.append(f"{i:>4}│ {line}" + ("    <- Inside a code block; do not change" if in_code else ""))
    return "\n".join(out)


def body(line: str) -> str:
    return _MARKER.sub("", line).strip()


def protected_lines(md: str) -> set[int]:
    out: set[int] = set()
    in_code = False
    for i, line in enumerate(md.splitlines(), 1):
        if _FENCE.match(line):
            in_code = not in_code
            out.add(i)
            continue
        if in_code or line.lstrip().startswith("|"):
            out.add(i)
    return out


def apply_ops(md: str, ops: list[dict]) -> tuple[str, list[str]]:
    lines = md.splitlines()
    protect = protected_lines(md)
    skipped: list[str] = []

    marks: dict[int, str] = {}
    splits: dict[int, str] = {}
    inserts: list[tuple[int, str]] = []

    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = str(op.get("op", "")).strip()
        if kind not in OPS:
            skipped.append(f'Unknown operation {kind!r}')
            continue
        if kind == "insert_heading":
            at = int(op.get("before", 0) or 0)
            text = str(op.get("text", "")).strip()
            level = max(1, min(6, int(op.get("level", 2) or 2)))
            if not text:
                skipped.append('insert_heading requires heading text')
                continue
            if len(text) > MAX_HEADING_CHARS:

                skipped.append(f'New heading is too long ({len(text)} characters); maximum {MAX_HEADING_CHARS} characters')
                continue
            if at < 1 or at > len(lines) + 1:
                skipped.append(f'insert_heading position {at} is out of range')
                continue
            inserts.append((at, "#" * level + " " + text))
            continue

        ln = int(op.get("line", 0) or 0)
        if ln < 1 or ln > len(lines):
            skipped.append(f'Line {ln} is out of range')
            continue
        if ln in protect:
            skipped.append(f'Line {ln} is inside a code block or table; unchanged')
            continue
        if not body(lines[ln - 1]):
            skipped.append(f'Line {ln} is empty; unchanged')
            continue
        if kind == "heading":
            text = body(lines[ln - 1])
            if len(text) > MAX_HEADING_LINE:
                skipped.append(f'Line {ln} has {len(text)} characters and is too long for a heading; unchanged')
                continue
            if looks_like_sentence(text):
                skipped.append(f'Line {ln} is a sentence rather than a heading; unchanged: {text[:24]}…')
                continue
            level = max(1, min(6, int(op.get("level", 2) or 2)))
            marks[ln] = "#" * level + " "
        elif kind == "list":
            level = max(0, min(4, int(op.get("indent", 0) or 0)))
            marks[ln] = "  " * level + "- "
        elif kind == "ordered":
            marks[ln] = "1. "
        elif kind == "quote":
            marks[ln] = "> "
        elif kind == "split":
            splits[ln] = "1. " if str(op.get("marker", "")) == "ordered" else "- "
        else:
            marks[ln] = ""

    out: list[str] = []
    for i, line in enumerate(lines):
        n = i + 1
        if n in splits:
            lead, items = split_enumerated(body(line))
            if items:

                if lead:
                    out.append(lead)
                out.extend((splits[n] + it) for it in items)
                continue
            skipped.append(f'Line {n} has fewer than {MIN_SPLIT_ITEMS} explicit numbered items; not split')
        out.append((marks[n] + body(line)) if n in marks else line)
    for at, text in sorted(inserts, key=lambda x: -x[0]):
        out.insert(at - 1, text)
    return "\n".join(out), skipped


def split_enumerated(text: str) -> tuple[str, list[str]]:
    marks = list(_ENUM.finditer(text))
    if len(marks) < MIN_SPLIT_ITEMS:
        return "", []

    nums = []
    for m in marks:
        g = m.group(1) or m.group(3)
        nums.append(int(g) if g else (ord(m.group(2)) - 0x2460 + 1))
    if nums != list(range(nums[0], nums[0] + len(nums))):
        return "", []
    out: list[str] = []
    lead = text[:marks[0].start()].strip()
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        piece = text[m.end():end].strip()
        if piece:
            out.append(piece)
    if len(out) < MIN_SPLIT_ITEMS:
        return "", []


    if len(lead) < 6:


        return "", ([lead + out[0]] + out[1:]) if lead else out
    return lead, out
