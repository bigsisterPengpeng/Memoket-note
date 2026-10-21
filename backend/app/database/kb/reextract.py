"""Rebuild the writing codebook from the source one, and keep it caught up.

**Two codebooks, on purpose.** The library's own extraction prompt opens with
"Extract durable, atomic structured facts" -- built so an answer can be
recalled and located later. Writing wants the opposite: self-contained
statements that carry the cause and the constraint, with the several mentions
of one thing already merged and the speaker labels gone. Measured on the
original codebook, 16% of its 20k facts are unusable for writing outright and
most of the rest are still question-answering shaped.

So the writing facts go to ``{user}-rewrite`` and the original is never
touched. Nothing here writes to the source.

**A whole meeting at a time.** This matters more than the prompt change. On
ingestion a meeting is cut into ~1125-character chunks and each chunk is
extracted alone -- 201 meetings became 2429 chunks, a median of 7 per meeting
and up to 64. An extractor seeing a thousand characters cannot merge the
several mentions of one decision or attach the reason to it, because those
are usually in a different chunk. It can only produce fragments. Regrouping
by meeting is what lets it produce something a writer can use.

**Resumable because it has to be.** This ran as a batch script that was meant
to be stopped and inspected between batches, and it was: the writing codebook
sat unfinished with no ordinary way to catch it up. KITE refuses a duplicate
``session_id`` without spending a model call, so re-running is already free
and idempotent; what was missing was something that finds the gap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..kite.kite_memory import UserMemory


# what precedes it is the meeting.
_CHUNK_SUFFIX = re.compile(r"^(.*)-(\d+)$")

# Writing suffix. The source codebook for user U is U; its writing view is
# U-rewrite, and asking for the writing view of a writing view is a mistake
# worth catching rather than silently nesting.
WRITING_SUFFIX = "-rewrite"


@dataclass(frozen=True)
class Meeting:
    """One conversation, reassembled from its chunks."""

    id: str
    date: str
    messages: tuple[dict, ...]

    @property
    def chars(self) -> int:
        return sum(len(m.get("content", "")) for m in self.messages)


def writing_user(user: str) -> str:
    base = user[:-len(WRITING_SUFFIX)] if user.endswith(WRITING_SUFFIX) else user
    return base + WRITING_SUFFIX


def source_user(user: str) -> str:
    return user[:-len(WRITING_SUFFIX)] if user.endswith(WRITING_SUFFIX) else user


def meeting_of(unit_id: str) -> str:
    """Return the parent meeting id of a source chunk.

    Source chunk ids end in a chunk index. Writing-library ids must be compared
    directly because their final numeric component identifies the meeting.
    """
    m = _CHUNK_SUFFIX.match(unit_id)
    return m.group(1) if m else unit_id


def pending(user: str) -> list[str]:
    """Meeting ids in the source codebook that the writing one doesn't have."""
    src, dst = UserMemory(source_user(user)), UserMemory(writing_user(user))
    try:
        sstore, _ = src._index()
    except Exception:
        return []
    try:
        dstore, _ = dst._index()
        # Destination unit ids **are** meeting ids -- one meeting, one unit.
        # Do not run them through meeting_of(): see the note there.
        done = set(dstore.units)
    except Exception:
        done = set()
    seen: list[str] = []
    for unit in sstore.units.values():
        mid = meeting_of(unit.id)
        if mid not in done and mid not in seen:
            seen.append(mid)
    return seen


def meetings(user: str, ids: list[str]) -> list[Meeting]:
    """Reassemble the named meetings from the source codebook, in order."""
    src = UserMemory(source_user(user))
    sstore, _ = src._index()

    lines_by_unit: dict[str, list] = {}
    for line in sstore.lines.values():
        lines_by_unit.setdefault(line.unit, []).append(line)

    chunks: dict[str, list[tuple[int, object]]] = {}
    for unit in sstore.units.values():
        m = _CHUNK_SUFFIX.match(unit.id)
        mid = m.group(1) if m else unit.id
        chunks.setdefault(mid, []).append((int(m.group(2)) if m else 0, unit))

    wanted = [i for i in ids if i in chunks]
    out: list[Meeting] = []
    for mid in wanted:
        parts = sorted(chunks[mid], key=lambda p: p[0])
        messages, date = [], ""
        for _idx, unit in parts:
            date = date or (getattr(unit, "date", "") or "")
            for line in lines_by_unit.get(unit.id, []):
                text = (line.text or "").strip()
                if text:
                    messages.append({"role": "user",
                                     "name": line.who or "speaker",
                                     "content": text})
        if messages:
            out.append(Meeting(id=mid, date=date, messages=tuple(messages)))
    return out


def extract_one(user: str, meeting: Meeting) -> int:
    """Extract one meeting into the writing codebook. Returns facts written.

    Re-running on a meeting already there costs nothing: KITE rejects the
    duplicate session id before it reaches a model.
    """
    dst = UserMemory(writing_user(user))
    dst.ensure()
    return dst.remember(list(meeting.messages), session_id=meeting.id,
                        date=meeting.date or None, profile=_profile(user))


def _profile(user: str):
    """The writing-side extraction profile, or None to leave KITE's alone."""
    from ..kite.kite_profile import WritingProfile
    from memoket_kite import Memory

    src = UserMemory(source_user(user))
    store, vocab = src._index()
    base = Memory.load([str(src.path)])._reasoner()._profile
    return WritingProfile(base, store, vocab)
