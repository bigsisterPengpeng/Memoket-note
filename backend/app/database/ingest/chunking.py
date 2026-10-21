"""Splitting text into chunks for extraction.

Lived in ``routers/ingest.py`` and was imported from ``routers/import_sources``
-- a router reaching into another router, which is how "just this one small
function" turns into a dependency graph nobody can draw.

On the strategy itself: fixed-size splitting keeps winning benchmarks over
semantic splitting (a 2026 comparison had recursive 512-token at 69% versus
semantic at 54%, the latter producing 43-token fragments that retrieved
cleanly and gave the model too little to work with). So the size is a knob,
not a placeholder for something cleverer.
"""

from __future__ import annotations

import re

CHUNK_CHARS = 1200


def chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split on paragraph boundaries, trying not to cut mid-sentence."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    out: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 1 > size and buf:
            out.append(buf)
            buf = para
        else:
            buf = f"{buf}\n{para}" if buf else para
    if buf:
        out.append(buf)
    return out


def markdown_sections(text: str) -> list[str]:
    """Split on heading lines, so a chunk stays inside one section."""
    sections: list[str] = []
    buf: list[str] = []
    for line in text.split("\n"):
        if re.match(r"^#{1,6}\s", line) and buf:
            sections.append("\n".join(buf).strip())
            buf = [line]
        else:
            buf.append(line)
    if buf:
        sections.append("\n".join(buf).strip())
    return [s for s in sections if s]


def chunks_for(text: str, kind: str, size: int = CHUNK_CHARS) -> list[str]:
    """Markdown gets split by heading first, then by size within each section."""
    if kind == "md":
        out: list[str] = []
        for section in markdown_sections(text):
            out.extend(chunks(section, size))
        return out or chunks(text, size)
    return chunks(text, size)
