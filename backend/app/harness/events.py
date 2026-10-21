"""Streaming writing events and payload helpers shared by all writing modes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """AG-UI standard event names. Domain-specific things go through CUSTOM."""

    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"

    STEP_STARTED = "STEP_STARTED"          # one round, or one section
    STEP_FINISHED = "STEP_FINISHED"

    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"

    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"
    ACTIVITY_SNAPSHOT = "ACTIVITY_SNAPSHOT"   # "looking things up...", "drawing..."

    CUSTOM = "CUSTOM"                          # {name, value}


# Domain events ride on CUSTOM's ``name`` field rather than becoming
# top-level types. The frontend then needs one branch for CUSTOM instead of
# one branch per domain concept, and adding a harness costs it nothing.
CUSTOM_EVALUATE = "evaluate"
CUSTOM_REVISION = "revision"
CUSTOM_DROPPED = "dropped"          # a revision the guards rejected
CUSTOM_SCRUB = "scrub"              # a whole sentence the server removed mid-round; client mirrors it
CUSTOM_DEDUP = "dedup"              # a paragraph / heading line the server dropped from this round's streamed text (repeat / model-written heading); client mirrors it
CUSTOM_CHECK_HIT = "check_hit"      # a deterministic Check fired
CUSTOM_POLICY = "policy"            # runtime policy / replan / plan extended
CUSTOM_WARNING = "warning"          # one middleware failed, run continues
CUSTOM_SKELETON = "skeleton"
CUSTOM_PHASE_DELTA = "phase_delta"   # live output from a sub-step
CUSTOM_ROUND = "round_summary"       # what this round gathered, before writing
CUSTOM_REPLAN = "replan"             # the skeleton changed mid-run
CUSTOM_INSERT_AT = "insert_at"       # this round's text goes into a section, not the end
CUSTOM_COST = "cost"
CUSTOM_CROSS_RUN = "cross_run"


CUSTOM_SKILLS = "skills"


@dataclass(frozen=True)
class Event:
    """One SSE event. ``type`` is an AG-UI name; ``data`` is its payload."""

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)

    # -- constructors -------------------------------------------------
    # The loop and middleware use these instead of hand-building dicts, so
    # payload shapes stay consistent and the frontend can generate types
    # from one place.

    @staticmethod
    def run_started(mode_key: str, label: str) -> "Event":
        return Event(EventType.RUN_STARTED, {"mode": mode_key, "label": label})

    @staticmethod
    def run_finished(content: str, reason: str, blocked_reason: str = "",
                     run_id: str = "") -> "Event":
        data = {"content": content, "reason": reason}
        if run_id:
            # A paused run. The client sends this back to /resume together
            # with what the user kept.
            data["run_id"] = run_id
        if blocked_reason:
            # "blocked" on its own tells the user nothing. The scorer wrote a
            # sentence about what the structural conflict is; carry it.
            data["blocked_reason"] = blocked_reason
        return Event(EventType.RUN_FINISHED, data)

    @staticmethod
    def run_error(message: str) -> "Event":
        return Event(EventType.RUN_ERROR, {"message": message[:500]})

    @staticmethod
    def step_started(step: int, label: str = "") -> "Event":
        return Event(EventType.STEP_STARTED, {"step": step, "label": label})

    @staticmethod
    def step_finished(step: int, content: str = "") -> "Event":
        return Event(EventType.STEP_FINISHED, {"step": step, "content": content})

    @staticmethod
    def text_start(message_id: str) -> "Event":
        return Event(EventType.TEXT_MESSAGE_START, {"messageId": message_id})

    @staticmethod
    def text_content(message_id: str, delta: str) -> "Event":
        return Event(EventType.TEXT_MESSAGE_CONTENT,
                     {"messageId": message_id, "delta": delta})

    @staticmethod
    def text_end(message_id: str) -> "Event":
        return Event(EventType.TEXT_MESSAGE_END, {"messageId": message_id})

    @staticmethod
    def tool_result(name: str, args: dict, result: str) -> "Event":
        return Event(EventType.TOOL_CALL_RESULT,
                     {"toolName": name, "args": args, "content": result[:400]})

    @staticmethod
    def activity(label: str) -> "Event":
        return Event(EventType.ACTIVITY_SNAPSHOT, {"content": label})

    @staticmethod
    def custom(name: str, value: dict) -> "Event":
        return Event(EventType.CUSTOM, {"name": name, "value": value})


def sse(event: str, data: dict) -> str:
    import json

    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def to_sse(event: Event) -> str:
    return sse(event.type.value, event.data)
