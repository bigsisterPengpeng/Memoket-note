"""Pure-logic regression tests of batch import: chunking, format extraction, job/item status aggregation.

No LLM/ASR - remember() itself is verified elsewhere (the concurrent write-lock test); only the parts new to
the batch flow are tested here: splitting markdown by heading, pdf/docx/txt extraction, and the aggregation
rules of store.update_job_from_items() (because they decide when the frontend progress bar goes from running
to done/error/cancelled).

    cd backend && python -m pytest tests/test_batch_ingest.py -v
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import store
from app.database.ingest import extract# noqa: E402
from app.database.kite.kite_memory import UserMemory  # noqa: E402
from app.routers import ingest  # noqa: E402
# Chunking moved to app/chunking.py - routers should not import each other, and import_sources used
# to take these functions from ingest.
from app.database.ingest.chunking import chunks_for as _chunks_for  # noqa: E402
from app.database.ingest.chunking import markdown_sections as _markdown_sections  # noqa: E402


# ---------------------------------------------------------------- chunking

def test_markdown_sections_split_on_headings():
    text = "intro line\n# A\nbody a\n## A.1\nbody a1\n# B\nbody b"
    sections = _markdown_sections(text)
    assert sections == [
        "intro line",
        "# A\nbody a",
        "## A.1\nbody a1",
        "# B\nbody b",
    ]


def test_chunks_for_md_keeps_sections_separate():
    text = "# A\nshort a\n# B\nshort b"
    chunks = _chunks_for(text, "md", size=1200)
    # the two headings become separate sections and are not merged into one chunk
    assert chunks == ["# A\nshort a", "# B\nshort b"]


def test_chunks_for_txt_falls_back_to_paragraph_chunking():
    text = "para one\npara two"
    assert _chunks_for(text, "txt", size=1200) == ["para one\npara two"]


def test_chunks_for_md_without_headings_still_chunks():
    # an md file with no headings at all: _markdown_sections yields one section, which still goes
    # through _chunks
    text = "just prose, no heading at all here"
    assert _chunks_for(text, "md", size=1200) == [text]


# ---------------------------------------------------------------- format extraction

def test_kind_for_recognizes_supported_extensions():
    assert extract.kind_for("report.PDF") == "pdf"
    assert extract.kind_for("notes.docx") == "docx"
    assert extract.kind_for("a.md") == "md"
    assert extract.kind_for("a.markdown") == "md"
    assert extract.kind_for("voice.m4a") == "audio"


def test_kind_for_rejects_unknown_extension():
    with pytest.raises(extract.UnsupportedFileType):
        extract.kind_for("virus.exe")


def test_extract_text_txt_and_md_decode_utf8():
    assert extract.extract_text('\u4f60\u597d'.encode(), "a.txt") == '\u4f60\u597d'
    assert extract.extract_text(b"# T\nbody", "a.md") == "# T\nbody"


def test_extract_text_txt_decodes_utf8_bom():
    assert extract.extract_text('\u4f60\u597d'.encode("utf-8-sig"), "a.txt") == '\u4f60\u597d'


def test_extract_text_txt_falls_back_to_gb18030():
    # Old Chinese txt files (novels especially) are commonly encoded not in UTF-8 but GBK/GB2312 -
    # GB18030 is their superset and decodes them compatibly. This used to decode as UTF-8
    # unconditionally, so GBK files turned into garbage sent to the LLM, which naturally could not
    # extract a single fact (hit for real: a GBK-encoded novel txt, dozens of chunks, all 0 facts).
    text = '\u8fd9\u662f\u4e00\u6bb5\u6d4b\u8bd5\u6587\u5b57\uff0c\u91cc\u9762\u6709\u4e54\u5cf0\u3001\u6bb5\u8a89\u3001\u865a\u7af9\u3002'
    assert extract.extract_text(text.encode("gb18030"), "novel.txt") == text


def test_extract_text_txt_gbk_bytes_are_not_silently_mangled():
    """Not testing "can it be read", but "does a wrong read still look like Chinese" - GBK bytes decoded as UTF-8 by
    mistake raise no error, they just produce garbage; that case must be caught by the GB18030 path, not reach
    the final errors='replace' fallback."""
    text = '\u91d1\u5eb8\u7684\u5929\u9f99\u516b\u90e8\u91cc\u6709\u4e54\u5cf0\u3001\u6bb5\u8a89\u3001\u865a\u7af9\u3002'
    gbk_bytes = text.encode("gbk")
    result = extract.extract_text(gbk_bytes, "novel.txt")
    assert result == text
    assert "�" not in result  # no replacement characters from falling through to the replace fallback


def test_extract_text_docx_reads_paragraphs():
    from docx import Document

    doc = Document()
    doc.add_paragraph("first paragraph")
    doc.add_paragraph("second paragraph")
    buf = io.BytesIO()
    doc.save(buf)

    text = extract.extract_text(buf.getvalue(), "notes.docx")
    assert "first paragraph" in text
    assert "second paragraph" in text


def test_extract_text_pdf_reads_page_text():
    import fitz

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "hello from pdf")
    data = pdf.tobytes()
    pdf.close()

    text = extract.extract_text(data, "report.pdf")
    assert "hello from pdf" in text
    assert "[p1]" in text


def test_extract_text_audio_is_not_a_document():
    with pytest.raises(extract.UnsupportedFileType):
        extract.extract_text(b"RIFF....", "clip.wav")


# ---------------------------------------------------------------- job/item aggregation

@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    """Put the store's sqlite under tmp_path so tests do not interfere with each other."""
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")
    return store


