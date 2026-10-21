"""Cache identical tool queries within a run and report duplicate calls."""

from __future__ import annotations

import json

from . import tools


CACHEABLE = frozenset({
    "search_memory", "list_topics", "list_entities", "filter_facts",
    "facts_in_range", "fact_sources", "search_session_context", "gather_subject",
})


SAME_ROUND = ("(The same {tool} arguments were already used in this run; the result is above. "
              "To find new evidence, change the query, perspective or tool.)")

_KEY = "query_cache"
SEP = "\t"


_TRANSIENT = ("Execution error", "Execution failed", '\u6267\u884c\u51fa\u9519', '\u6267\u884c\u5931\u8d25')


def _cache(ctx) -> dict:
    cache = ctx.scratch.get(_KEY)
    if not isinstance(cache, dict):
        cache = {"entries": {}, "round": -1,
                 "run": {"calls": 0, "hits": 0, "skipped": 0},
                 "this_round": {"calls": 0, "hits": 0, "skipped": 0}}
        ctx.scratch[_KEY] = cache
    return cache


def key(tool: str, args: dict, ctx=None) -> str:
    try:
        body = json.dumps(args or {}, sort_keys=True, ensure_ascii=False)
    except TypeError:
        body = repr(sorted((args or {}).items()))
    who = f"{getattr(ctx, 'user', '')}/{getattr(ctx, 'scope', '')}" if ctx is not None else ""
    return who + SEP + tool + SEP + body


def begin_round(ctx, round_: int) -> None:
    cache = _cache(ctx)
    cache["round"] = int(round_)
    cache["this_round"] = {"calls": 0, "hits": 0, "skipped": 0}


def stats(ctx) -> dict:
    cache = _cache(ctx)
    return {"run": dict(cache["run"]), "this_round": dict(cache["this_round"])}


def repeat_rate(ctx) -> float:
    run = _cache(ctx)["run"]
    return (run["hits"] / run["calls"]) if run["calls"] else 0.0


def dispatch(name: str, args: dict | str, ctx) -> str:
    """Reuse prior query results without repeating the full payload."""
    cache = _cache(ctx)
    cache["run"]["calls"] += 1
    cache["this_round"]["calls"] += 1
    if name not in CACHEABLE:
        return tools.dispatch(name, args, ctx)

    parsed = args
    if isinstance(args, str):
        try:
            parsed = json.loads(args or "{}")
        except json.JSONDecodeError:
            parsed = None
    if not isinstance(parsed, dict):
        return tools.dispatch(name, args, ctx)

    k = key(name, parsed, ctx)
    hit = cache["entries"].get(k)
    if hit is not None:
        cache["run"]["hits"] += 1
        cache["this_round"]["hits"] += 1
        hit["n"] += 1
        if hit["round"] == cache["round"]:
            cache["run"]["skipped"] += 1
            cache["this_round"]["skipped"] += 1
            return SAME_ROUND.format(tool=name)

        hit["round"] = cache["round"]
        return hit["result"]

    result = tools.dispatch(name, args, ctx)
    if not any(flag in result[:40] for flag in _TRANSIENT):
        cache["entries"][k] = {"result": result, "round": cache["round"], "n": 1}
    return result
