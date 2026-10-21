"""Note-side incremental import (docs/import-sync-plan.md section 3): import the same thing ten times and the notes still have one;
a source-side change updates the body; a local change is left alone. Knowledge-base side: if the content changed, delete the old session first, then re-extract."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import store  # noqa: E402
from app.database.ingest import importers  # noqa: E402
from app.database.kite.kite_memory import UserMemory  # noqa: E402
from app.routers import import_sources  # noqa: E402


@pytest.fixture()
def iso(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")
    fake = SimpleNamespace(kite_data_dir=tmp_path, kite_extract_model="fake", whisper_base_url="http://x")
    monkeypatch.setattr(import_sources, "get_settings", lambda: fake)
    return tmp_path


def _note(content='\u7b2c\u4e00\u7248\u6b63\u6587\u3002', title='\u5468\u4f1a'):
    return importers.ImportedNote(title=title, content=content, date="2026-03-10", source="obsidian", source_id="vault/a.md")


def _run(notes, to="notes"):
    job_id, items = store.create_batch_job("u1", [{"filename": n.title, "kind": n.source} for n in notes])
    import_sources._land("u1", notes, to, job_id, items)
    return store.get_items(job_id)


def test_reimport_same_content_does_not_duplicate(iso):
    _run([_note()])
    _run([_note()])
    notes = [n for n in store.list_notes("u1") if n["title"] == '\u5468\u4f1a']
    assert len(notes) == 1 and notes[0]["source"] == "obsidian" and notes[0]["source_sha"]
    assert 'unchanged' in _run([_note()])[0]["detail"]


def test_source_changed_updates_note_unless_locally_modified(iso):
    _run([_note()])
    n = [x for x in store.list_notes("u1") if x["title"] == '\u5468\u4f1a'][0]
    items = _run([_note('\u7b2c\u4e8c\u7248\u6b63\u6587\u3002')])
    assert 'updated' in items[0]["detail"]
    assert store.get_note("u1", n["id"])["content"] == '\u7b2c\u4e8c\u7248\u6b63\u6587\u3002'
    # changed locally (updated_at newer than imported_at) -> not overwritten
    with store.connect() as c:
        c.execute("UPDATE notes SET updated_at='2099-01-01T00:00:00+00:00' WHERE id=?", (n["id"],))
    items = _run([_note('\u7b2c\u4e09\u7248\u6b63\u6587\u3002')])
    assert "local content changed" in items[0]["detail"]
    assert store.get_note("u1", n["id"])["content"] == '\u7b2c\u4e8c\u7248\u6b63\u6587\u3002'
    assert len([x for x in store.list_notes("u1") if x["title"] == '\u5468\u4f1a']) == 1


def test_kb_side_reextracts_only_when_content_changed(iso, monkeypatch):
    removed: list[str] = []
    calls: list[str] = []
    monkeypatch.setattr(UserMemory, "remember", lambda self, m, *, session_id, date=None, title="", profile=None: calls.append(session_id) or 1)
    monkeypatch.setattr(UserMemory, "remove_sessions", lambda self, prefix, keep_suffix="-manual": removed.append(prefix) or 1)
    _run([_note()], to="both")
    assert removed == [] and len(calls) == 1
    _run([_note()], to="both")             # unchanged: nothing deleted; KITE skips by id itself (the fake remember records it again here, which does not matter)
    assert removed == []
    _run([_note('\u6539\u4e86\u7684\u6b63\u6587\u3002')], to="both")
    assert removed == ["obsidian-vault/a.md-"]