def test_batch_job_aggregates_to_running_while_items_pending(isolated_store):
    job_id, items = isolated_store.create_batch_job(
        "u1", [{"filename": "a.txt", "kind": "txt"},
               {"filename": "b.txt", "kind": "txt"}])
    isolated_store.set_item(items[0]["id"], "done", facts=3)
    isolated_store.update_job_from_items(job_id)

    job = isolated_store.get_job(job_id)
    assert job["status"] == "running"  # b.txt is still queued
    assert job["facts"] == 3


def test_batch_job_done_when_all_items_done(isolated_store):
    job_id, items = isolated_store.create_batch_job(
        "u1", [{"filename": "a.txt", "kind": "txt"},
               {"filename": "b.txt", "kind": "txt"}])
    isolated_store.set_item(items[0]["id"], "done", facts=3)
    isolated_store.set_item(items[1]["id"], "done", facts=5)
    isolated_store.update_job_from_items(job_id)

    assert isolated_store.get_job(job_id)["status"] == "done"
    assert isolated_store.get_job(job_id)["facts"] == 8


def test_batch_job_errors_if_any_item_fails_even_if_others_done(isolated_store):
    """One failed file does not bring down the whole batch - but the job's aggregate status must let the frontend see "something is wrong"."""
    job_id, items = isolated_store.create_batch_job(
        "u1", [{"filename": "a.txt", "kind": "txt"},
               {"filename": "b.pdf", "kind": "pdf"}])
    isolated_store.set_item(items[0]["id"], "done", facts=3)
    isolated_store.set_item(items[1]["id"], "failed", detail="corrupt pdf")
    isolated_store.update_job_from_items(job_id)

    job = isolated_store.get_job(job_id)
    assert job["status"] == "error"
    assert job["facts"] == 3  # the successful one is not dragged down by the failed one
    assert "corrupt pdf" in job["detail"]


def test_batch_job_cancelled_when_all_items_cancelled(isolated_store):
    job_id, items = isolated_store.create_batch_job(
        "u1", [{"filename": "a.txt", "kind": "txt"}])
    isolated_store.set_item(items[0]["id"], "cancelled")
    isolated_store.update_job_from_items(job_id)

    assert isolated_store.get_job(job_id)["status"] == "cancelled"


def test_cancel_flag_roundtrip(isolated_store):
    job_id = isolated_store.create_job("u1")
    assert isolated_store.is_cancel_requested(job_id) is False
    isolated_store.request_cancel(job_id)
    assert isolated_store.is_cancel_requested(job_id) is True


# ---------------------------------------------------------------- incremental progress
#
# Extraction runs per chunk, one independent LLM call per chunk (~13s). User feedback: "show it
# during extraction, not all at once after extraction finishes" - these two tests lock in exactly
# that behaviour: the fact count must rise as each chunk finishes, not jump once after all chunks
# are done. The real remember() is not touched (it would call the LLM); a fake that adds a fixed +2
# each time is used.

def _fake_remember_plus_two(monkeypatch):
    monkeypatch.setattr(UserMemory, "remember", lambda self, *a, **kw: 2)


def _long_paragraph(tag: str) -> str:
    # a single paragraph must reach about CHUNK_CHARS (1200) of _chunks(), so three of them together
    # necessarily exceed one chunk's limit, forcing at least 2 remember() calls.
    return f"{tag} " + ('\u5185\u5bb9 ' * 220)


def test_ingest_job_reports_facts_incrementally_across_chunks(isolated_store, monkeypatch):
    _fake_remember_plus_two(monkeypatch)
    seen_facts: list[int] = []
    real_set_job = store.set_job

    def spy_set_job(job_id, status, facts=0, detail=""):
        seen_facts.append(facts)
        real_set_job(job_id, status, facts=facts, detail=detail)
    monkeypatch.setattr(store, "set_job", spy_set_job)

    text = "\n\n".join(_long_paragraph(t) for t in ("A", "B", "C"))
    assert len(ingest._chunks(text)) >= 2  # sanity: the fixture text really is multi-chunk

    job_id = store.create_job("u1")
    ingest._ingest_job(job_id, "u1", text, "t", "doc")

    # every chunk's completion is its own store write, not one write at the end
    assert len(seen_facts) >= 2
    # and the count actually climbs chunk by chunk, not just at the final write
    assert seen_facts == sorted(seen_facts)
    assert seen_facts[0] < seen_facts[-1]


def test_batch_job_reports_item_facts_incrementally_across_chunks(isolated_store, monkeypatch):
    _fake_remember_plus_two(monkeypatch)
    text = "\n\n".join(_long_paragraph(t) for t in ("A", "B", "C"))
    assert len(ingest._chunks_for(text, "txt")) >= 2

    job_id, items = store.create_batch_job("u1", [{"filename": "a.txt", "kind": "txt"}])
    item_id = items[0]["id"]
    seen_facts: list[int] = []
    real_set_item = store.set_item

    def spy_set_item(item_id_, status, facts=0, detail="", **kw):
        if item_id_ == item_id:
            seen_facts.append(facts)
        real_set_item(item_id_, status, facts=facts, detail=detail, **kw)
    monkeypatch.setattr(store, "set_item", spy_set_item)

    ingest._batch_job(job_id, "u1", items, {item_id: text.encode()}, "auto")

    # "remembering" gets written once per chunk (plus the terminal "done") --
    # if this were only 1, the fix regressed back to "one jump at the end".
    remembering_facts = seen_facts[:-1]  # last entry is the terminal "done" write
    assert len(remembering_facts) >= 2
    assert remembering_facts[0] < remembering_facts[-1]
