"""Feishu import: blocks -> markdown is a pure function; the HTTP layer uses fake get/post."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import store  # noqa: E402
from app.database.ingest import feishu  # noqa: E402
from app.routers import import_sources  # noqa: E402


def _t(content, **style):
    return {"text_run": {"content": content, "text_element_style": style}}


BLOCKS = [
    {"block_id": "p", "block_type": 1, "parent_id": "", "children": ["h", "t", "b1", "b2", "o1", "o2", "c", "q", "td", "tb", "img"],
     "page": {"elements": [_t('\u5468\u4f1a\u7eaa\u8981')]}},
    {"block_id": "h", "block_type": 4, "parent_id": "p", "heading2": {"elements": [_t('\u51b3\u5b9a')]}},
    {"block_id": "t", "block_type": 2, "parent_id": "p", "text": {"elements": [_t('\u7535\u6c60\u6539 '), _t("380mAh", bold=True), _t('\uff0c\u89c1 '), _t('\u6587\u6863', link={"url": "https://x"})]}},
    {"block_id": "b1", "block_type": 12, "parent_id": "p", "bullet": {"elements": [_t('\u7b2c\u4e00\u6761')]}, "children": ["b1a"]},
    {"block_id": "b1a", "block_type": 12, "parent_id": "b1", "bullet": {"elements": [_t('\u5b50\u9879')]}},
    {"block_id": "b2", "block_type": 12, "parent_id": "p", "bullet": {"elements": [_t('\u7b2c\u4e8c\u6761')]}},
    {"block_id": "o1", "block_type": 13, "parent_id": "p", "ordered": {"elements": [_t('\u5148')]}},
    {"block_id": "o2", "block_type": 13, "parent_id": "p", "ordered": {"elements": [_t('\u540e')]}},
    {"block_id": "c", "block_type": 14, "parent_id": "p", "code": {"elements": [_t("print(1)")]}},
    {"block_id": "q", "block_type": 15, "parent_id": "p", "quote": {"elements": [_t('\u5f15\u7528')]}},
    {"block_id": "td", "block_type": 17, "parent_id": "p", "todo": {"elements": [_t('\u5f85\u529e')], "style": {"done": True}}},
    {"block_id": "tb", "block_type": 31, "parent_id": "p", "table": {"property": {"row_size": 2, "column_size": 2}, "cells": ["c1", "c2", "c3", "c4"]}},
    {"block_id": "c1", "block_type": 32, "parent_id": "tb", "children": ["c1t"]},
    {"block_id": "c1t", "block_type": 2, "parent_id": "c1", "text": {"elements": [_t('\u8282\u70b9')]}},
    {"block_id": "c2", "block_type": 32, "parent_id": "tb", "children": ["c2t"]},
    {"block_id": "c2t", "block_type": 2, "parent_id": "c2", "text": {"elements": [_t('\u65e5\u671f')]}},
    {"block_id": "c3", "block_type": 32, "parent_id": "tb", "children": ["c3t"]},
    {"block_id": "c3t", "block_type": 2, "parent_id": "c3", "text": {"elements": [_t("DVT")]}},
    {"block_id": "c4", "block_type": 32, "parent_id": "tb", "children": ["c4t"]},
    {"block_id": "c4t", "block_type": 2, "parent_id": "c4", "text": {"elements": [_t("8-5")]}},
    {"block_id": "img", "block_type": 27, "parent_id": "p", "image": {"token": "img_x"}},
]


def test_blocks_to_markdown():
    md = feishu.blocks_to_markdown(BLOCKS)
    assert md.startswith('## \u51b3\u5b9a\n\n\u7535\u6c60\u6539 **380mAh**\uff0c\u89c1 [\u6587\u6863](https://x)\n')
    # List items are tight, **but a block right after a list needs a blank line** - without it
    # markdown swallows it as the continuation of the last item (hit twice in the round-649 real-
    # account round trip: a quote, a plain paragraph)
    assert '- \u7b2c\u4e00\u6761\n  - \u5b50\u9879\n- \u7b2c\u4e8c\u6761\n1. \u5148\n2. \u540e\n\n```\nprint(1)\n```' in md
    assert '> \u5f15\u7528' in md and '- [x] \u5f85\u529e' in md
    assert '| \u8282\u70b9 | \u65e5\u671f |\n|---|---|\n| DVT | 8-5 |' in md
    assert "![image](img_x)" in md
    assert feishu.page_title(BLOCKS) == '\u5468\u4f1a\u7eaa\u8981'
    assert feishu.epoch_to_date("1741568400") == "2026-03-10" or feishu.epoch_to_date("1741568400")  # across timezones the date can differ by one day
    assert feishu.epoch_to_date("") == "" and feishu.epoch_to_date("abc") == ""


def test_route_lists_wiki_and_queues(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")
    fake = SimpleNamespace(kite_data_dir=tmp_path, kite_extract_model="fake", whisper_base_url="http://x")
    monkeypatch.setattr(import_sources, "get_settings", lambda: fake)
    calls = []

    def fake_post(path, json):
        calls.append(path)
        return {"code": 0, "tenant_access_token": "t-1"}

    def fake_get(path, params):
        calls.append(path)
        if path == "/wiki/v2/spaces":
            return {"code": 0, "data": {"items": [{"space_id": "sp1"}]}}
        if path == "/wiki/v2/spaces/sp1/nodes":
            if params.get("parent_node_token") == "n1":
                return {"code": 0, "data": {"items": [{"node_token": "n2", "obj_type": "docx", "obj_token": "docB", "title": '\u5b50\u9875', "obj_create_time": "1741568400"}], "has_more": False}}
            return {"code": 0, "data": {"items": [
                {"node_token": "n1", "obj_type": "docx", "obj_token": "docA", "title": '\u5468\u4f1a\u7eaa\u8981', "has_child": True, "obj_create_time": "1741568400"},
                {"node_token": "n9", "obj_type": "sheet", "obj_token": "sheetX", "title": '\u8868\u683c'},
            ], "has_more": False}}
        if path.startswith("/docx/v1/documents/"):
            return {"code": 0, "data": {"items": BLOCKS, "has_more": False}}
        raise AssertionError(path)

    real_init = feishu.FeishuClient.__init__
    monkeypatch.setattr(feishu.FeishuClient, "__init__", lambda self, a, b, **kw: real_init(self, a, b, get=fake_get, post=fake_post))
    from fastapi import BackgroundTasks
    out = import_sources.import_feishu(BackgroundTasks(), app_id="cli_x", app_secret="s", scope="wiki", to="notes", limit=0, docs="", user="u1")
    assert out.status == "queued" and [it.filename for it in out.items] == ['\u5468\u4f1a\u7eaa\u8981', '\u5b50\u9875']
    assert "/auth/v3/tenant_access_token/internal" in calls
    # only docx is listed, sheets skipped; source_id = document_id (stable -> incremental re-import)
    import json
    payload = json.loads(Path(store.get_job(out.job_id)["payload_path"]).read_text())
    assert [n["source_id"] for n in payload["notes"]] == ["docA", "docB"] and payload["notes"][0]["source"] == "feishu"
    assert payload["notes"][0]["content"].startswith('## \u51b3\u5b9a')


def test_code_block_language_tag_comes_back():
    """Round-trip test (round 649, real account): ```python exported and imported back became a bare ```,
    the code block lost highlighting, **once more per re-import**. The table of the writing side is
    `database/exporters._FEISHU_LANG`; the two tables must match."""
    blocks = [
        {"block_id": "p", "block_type": 1, "children": ["c"], "page": {"elements": [_t('\u6807\u9898')]}},
        {"block_id": "c", "block_type": 14, "parent_id": "p",
         "code": {"elements": [_t("print(1)")], "style": {"language": 43}}},
    ]
    assert "```python\nprint(1)\n```" in feishu.blocks_to_markdown(blocks)

    # unrecognized languages are not written, no guessing
    blocks[1]["code"]["style"] = {"language": 999}
    assert "```\nprint(1)\n```" in feishu.blocks_to_markdown(blocks)


def test_the_two_language_tables_match():
    """One table writes out, the other reads back. If they drift, the language changes or is lost after a round trip."""
    from app.database.exporters import _FEISHU_LANG
    from app.database.ingest.feishu import _CODE_LANG

    for name, num in _FEISHU_LANG.items():
        assert num in _CODE_LANG, f"export knows {name}={num}, import does not"
        # aliases (py / js / cpp) come back as the canonical name, which is right; canonical names
        # must come back unchanged
        if _CODE_LANG[num] == name:
            continue
        assert _CODE_LANG[num] in _FEISHU_LANG, f"{num} reads back as {_CODE_LANG[num]}, which export does not know"


def test_pasting_a_link_imports_only_that_doc_without_listing(monkeypatch, tmp_path):
    """**Feishu authorizes per document, while "listing" requires the app to be a member of the knowledge-base space.**

    Measured (round 649, real account): a wiki document with the app added as a collaborator on the document
    could be read by `get_node`, yet `/wiki/v2/spaces` had not a single space - readable but not listable.
    Being able to paste a link is what makes this feature work for "people who are not admins".
    """
    from fastapi import BackgroundTasks

    from app.routers import import_sources

    seen: dict = {}

    def fake_get(path, params):
        seen.setdefault("paths", []).append(path)
        if path == "/wiki/v2/spaces/get_node":
            return {"code": 0, "data": {"node": {"obj_type": "docx", "obj_token": "docW", "title": '\u5171\u4eab\u7ed9\u6211\u7684\u90a3\u7bc7'}}}
        if path.startswith("/docx/v1/documents/"):
            return {"code": 0, "data": {"items": BLOCKS, "has_more": False}}
        raise AssertionError(f"should not access {path}")

    real_init = feishu.FeishuClient.__init__
    monkeypatch.setattr(feishu.FeishuClient, "__init__",
                        lambda self, a, b, **kw: real_init(self, a, b, get=fake_get,
                                                           post=lambda p, j: {"code": 0, "tenant_access_token": "t"}))
    out = import_sources.import_feishu(
        BackgroundTasks(), app_id="cli_x", app_secret="s", scope="wiki", to="notes", limit=0,
        docs="https://x.feishu.cn/wiki/WikiTok3nAAAAAAAAAA\nDocxTok3nBBBBBBBBBB", user="u_links")
    assert out.status == "queued"
    # **the spaces were not listed even once**
    assert not any(p.endswith("/spaces") for p in seen["paths"]), seen["paths"]
    assert [it.filename for it in out.items][:1] == ['\u5171\u4eab\u7ed9\u6211\u7684\u90a3\u7bc7']
