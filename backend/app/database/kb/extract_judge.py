"""Evaluate extraction results against their supplied source text."""

from __future__ import annotations

import collections
from dataclasses import dataclass

from ...harness.checks.rubric import evaluate
from ...harness.types import Dimension, Evaluation

from ...harness import adapter as harness_adapter
from ..kite.kite_memory import UserMemory

# How much of the original conversation the judge sees. It has to see some --
# "is this self-contained" can be answered from the fact alone, but "is this
# the right topic" cannot -- and a whole transcript would cost more than the
# extraction it is checking.
SOURCE_CHARS = 6000

DIMENSIONS = (
    Dimension(
        "self_contained",
        'Pass: each fact stands alone with explicit people, subjects and dates or months. Use specific names rather than pronouns, and absolute dates rather than relative time.\nFail: understanding depends on missing context or unresolved relative time.'),
    Dimension(
        "topic_fit",
        'Pass: each fact uses the most relevant topic among the known topics.\nFail: the topic is unrelated, or the fact has no topic.'),
)


@dataclass(frozen=True)
class MeetingJudgement:
    meeting: str
    facts: int
    evaluation: Evaluation | None


async def judge_meeting(user: str, meeting_id: str) -> MeetingJudgement:
    """Judge one meeting's extraction. ``evaluation`` is None if it failed.

    Failure is not an error here: this runs after a successful extraction,
    and losing the judgement must not lose the facts.
    """
    store, _vocab = UserMemory(user)._index()
    facts = [f for f in store.facts.values() if getattr(f, "unit", "") == meeting_id]
    if not facts:
        return MeetingJudgement(meeting_id, 0, None)

    body = "\n".join(f"- [{','.join(f.topics)}] {f.text}" for f in facts)
    source = "".join(line.text or "" for line in store.lines.values()
                     if line.unit == meeting_id)
    try:
        evaluation = await evaluate(
            harness_adapter.AppLLMClient(), content=body,
            dimensions=list(DIMENSIONS),
            context={'Original conversation': source[:SOURCE_CHARS]})
    except Exception:                                  # noqa: BLE001


        return MeetingJudgement(meeting_id, len(facts), None)
    return MeetingJudgement(meeting_id, len(facts), evaluation)


async def judge_sample(user: str, limit: int = 5) -> dict:
    """Judge the biggest few extractions and aggregate.

    Biggest first because a meeting that produced three facts says little
    about the prompt either way -- what is being measured is the extraction
    rules, and they show themselves on the meetings that had material.
    """
    store, _vocab = UserMemory(user)._index()
    per_unit: dict[str, int] = collections.Counter(
        getattr(f, "unit", "") for f in store.facts.values())
    meetings = [m for m, _n in per_unit.most_common(max(1, min(limit, 50))) if m]

    results = [await judge_meeting(user, m) for m in meetings]
    scored = [r for r in results if r.evaluation]
    per_dim: dict[str, list[int]] = collections.defaultdict(list)
    for r in scored:
        for name, score in r.evaluation.scores.items():
            per_dim[name].append(score.level)

    return {
        "meetings": len(results),
        "judged": len(scored),
        "dimensions": {
            name: {"mean": round(sum(v) / len(v), 2),
                   "below_bar": sum(1 for x in v if x < 2)}
            for name, v in per_dim.items()
        },
        "details": [
            {"meeting": r.meeting, "facts": r.facts,
             "scores": {n: {"level": s.level, "note": s.note[:300]}
                        for n, s in r.evaluation.scores.items()}}
            for r in scored
        ],
    }
