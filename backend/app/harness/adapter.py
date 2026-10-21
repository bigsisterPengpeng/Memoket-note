"""Translate writing requests into mode-independent harness state and event streams."""

from __future__ import annotations

from .types import RunRecord

from ..util import llm as _llm
from ..database import store


class AppLLMClient:
    """Implements harness.types.LLMClient by forwarding to app.llm.complete()."""

    async def complete(self, messages: list[dict], **kwargs) -> str:
        return await _llm.complete(messages, **kwargs)


class AppJudgeLLMClient:
    async def complete(self, messages: list[dict], **kwargs) -> str:
        return await _llm.complete(messages, config=store.get_active_judge_config(), **kwargs)


class SqliteRunHistoryStore:
    """Implements harness.types.RunHistoryStore over app/store.py's
    harness_runs table."""

    def record(self, run: RunRecord) -> None:
        store.record_harness_run(
            run.key, run.status, run.rounds, run.final_scores, run.weak_dimensions,
            stopped=run.stopped, run_id=run.run_id,
            tokens=run.tokens, calls=run.calls)

    def recent(self, key: str, limit: int = 3) -> list[RunRecord]:
        return [
            RunRecord(
                key=row["key"], status=row["status"], rounds=row["rounds"],
                final_scores=row["final_scores"], weak_dimensions=row["weak_dimensions"],
                timestamp=row["timestamp"], stopped=row.get("stopped", ""),
            )
            for row in store.recent_harness_runs(key, limit)
        ]
