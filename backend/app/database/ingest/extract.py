"""Document text extraction: PDF / DOCX / TXT / MD -> plain text.

Batch ingestion (see routers/ingest.py) first uses the functions here to turn every format into
text, then goes through the same chunking + remember() flow as single-text ingestion.
"""

from __future__ import annotations

import io
from pathlib import Path

from ...util import i18n

# suffix -> internal kind; also the whitelist /api/ingest/batch accepts
EXT_KIND = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
    ".flac": "audio",
}


class UnsupportedFileType(ValueError):
    pass


def kind_for(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    kind = EXT_KIND.get(ext)
    if not kind:
        raise UnsupportedFileType(i18n.msg("Unsupported file type: {what}", what=ext or filename))
    return kind


def extract_text(data: bytes, filename: str) -> str:
    """Dispatch by filename suffix. Handles only documents (pdf/docx/txt/md); audio goes through asr.transcribe."""
    kind = kind_for(filename)
    if kind == "pdf":
        return _extract_pdf(data)
    if kind == "docx":
        return _extract_docx(data)
    if kind in ("txt", "md"):
        return _decode_text(data)
    raise UnsupportedFileType(i18n.msg("{kind} is not a document type; use ASR", kind=kind))


def _decode_text(data: bytes) -> str:
    """Decode strictly as UTF-8 first; if that fails try GB18030 (covers GBK/GB2312, the most common
    encoding of old Chinese txt files, especially novels circulated from old forums / resource
    sites); only if both fail fall back to UTF-8+replace, which at least does not blow up, though
    in that case the content is unreadable anyway.

    This used to decode unconditionally as UTF-8 - a GBK-encoded file came out as a pile of garbage
    (e.g. a short Chinese phrase decoded into "����"), and feeding that to LLM extraction naturally
    yielded not a single fact: the content was not unsuitable for extraction, the file was never
    read correctly in the first place, and what the model saw was not Chinese at all. Actually
    hit in practice: a GBK-encoded txt novel, dozens of chunks all returned 0 facts, and only at
    the end was the encoding found to be the problem.
    """
    try:
        return data.decode("utf-8-sig")  # also handles UTF-8 with a BOM
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("gb18030")
    except UnicodeDecodeError:
        pass
    return data.decode("utf-8", errors="replace")


def _extract_pdf(data: bytes) -> str:
    import fitz  # PyMuPDF

    parts: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            text = page.get_text().strip()
            if text:
                parts.append(f"[p{i + 1}]\n{text}")
    return "\n\n".join(parts)


def _extract_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
