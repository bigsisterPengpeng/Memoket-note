"""Execute bounded tool-call iterations and preserve evidence and trace metadata."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import query_cache
from . import tools
from ..util import llm


MAX_TOOL_ITERS = 2


MAX_CALLS_PER_ITER = 5


BARREN_STOP = 2


DEPTH_TOOLS = frozenset({"fact_sources", "filter_facts", "search_session_context"})
BREADTH_TOOLS = frozenset({"search_memory", "list_topics", "list_entities"})


FACT_TOOLS = frozenset({
    "search_memory", "filter_facts", "facts_in_range",
    "fact_sources", "search_session_context",
})


_SCOPED_PATTERNS = [
    r"\u90a3\u6b21", r"\u4e0a\u6b21", r"\u4e0a\u4e00\u6b21", r"\u5f53\u65f6", r"\u90a3\u573a", r"\u90a3\u5929", r"\u4e4b\u524d\u90a3",
    r"\u9664\u4e86.{0,12}\u8fd8", r"\u4f1a\u4e0a", r"\u8ba8\u8bba.{0,6}\u7684\u65f6\u5019", r"\u804a.{0,6}\u7684\u65f6\u5019",
    r"\b(?:that|last|previous)\s+(?:meeting|conversation|session|discussion|call|time|day)\b",
    r"\bduring\s+(?:the|that)\b.{0,60}\b(?:meeting|call|session)\b",
]
_SCOPED_RE = re.compile("|".join(_SCOPED_PATTERNS), re.I)


def is_scoped_question(text: str) -> bool:
    """Recognize questions anchored to a specific conversation or occasion."""
    return bool(_SCOPED_RE.search(text or ""))


@dataclass
class ToolTrace:
    """Accumulate tool results and execution metadata across retrieval steps."""

    calls: list[tuple[str, dict, str]] = field(default_factory=list)
    iters: int = 0
    truncated: bool = False
    error: str = ""


    barren_calls: int = 0
    stopped_barren: bool = False


    dropped_depth: int = 0


    stopped_all_dropped: bool = False


    reported: int = 0

    @property
    def used(self) -> bool:
        return bool(self.calls)

    def merge(self, other: "ToolTrace") -> None:
        """Merge every trace field so later steps retain errors and stopping signals."""
        self.calls += other.calls
        self.iters += other.iters
        self.barren_calls += other.barren_calls
        self.dropped_depth += other.dropped_depth
        self.truncated = self.truncated or other.truncated
        self.stopped_barren = self.stopped_barren or other.stopped_barren
        self.stopped_all_dropped = (self.stopped_all_dropped
                                    or other.stopped_all_dropped)

        self.error = self.error or other.error

    def summary(self) -> list[dict]:
        return [{"tool": n, "args": a, "result": r[:400]} for n, a, r in self.calls]

    def as_facts(self, limit: int = 12) -> list[str]:
        """Keep factual tool results with their metadata, excluding status text and topic lists."""
        out: list[str] = []
        meta_line = re.compile(r"^(?:\([^)]{0,160}\)|\uff08[^\uff09]{0,160}\uff09)$")
        for name, _args, result in self.calls:
            if name not in FACT_TOOLS:


                continue
            if not result or tools.is_tool_notice(result):
                continue
            last_fact: int | None = None
            for line in result.splitlines():
                line = line.strip()
                if not line or line.startswith('\u5171 ') or re.match(r"^\d+ facts total; returning \d+:", line):
                    continue


                if meta_line.match(line) and last_fact is not None:
                    out[last_fact] += " " + line
                    continue
                if len(out) >= limit:
                    return out
                out.append(line.lstrip("- ").strip())
                last_fact = len(out) - 1
        return out


_FACT_ID_RE = re.compile(r"^\[([\w.-]+)\]", re.M)


def fact_ids_in(trace_or_text) -> list[str]:
    text = trace_or_text
    if hasattr(trace_or_text, "calls"):
        text = "\n".join(r for _n, _a, r in trace_or_text.calls)
    seen: list[str] = []
    for m in _FACT_ID_RE.finditer(text or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def _parse_call(call: dict) -> tuple[str, str, str]:
    fn = call.get("function") or {}
    args = fn.get("arguments")
    if args is None:
        args = call.get("arguments")
    if not isinstance(args, str):
        args = json.dumps(args or {}, ensure_ascii=False)
    return (
        str(call.get("id") or ""),
        str(fn.get("name") or call.get("name") or ""),
        args,
    )


def _rebuild_call(call: dict, *, iteration: int, index: int) -> dict:
    cid, name, raw_args = _parse_call(call)
    return {"id": cid or f"tc_{iteration}_{index}",
            "type": "function",
            "function": {"name": name, "arguments": raw_args}}


def _cap_calls(calls: list[dict], iteration: int = 0) -> tuple[list[dict], bool, int]:
    per_tool: dict[str, int] = {}
    kept: list[dict] = []
    dropped_breadth = 0
    for call in calls:
        _cid, name, _args = _parse_call(call)
        if iteration >= 1 and name in BREADTH_TOOLS:
            dropped_breadth += 1
            continue
        tool = tools.get(name)
        cap = tool.max_calls_per_round if tool else 1
        if per_tool.get(name, 0) >= cap or len(kept) >= MAX_CALLS_PER_ITER:
            continue
        per_tool[name] = per_tool.get(name, 0) + 1
        kept.append(call)

    truncated = len(kept) < (len(calls) - dropped_breadth)
    return kept, truncated, dropped_breadth


async def gather_context(
    messages: list[dict],
    ctx: tools.ToolContext,
    *,
    groups: list[str] | None = None,
    max_iters: int = MAX_TOOL_ITERS,
    max_tokens: int = 700,
    temperature: float = 0.3,
    known_ids: set[str] | None = None,
) -> tuple[list[dict], ToolTrace]:
    """Execute selected tools within iteration, breadth and per-tool budgets."""
    trace = ToolTrace()
    spec = tools.specs(groups)
    if not spec:
        return [], trace

    convo = list(messages)
    extra: list[dict] = []
    seen_ids: set[str] = set(known_ids or ())
    barren = 0

    for _ in range(max_iters):
        try:
            msg = await llm.complete_raw(convo, max_tokens=max_tokens,
                                         temperature=temperature, tools=spec)
        except Exception as exc:  # noqa: BLE001


            trace.error = f"{type(exc).__name__}: {exc}"


            return extra, trace

        calls = msg.get("tool_calls") or []
        if not calls:


            break


        calls = [_rebuild_call(c, iteration=trace.iters, index=i)
                 for i, c in enumerate(calls)]
        kept, truncated, dropped_depth = _cap_calls(calls, iteration=trace.iters)
        trace.truncated = trace.truncated or truncated
        trace.dropped_depth += dropped_depth


        if not kept:


            trace.stopped_all_dropped = True
            break
        msg = dict(msg)
        msg["tool_calls"] = kept
        convo.append(msg)
        extra.append(msg)

        for call in kept:
            cid, name, raw_args = _parse_call(call)


            result = query_cache.dispatch(name, raw_args, ctx)
            try:
                args = json.loads(raw_args or "{}")
            except json.JSONDecodeError:
                args = {"_raw": raw_args[:200]}
            trace.calls.append((name, args if isinstance(args, dict) else {}, result))
            tool_msg = {"role": "tool", "tool_call_id": cid, "name": name, "content": result}
            convo.append(tool_msg)
            extra.append(tool_msg)


            if name in FACT_TOOLS:
                ids = set(fact_ids_in(result))
                if ids - seen_ids:
                    barren = 0
                else:
                    barren += 1
                    trace.barren_calls += 1
                seen_ids |= ids
                if barren >= BARREN_STOP:


                    trace.stopped_barren = True

        trace.iters += 1
        if trace.stopped_barren:


            break
    else:

        trace.truncated = True

    return extra, trace
