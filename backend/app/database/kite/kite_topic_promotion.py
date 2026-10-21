"""Promote supported candidate topics using source-linked facts and the engine vocabulary."""

from __future__ import annotations

import re
import warnings
from typing import Callable

_DATE = re.compile(r"(\d{4})-(\d{2})")
_EMPTY_USE = re.compile(r'<use unit="([^"]+)" bucket=""\s*/>')
_SESSION_ID = re.compile(r'<session id="([^"]+)"')


def time_bucket(date: str | None) -> str:
    m = _DATE.match(str(date or ""))
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def settle(vocab, unit_date: Callable[[str], str]) -> tuple[int, list[str]]:
    filled = 0
    for topic in vocab.topics.values():
        for unit, bucket in list(topic.usage.items()):
            if bucket:
                continue
            b = time_bucket(unit_date(unit))
            if b:
                topic.usage[unit] = b
                filled += 1
    return filled, vocab.promotion_pass()


def needs_settle(xml_text: str) -> bool:
    empty = set(_EMPTY_USE.findall(xml_text))
    if not empty:
        return False
    return not empty.isdisjoint(_SESSION_ID.findall(xml_text))


def _wrap(extract_facts):
    def extract_facts_with_promotion(vocabulary, session, *args, **kwargs):
        if isinstance(session, dict) and not session.get("bucket"):
            session["bucket"] = time_bucket(session.get("date"))
        facts = extract_facts(vocabulary, session, *args, **kwargs)
        vocabulary.promotion_pass()
        return facts

    extract_facts_with_promotion._memoket_promotes_topics = True
    return extract_facts_with_promotion


def install() -> None:
    import memoket_kite.memory as _memory

    current = getattr(_memory, "extract_facts", None)
    if current is None:
        warnings.warn(
            'kite_topic_promotion: memoket_kite.memory.extract_facts is unavailable. Topic promotion is not connected; newly ingested topics will remain candidates.',
            stacklevel=2,
        )
        return
    if getattr(current, "_memoket_promotes_topics", False):
        return
    _memory.extract_facts = _wrap(current)
