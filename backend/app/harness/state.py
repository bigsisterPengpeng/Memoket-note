"""Everything one run carries.

**One State per run.** That is the whole answer to concurrency (R9): several
`/` commands can run against the same note at once, each with its own State,
and nothing crosses over.

It is also the answer to a bug that shipped four times: "the accumulated
thing" and "the per-round thing" used to both be locals in one giant
generator, distinguished only by indentation, so it was easy to reset the
wrong one. Here the accumulated things are fields on an object created
outside the loop -- the mistake is no longer expressible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .types import Evaluation

if TYPE_CHECKING:                       # pragma: no cover
    from fastapi import Request

    from .agent_loop import ToolTrace
    from .tools import ToolContext
    from .types import Mode


COVERAGE_DIMS = ("beat_coverage", "section_coverage", "material_use")


@dataclass
class State:
    """Read by everything, written only by the loop and by middleware.

    ``Check`` gets a State but must treat it as read-only -- that's what makes
    checks unit-testable and keeps "what changed the content" answerable by
    looking in one place.
    """

    mode: "Mode"
    ctx: "ToolContext"                  # user · note · content · cursor
    request: "Request | None" = None    # for is_disconnected(); None in tests

    round: int = 0
    before: str = ""                    # text before the cursor (block) / whole note
    after: str = ""

    content: str = ""                   # current output
    fresh: str = ""                     # what this round produced

    # Material. ``facts_new`` is this round's raw haul; ``facts`` is the
    # accumulated-and-trimmed set. Keeping both is deliberate: the Facts
    # middleware needs the delta to know whether the round was dry.
    facts_new: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    charts: list[str] = field(default_factory=list)   # mermaid the tools actually produced
    trace: "ToolTrace | None" = None

    # Skills: bodies injected by scope match *plus* whatever the model loaded
    # via load_skill. Kept across rounds -- otherwise an 8-round run would
    # make the model re-load the same skill 8 times.
    skill_bodies: list[str] = field(default_factory=list)
    skill_menu: list[tuple[str, str]] = field(default_factory=list)

    ev: Evaluation | None = None
    skip_judge: bool = False            # a Check already failed it; don't pay for scoring
    best: tuple[tuple[int, float], str] | None = None


    best_ev: Evaluation | None = None

    # Why the run ended, set by the loop just before commit. Middleware needs
    # it: recording a paused run in the history as "finished" would teach the
    # next run the wrong lesson.
    stopped: str = ""

    bag: dict[str, Any] = field(default_factory=dict)   # middleware scratch space

    def rank(self) -> tuple[int, float]:
        """Collapse multi-dimensional scores into something comparable.

        Deterministic on purpose -- picking which round to ship must not cost
        another model call. Dimensions that meet the bar first, then the mean.

        A round that never got scored (a Check short-circuited it) ranks
        below everything, which is correct: it is known-unfit.
        """
        if not self.ev:
            return (-1, -1.0)
        levels = [s.level for s in self.ev.scores.values()]
        if not levels:
            return (-1, -1.0)
        return (sum(1 for v in levels if v >= 2), sum(levels) / len(levels))

    def coverage_unmet(self) -> bool:
        return any((s := self.ev.scores.get(d)) and s.level < 2
                   for d in COVERAGE_DIMS) if self.ev else False

    @property
    def steer(self) -> str:
        dim = str(self.bag.get("focus") or "")
        note = str(self.bag.get("focus_note") or "")
        return f"{dim}: {note}" if dim and note else ""

    def content_for_continue(self) -> str:
        """What the continuation prompt should see.

        Defaults to the full content; the ``Compact`` middleware overwrites
        this via ``bag`` for long-form harnesses. Revision and scoring always
        read the *full* content -- they hunt for drift and repetition across
        the whole piece, and compacting hides exactly what they're looking for.
        """
        return self.bag.get("content_for_continue") or self.content
