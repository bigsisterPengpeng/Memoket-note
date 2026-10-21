'Regression tests for rewrite truncated.'

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import store  # noqa: E402
from app.routers import compose  # noqa: E402


def _client(monkeypatch, tmp_path, text: str, finish_reason: str):
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")

    async def fake_complete(messages, *, max_tokens=0, temperature=0.0, effort="low", stats=None):
        if stats is not None:
            stats["finish_reason"] = finish_reason
        return text

    monkeypatch.setattr(compose.llm, "complete", fake_complete)
    monkeypatch.setattr(compose, "_retrieve", lambda *a, **k: ([], [], 0.0))
    from app.main import app
    return TestClient(app, headers={"X-User-Id": "u1"})


def test_rewrite_truncated_json_gives_note(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path, '{"text": "\u6539\u5230\u4e00\u534a\u5c31', "length") as c:
        r = c.post("/api/rewrite", json={"content": 'a \u9009\u4e2d b', "selection": '\u9009\u4e2d'}).json()
    assert r["revisions"] == []
    assert 'Select a shorter passage' in r["note"]


def test_rewrite_ok_has_empty_note(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path, '{"text": "\u6539\u597d\u4e86", "reason": "\u66f4\u987a"}', "stop") as c:
        r = c.post("/api/rewrite", json={"content": 'a \u9009\u4e2d b', "selection": '\u9009\u4e2d'}).json()
    assert len(r["revisions"]) == 1 and r["note"] == ""


def test_expand_truncated_json_gives_note(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path, '{"before": "\u8865\u5230\u4e00\u534a', "length") as c:
        r = c.post("/api/expand", json={"content": 'a \u9009\u4e2d b', "selection": '\u9009\u4e2d'}).json()
    assert r["revisions"] == [] and 'Select a shorter passage' in r["note"]
