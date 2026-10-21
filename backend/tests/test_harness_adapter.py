'Regression tests for harness adapter.'

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import store
from app.harness import adapter as harness_adapter
from app.util import llm# noqa: E402
from app.harness.types import RunRecord  # noqa: E402


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_db_path", lambda: tmp_path / "notes.sqlite3")
    return store


@pytest.mark.anyio
async def test_app_llm_client_forwards_to_app_llm_complete(monkeypatch):
    captured = {}

    async def fake_complete(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return "the response"

    monkeypatch.setattr(llm, "complete", fake_complete)
    client = harness_adapter.AppLLMClient()
    result = await client.complete([{"role": "user", "content": "hi"}], max_tokens=42)
    assert result == "the response"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["kwargs"] == {"max_tokens": 42}


@pytest.mark.anyio
async def test_judge_client_uses_the_independent_judge_config(monkeypatch):
    captured = {}
    judge = {"base_url": "http://judge.test/v1", "api_key": "j-key",
             "model": "judge-model", "provider": "judge", "independent": True}

    async def fake_complete(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return "judged"

    monkeypatch.setattr(store, "get_active_judge_config", lambda: judge)
    monkeypatch.setattr(llm, "complete", fake_complete)

    result = await harness_adapter.AppJudgeLLMClient().complete(
        [{"role": "user", "content": "score this"}], max_tokens=99)

    assert result == "judged"
    assert captured["kwargs"] == {"config": judge, "max_tokens": 99}


def test_judge_config_falls_back_to_the_writer_when_unconfigured(monkeypatch):
    from app.util.config import Settings

    writer = {"base_url": "http://writer.test/v1", "api_key": "w-key",
              "model": "writer-model", "provider": "local"}
    monkeypatch.setattr(store, "get_settings", lambda: Settings(
        judge_base_url="", judge_model=""))
    monkeypatch.setattr(store, "get_active_llm_config", lambda: writer)

    assert store.get_active_judge_config() == {**writer, "independent": False}


def test_sqlite_run_history_store_round_trips(isolated_store):
    hist = harness_adapter.SqliteRunHistoryStore()
    hist.record(RunRecord(
        key="note-1", status="complete", rounds=3,
        final_scores={"spine_fidelity": 2, "non_repetition": 1},
        weak_dimensions=["non_repetition"],
    ))
    recent = hist.recent("note-1", limit=3)
    assert len(recent) == 1
    assert recent[0].status == "complete"
    assert recent[0].rounds == 3
    assert recent[0].final_scores == {"spine_fidelity": 2, "non_repetition": 1}
    assert recent[0].weak_dimensions == ["non_repetition"]


def test_sqlite_run_history_store_scoped_by_key(isolated_store):
    hist = harness_adapter.SqliteRunHistoryStore()
    hist.record(RunRecord(key="note-1", status="complete", rounds=1,
                          final_scores={}, weak_dimensions=[]))
    hist.record(RunRecord(key="note-2", status="complete", rounds=1,
                          final_scores={}, weak_dimensions=[]))
    assert len(hist.recent("note-1")) == 1
    assert len(hist.recent("note-3")) == 0


def test_sqlite_run_history_store_orders_most_recent_first(isolated_store):
    hist = harness_adapter.SqliteRunHistoryStore()
    for i in range(3):
        hist.record(RunRecord(key="note-1", status="complete", rounds=i,
                              final_scores={}, weak_dimensions=[]))
    recent = hist.recent("note-1", limit=2)
    assert len(recent) == 2
    assert recent[0].rounds == 2  # most recently inserted
