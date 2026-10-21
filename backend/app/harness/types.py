"""Configuration and extension contracts for modes, hooks, middleware, checks, verdicts and stop conditions."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import (TYPE_CHECKING, AsyncIterator, Callable, Literal, Protocol,
                    runtime_checkable)


if TYPE_CHECKING:                       # pragma: no cover
    from ..agent_loop import ToolTrace
    from .events import Event
    from .state import State


class Hooks(Protocol):
    """The three things that genuinely differ between harnesses.

    Everything else -- accumulating facts, deduping, scoring, best-of,
    stopping -- is shared. If a fourth thing shows up here, stop and check
    whether it's really a hook or a middleware in disguise.

    **This is a contract, not an implementation.** The opposite of middleware:
    there, one written implementation is shared by every harness; here, every
    harness writes its own. That asymmetry is why middleware can default to
    on and hooks cannot -- an empty contract has no default to give.

    Implementations *may* still be shared. note_harness and writing_plan both
    fall back to keyword retrieval when the tool loop fails; if that turns out
    to be the only thing their ``prepare`` has in common, it belongs in one
    shared base rather than copied twice.
    """

    async def prepare(self, st: "State") -> tuple[list[str], "ToolTrace"]:
        """Gather material. Returns (facts found this round, tool trace).

        Accumulation and trimming are *not* this hook's job -- the ``Facts``
        middleware owns those, precisely so that no harness can accidentally
        do only half of it (that mistake shipped four separate times).
        """

    def produce(self, st: "State") -> AsyncIterator[str]:
        """Generate, streaming pieces, **and update ``st.content``**.

        Why updating content belongs here and not in the loop: the merge rule
        differs per harness.

          * block generation: ``st.content = <the new block>``  (replace)
          * long-form: ``st.content = join(st.content, <what was written>)``

        The loop only accumulates pieces into ``st.fresh`` (for events and the
        no-progress stop condition). Putting the merge in the loop would mean
        an ``if mode.xxx`` there, which is exactly what this design forbids.
        """

    async def commit(self, st: "State") -> None:
        """Finish the run. **Not per-round persistence** -- that's the ``Save``
        middleware. This is for run-level wrap-up, e.g. writing_plan updating
        its tracking note."""


class Middleware(Protocol):
    """A capability package. Implement the hooks you need, omit the rest.

    Hook names follow *our* loop's phases, not LangChain's ``before_model`` --
    their loop is model-centric, ours is produce-then-judge.

    **Two shapes are allowed**, decided by whether it emits events:

      * emits events -> ``async def hook(st) -> AsyncIterator[Event]`` (yield)
      * emits nothing -> ``async def hook(st) -> None`` (plain async def)

    ``_fire`` tells them apart with ``inspect.isasyncgen``. Without this, a
    middleware that emits nothing would be forced to write ``return; yield``
    just to become a generator.
    """

    name: str

    # lifecycle: once per run
    async def before_run(self, st: "State") -> AsyncIterator["Event"]: ...
    async def after_run(self, st: "State") -> AsyncIterator["Event"]: ...

    # lifecycle: once per round
    async def before_round(self, st: "State") -> AsyncIterator["Event"]: ...
    async def after_prepare(self, st: "State") -> AsyncIterator["Event"]: ...
    async def before_produce(self, st: "State") -> AsyncIterator["Event"]: ...
    async def after_produce(self, st: "State") -> AsyncIterator["Event"]: ...
    async def before_judge(self, st: "State") -> AsyncIterator["Event"]: ...
    async def after_judge(self, st: "State") -> AsyncIterator["Event"]: ...
    async def after_round(self, st: "State") -> AsyncIterator["Event"]: ...

    # interception: can call the handler more than once (retry), skip it
    # (short-circuit), or rewrite request/response around it
    async def wrap_prepare(self, st: "State", handler) -> tuple[list[str], "ToolTrace"]: ...
    def wrap_produce(self, st: "State", handler) -> AsyncIterator[str]: ...


@dataclass(frozen=True)
class Verdict:
    """What a ``Check`` says when it fires.

    ``fix`` is the linter's ``--fix``: when the repair is unambiguous and
    needs no semantic judgement, just do it. Heading depth is fixable (sink
    everything one level, text untouched); "too many subheadings" is not
    (which one to drop is a judgement call). That boundary was established by
    running both against real failing output, not by reasoning about it.
    """

    dimension: str                                  # which dimension to fail
    message: str                                    # what the model is told
    fix: Callable[[str], str] | None = None         # pure function, or None


    fix_done: Callable[[str], bool] | None = None


    fix_note: str = ""


    advisory: bool = False


# Code decides. Pure function, read-only, no I/O -- so it can be unit-tested
# by constructing a string, and so a Check can never be the thing that breaks
# a run.
Check = Callable[["State"], Verdict | None]

# Returns a stop reason, or None to keep going. Composable: the loop ORs a
# built-in set with Mode.stop_when (Vercel AI SDK's ``stopWhen`` shape).
StopCondition = Callable[["State"], str | None]


@dataclass(frozen=True)
class Mode:
    """Everything that makes one feature different from another.

    Must stay pure data: skills get layered on top at runtime by producing a
    modified copy, so a Mode can't hold anything only code could supply.
    """

    key: str
    label: str
    task: str = ""
    # Activity wording distinguishes writing, drawing and data analysis.
    verb: str = "Writing"

    # Tool authorisation. A ``group`` bundles tools by domain; ``exclude``
    # removes individual ones. If the same tool keeps getting excluded by
    # several Modes, the grouping is wrong -- fix the group, don't patch it
    # here (there's a test for that).
    groups: tuple[str, ...] = ("memory",)
    # A second gather round restricted to these groups, run only when the
    # first round produced nothing from them.
    # Measured: on a note containing a table, the model spent all three tool
    # iterations on list_tables / aggregate_table / correlate_columns. It
    # found every number and drew no chart, then wrote "the chart code was not
    # returned by the tools". The iteration budget is shared and exploration
    # naturally comes first, so charting is always the thing that gets
    # squeezed out. A dedicated round does not compete for that budget.
    focus_groups: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    # Judgement, two kinds. Both are the system's -- skills cannot touch them.
    dims: tuple[Dimension, ...] = ()
    checks: tuple[Check, ...] = ()

    # Which skill scope matches here. Empty means user skills never auto-inject
    # for this feature -- which is a bug waiting to happen, so a test asserts
    # every Mode fills it in.
    skill_scope: str = ""

    stop_when: tuple[StopCondition, ...] = ()
    extra_mw: tuple[Middleware, ...] = ()


    precheck: Callable[["State"], str | None] | None = None

    # Turning off a BASE capability has to be written down. Not because it is
    # never right, but because the four times a harness ended up missing one,
    # nobody had decided anything -- it was simply never wired in. A test
    # asserts this stays empty, so switching one off means arguing for it in
    # a pull request.
    rails_off: tuple[str, ...] = ()

    # Pause at the end of each round so the user can accept or reject what
    # was just written. Off by default and set per request, not per feature:
    # whether to review is the user's call, and the same person wants it on a
    # document that matters and off on a scratch note.
    review_each_round: bool = False
    max_rounds: int = 3
    fact_budget: int = 40             # how many accumulated facts to keep
    context_keep_last: int = 4000     # chars of content kept verbatim for continuation
    max_tokens: int = 1400


Status = Literal["continue", "complete", "blocked"]


@dataclass(frozen=True)
class Dimension:
    name: str
    guidance: str
    binary: bool = False


@dataclass(frozen=True)
class DimensionScore:
    """One dimension's result for one evaluate() call.

    ``level`` is 0 (insufficient) / 1 (partial) / 2 (meets the bar) -- coarse
    on purpose. A finer scale invites false precision from a single LLM call;
    three levels is enough to drive "what's weakest" without pretending the
    judgment is more exact than it is.
    """

    level: int
    note: str


@dataclass(frozen=True)
class Evaluation:
    """Result of one evaluate() call."""

    scores: dict[str, DimensionScore]
    status: Status
    weakest: str | None = None
    blocked_reason: str | None = None


@dataclass(frozen=True)
class DupHint:
    """One candidate near-duplicate pair found by find_repeats()."""

    a: str
    b: str
    similarity: float


@dataclass(frozen=True)
class RunRecord:
    """One completed (or abandoned) harness run, for RunHistoryStore."""

    key: str
    status: Status
    rounds: int
    final_scores: dict[str, int]
    weak_dimensions: list[str] = field(default_factory=list)
    timestamp: str = ""


    stopped: str = ""


    run_id: str = ""


    tokens: int = 0
    calls: int = 0


@runtime_checkable
class LLMClient(Protocol):
    """Anything that can turn a chat-style message list into text. Matches
    the common OpenAI-compatible `complete(messages, **kw) -> str` shape
    closely enough that most existing app-side LLM wrappers satisfy this
    with a one-line adapter, without this package caring which provider,
    auth scheme, or model is behind it."""

    async def complete(self, messages: list[dict], **kwargs) -> str: ...


@runtime_checkable
class RunHistoryStore(Protocol):
    """Persists completed runs and retrieves recent ones for a given key
    (whatever the host app's model of "same recurring task" is -- a note
    id, a user id, a task type -- this package doesn't prescribe it).
    Optional: callers that don't care about cross-run history simply never
    construct one."""

    def record(self, run: RunRecord) -> None: ...

    def recent(self, key: str, limit: int = 3) -> list[RunRecord]: ...
