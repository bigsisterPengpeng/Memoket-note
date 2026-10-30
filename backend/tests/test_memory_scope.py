"""Source selection must survive retrieval caps and every writing-memory tool."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from app.database.kite.kite_memory import UserMemory
from app.database.kb.recall import recall_clustered
from app.harness.tools import ToolContext, memory_tools


def seed_memory(memory, *, distractors=14):
    root = ET.fromstring(memory.ensure().read_text())
    vocab = root.find("vocab")
    ET.SubElement(vocab, "topic", code="maple", status="canonical", parents="project")
    ET.SubElement(vocab, "topic", code="screen_only", status="canonical", parents="project")
    ET.SubElement(vocab, "entity", code="maple_team", name="Maple team", type="org")
    timeline = root.find("timeline")
    units = [
        ("note-maple-1", "2026-10-01", "Maple labels approved.", "maple"),
        ("note-maple-2", "2026-10-02", "The follow-up review is scheduled for Friday.", "maple"),
        ("md-maple-1", "2026-10-03", "Maple labels imported from a fictional vault.", "maple"),
        ("meeting-maple-1", "2026-10-04", "Maple labels reviewed in a fictional meeting.", "maple"),
    ]
    units += [(f"screen-maple-{i}", "2026-10-20", "Maple labels Maple labels Maple labels on a fictional screen.", "maple screen_only") for i in range(distractors)]
    units += [(f"meeting-birch-{i}", "2026-09-01", "The fictional Birch workshop uses blue envelopes.", "work") for i in range(200)]
    for uid, date, text, topic in units:
        session = ET.SubElement(timeline, "session", id=uid, date=date, title="Fictional Maple", dur="1m")
        ET.SubElement(session, "line", id=f"{uid}-L1", who="user").text = text
        ET.SubElement(session, "fact", id=f"{uid}-F1", t=date, kind="decision", conf="high", topics=topic, entities="maple_team", src=f"{uid}-L1").text = text
    ET.ElementTree(root).write(memory.path, encoding="utf-8", xml_declaration=True)
    memory.invalidate()
    return memory


@pytest.fixture()
def memory():
    return seed_memory(UserMemory("fictional-scope"))


@pytest.mark.parametrize("scope, expected", [
    ("all", {"note-maple-1-F1", "md-maple-1-F1", "meeting-maple-1-F1"}),
    ("notes", {"note-maple-1-F1"}),
    ("imports", {"md-maple-1-F1"}),
    ("meetings", {"meeting-maple-1-F1"}),
    ("screen", {f"screen-maple-{i}-F1" for i in range(14)}),
])
def test_keyword_scope_applies_before_ranking_cap(memory, scope, expected):
    rows, _, _ = memory.recall("Maple labels", limit=2, scope=scope, evidence=True)
    ids = {r["id"] for r in rows}
    assert ids and ids <= expected
    assert len(ids) == min(2, len(expected))


def test_cluster_expansion_keeps_scope_and_valid_followup(memory):
    rows, _, _ = recall_clustered(memory, "Maple labels", scope="notes", limit=5, evidence=True, entity_guard=True)
    assert {r["id"] for r in rows} == {"note-maple-1-F1", "note-maple-2-F1"}
    assert memory.fact_sources("note-maple-2-F1")[0]["text"] == "The follow-up review is scheduled for Friday."


def test_scope_with_no_matching_units_abstains(memory):
    rows, _, _ = memory.recall("Maple labels", scope="imports")
    assert rows
    memory.remove_sessions("md-")
    assert not memory.recall("Maple labels", scope="imports")[0]
    assert not recall_clustered(memory, "Maple labels", scope="imports")[0]


@pytest.mark.parametrize("tool, kwargs", [
    (memory_tools.search_memory, {"query": "Maple labels"}),
    (memory_tools.gather_subject, {"query": "Maple labels"}),
    (memory_tools.filter_facts, {"topic": "maple"}),
    (memory_tools.facts_in_range, {"date_from": "2026-10-01", "date_to": "2026-10-30"}),
])
def test_writing_tools_keep_selected_source(memory, tool, kwargs):
    result = tool(ToolContext(user=memory.user_id, scope="notes"), **kwargs)
    assert "note-maple-1-F1" in result
    assert "screen-maple" not in result and "md-maple" not in result and "meeting-maple" not in result


def test_full_library_browsing_still_includes_all_sources(memory):
    rows, total = memory.facts_page(limit=100)
    assert total == 218 and len(rows) == 100
    assert any(r["unit"].startswith("screen-") for r in rows)


@pytest.mark.parametrize("evidence", [False, True])
def test_allowed_fact_survives_a_full_candidate_pool(evidence):
    memory = seed_memory(UserMemory("fictional-large-scope"), distractors=820)
    rows, _, _ = memory.recall("Maple labels", limit=2, scope="notes", evidence=evidence)
    assert [r["id"] for r in rows] == ["note-maple-1-F1"]


def test_raw_line_fallback_cannot_select_an_excluded_source(memory):
    store, vocab = memory._index("notes")
    rows = memory._recall_via_lines(store, vocab, "Maple labels", 4)
    assert [r["id"] for r in rows] == ["note-maple-1-F1"]
    assert memory.source_lines(rows[0]) == ["Maple labels approved."]


def test_scoped_counts_pagination_sources_and_metadata(memory):
    rows, total = memory.facts_page(topic="maple", limit=1, offset=1, scope="notes")
    assert total == 2 and [r["id"] for r in rows] == ["note-maple-1-F1"]
    assert memory.fact_by_id("screen-maple-0-F1", scope="notes") is None
    assert not memory.fact_sources("screen-maple-0-F1", scope="notes")
    assert memory.fact_sources("screen-maple-0-F1", scope="screen")
    topics = {r["code"]: r["fact_count"] for r in memory.topics(scope="notes")}
    assert topics["maple"] == 2 and topics["screen_only"] == 0
    entities = {r["code"]: r["fact_count"] for r in memory.entities(scope="notes")}
    assert entities["maple_team"] == 2
    rows = memory.recall("Maple labels", scope="notes", evidence=True)[0]
    evidence = memory.recall_evidence("Maple labels", rows, scope="notes")
    assert next(e for e in evidence if e["term"] == "maple")["units"] == 1
    context = ToolContext(user=memory.user_id, scope="notes")
    assert "screen_only" not in memory_tools.list_topics(context)
    assert "2 facts" in memory_tools.list_entities(context)
    assert "fictional screen" in memory_tools.fact_sources(context, "screen-maple-0-F1")


def test_compiled_session_lookup_keeps_scope_through_stage_bindings(memory, monkeypatch):
    from types import SimpleNamespace
    from app.database.kite import kite_memory
    from memoket_kite.pipeline import compile_plan

    monkeypatch.setattr(kite_memory, "_export_provider_env", lambda: None)
    monkeypatch.setattr(kite_memory.Memory, "load", lambda *a, **k: SimpleNamespace(
        _reasoner=lambda: SimpleNamespace(_profile=SimpleNamespace())))
    def compile_question(question, vocab, kb, profile, model, **kwargs):
        assert set(kb.units) == {"note-maple-1", "note-maple-2"}
        if question == "Excluded unit":
            return {"queries": [{"select": "facts", "where": {"units": ["screen-maple-0"]}}]}
        return {"stages": [
            {"name": "anchor", "select": "facts", "where": {"grep": "labels"}},
            {"name": "rest", "select": "facts", "where": {"units": "$anchor.units"}},
        ]}
    monkeypatch.setattr(compile_plan, "compile_plan", compile_question)
    rows, multi, _ = memory.recall_multihop("Find related decisions", scope="notes")
    assert multi and {r["id"] for r in rows} == {"note-maple-1-F1"}
    assert not memory.recall_multihop("Excluded unit", scope="notes")[0]
    result = memory_tools.search_session_context(ToolContext(user=memory.user_id, scope="notes"), "Find related decisions")
    assert "note-maple-1-F1" in result and "screen-maple" not in result


def test_scope_views_invalidate_after_source_change(memory):
    assert len(memory.facts_page(scope="notes")[0]) == 2
    assert len(memory.facts_page(scope="screen")[0]) == 14
    memory.remove_sessions("note-maple-2")
    assert [r["id"] for r in memory.facts_page(scope="notes")[0]] == ["note-maple-1-F1"]
    assert len(memory.facts_page(scope="screen")[0]) == 14
    assert not UserMemory("another-fictional-user").recall("Maple labels")[0]


def test_unknown_scope_preserves_the_default_screen_exclusion(memory):
    known = memory.recall("Maple labels", scope="all")[0]
    unknown = memory.recall("Maple labels", scope="unrecognized")[0]
    assert known and unknown == known


def test_digest_filters_sources_before_its_date_range_cap(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routers import compose

    memory = seed_memory(UserMemory("fictional-digest"), distractors=405)
    root = ET.parse(memory.path)
    for session in root.getroot().find("timeline"):
        if session.get("id", "").startswith("note-"):
            session.set("date", "2026-10-28")
            for fact in session.findall("fact"):
                fact.set("t", "2026-10-28")
    root.write(memory.path, encoding="utf-8", xml_declaration=True)
    memory.invalidate()
    calls = []
    async def complete(messages, **kwargs):
        calls.append(messages)
        return "The fictional Maple team approved labels and scheduled a follow-up."
    monkeypatch.setattr(compose.llm, "complete", complete)
    response = TestClient(app).post("/api/digest", json={
        "date_from": "2026-10-01", "date_to": "2026-10-30", "scope": "notes"},
        headers={"X-User-Id": "fictional-digest"})
    assert response.status_code == 200
    assert response.json()["fact_count"] == 2
    assert len(calls) == 1
    assert "Maple labels approved." in calls[0][1]["content"]
    assert "fictional screen" not in calls[0][1]["content"]
