'Regression tests for verify cited.'

from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import store
from app.routers import compose


def test_cited_near_takes_the_paragraph_of_the_selection():
    content = '\u5f00\u5934 [u-1-A1]\u3002\n\n4\u670816\u65e5\u7684EVT\u51c6\u59074\u53f0\u4e3b\u673a [u-2-B2] [u-2-B3]\u3002\u540e\u534a\u53e5\u3002\n\n\u7ed3\u5c3e [u-3-C3]\u3002'
    assert compose._cited_near(content, '4\u670816\u65e5\u7684EVT\u51c6\u59074\u53f0\u4e3b\u673a') == ["u-2-B2", "u-2-B3"]
    assert compose._cited_near(content, '\u4e0d\u5728\u6b63\u6587\u91cc\u7684\u9009\u533a [u-9-F9]') == ["u-9-F9"]


def test_verify_feeds_cited_facts_first(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")
    facts = {"u-2-B2": {"id": "u-2-B2", "text": 'EVT \u51c6\u5907 4 \u53f0\u4e3b\u673a\uff0c15 \u5957 PCBA', "when": "2026-04-16"}}

    class FakeMem:
        def __init__(self, user): pass
        def fact_by_id(self, fid): return facts.get(fid)
        def recall(self, q, limit=8, scope="all"): return ([{"id": "u-7-X1", "text": '\u65e0\u5173\u7684\u4e00\u6761', "date": ""}], [], 0.1)
        def source_lines(self, row): return ['\u539f\u8bdd']
    monkeypatch.setattr(compose, "UserMemory", FakeMem)
    seen = {}

    async def fake_complete(messages, **kw):
        seen["user"] = messages[-1]["content"]
        return '[{"verdict":"\u652f\u6301","reason":"\u77e5\u8bc6\u5e93 4 \u6708 16 \u65e5\u8bb0\u4e86\u540c\u6837\u7684\u6570","fact_index":0}]'
    monkeypatch.setattr(compose.llm, "complete", fake_complete)
    from app.main import app
    with TestClient(app, headers={"X-User-Id": "u1"}) as c:
        content = '\u524d\u6587\u3002\n\n4\u670816\u65e5\u7684EVT\u51c6\u59074\u53f0\u4e3b\u673a\u548c15\u5957PCBA [u-2-B2]\u3002\n\n\u540e\u6587\u3002'
        r = c.post("/api/verify", json={"content": content, "selection": '4\u670816\u65e5\u7684EVT\u51c6\u59074\u53f0\u4e3b\u673a\u548c15\u5957PCBA'}).json()
    assert '[0] EVT \u51c6\u5907 4 \u53f0\u4e3b\u673a' in seen["user"] and '[1] \u65e0\u5173\u7684\u4e00\u6761' in seen["user"]
    assert r["findings"][0]["fact_id"] == "u-2-B2" and r["findings"][0]["sources"] == ['\u539f\u8bdd']
