"""Deterministic last gate before a long-form run may say "complete".

The LLM judge evaluates prose quality, but it has repeatedly returned all
twos for drafts that still end in an empty heading or literally say that a
piece of evidence must be added. Those are not subtle quality judgements:
the document itself declares that work remains. Keep that truth outside the
model so a polished-looking score cannot turn an unfinished draft into a
successful delivery.
"""

from __future__ import annotations

import re


_PENDING = re.compile(
    '(?:\u8fd9\u91cc|\u6b64\u5904|\u8fd9\u4e00\u8282|\u672c\u8282)?(?:\u4ecd|\u8fd8|\u5c1a)?(?<!\u4e0d)(?<!\u65e0\u9700)(?<!\u4e0d\u518d)\u9700\u8981\u8865\u4e0a|[\uff08(]\\s*(?:\u65e5\u671f\u5f85\u8865|date pending)\\s*[\uff09)]|^\\s*(?:[-*+]\\s*)?(?:\u5f85\u8865|\u5c1a\u7f3a|\u672a\u5199|\u5f85\u5199)(?:\u5145)?\\s*[\uff1a:]|^\\s*(?:[-*+]\\s*)?(?:TODO|TBD|FIXME|TO ADD|MISSING|PLACEHOLDER)\\b\\s*[:\uff1a-]?',
    re.M | re.I,
)
_PENDING_BEAT = re.compile(
    '^\\s*(?:\u5f85\u8865|\u5c1a\u7f3a|\u672a\u5199|\u5f85\u5199)(?:\u5145)?\\s*[\uff1a:]|^\\s*(?:TODO|TBD|FIXME|TO ADD|MISSING|PLACEHOLDER)\\b\\s*[:\uff1a-]?',
    re.I,
)
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(\S.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def unfinished_reasons(content: str, beats: list[str] | None = None) -> list[str]:
    """Return short user-facing reasons why a long-form draft is unfinished."""
    reasons: list[str] = []
    text = content or ""
    if _PENDING.search(text):
        reasons.append("The text contains explicit missing-material placeholders")

    empty = _empty_headings(text)
    if empty:
        examples = "、".join(empty[:2])
        reasons.append(f"{len(empty)} empty sections ({examples})")

    pending_beats = [b for b in (beats or []) if _PENDING_BEAT.match(b)]
    if pending_beats:
        reasons.append(f"The writing plan has {len(pending_beats)} uncovered items")
    return reasons


def _empty_headings(content: str) -> list[str]:
    """Markdown headings with no prose/list/code content before the next one."""
    lines = content.splitlines()
    headings: list[tuple[int, int, str]] = []
    fenced = False
    fence_mark = ""
    for i, line in enumerate(lines):
        mark = _FENCE.match(line)
        if mark:
            token = mark.group(1)
            if not fenced:
                fenced, fence_mark = True, token[0]
            elif token.startswith(fence_mark):
                fenced, fence_mark = False, ""
            continue
        heading = _HEADING.match(line) if not fenced else None
        if heading:
            headings.append((i, len(heading.group(1)), heading.group(2).strip()))

    out: list[str] = []
    for n, (start, level, title) in enumerate(headings):
        # A document title followed by a populated H2 is not empty. A heading
        # ends only at the next heading of the same or a higher level; nested
        # subheadings belong to its section.
        end = len(lines)
        for next_start, next_level, _next_title in headings[n + 1:]:
            if next_level <= level:
                end = next_start
                break
        body = [line.strip() for line in lines[start + 1:end]
                if line.strip()
                and not line.lstrip().startswith("<!--")
                and not _HEADING.match(line)]
        if not body:
            out.append(title)
    return out
