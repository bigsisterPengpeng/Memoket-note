"""Track evidence used across rounds without dropping fact identifiers or treating summaries as verbatim evidence."""

from __future__ import annotations

import json
import re

from .. import query_cache
from ..state import State


_FACT_LINE = re.compile(r"^\[([A-Za-z0-9_\-]+)\]\s*(.+)$", re.M)


_META_LINE = re.compile(r"^\s*[（(]([^）)]*)[）)]\s*$")


_DATE = re.compile(r"^\d{4}(-\d{2}){0,2}$")


_TOTAL = re.compile('(?:\u5171\\s*)?(\\d+)\\s*(?:\u6761|facts total)')

_TOPIC_LINE = re.compile('^-\\s*(\\S+)\\s*[\uff08(](\\d+)\\s*(?:\u6761|facts)', re.M)

LINE_CHARS = 60
SEP = "\t"


def blank() -> dict:
    return {"queries": [], "axes": {}, "facts": {}}


def parse_facts(result: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    pending: tuple[str, str] | None = None
    for line in (result or "").splitlines():
        m = _FACT_LINE.match(line.strip())
        if m:
            if pending:
                out.append((pending[0], pending[1], ""))
            pending = (m.group(1), m.group(2).strip())
            continue
        meta = _META_LINE.match(line)
        if pending and meta:
            head = meta.group(1).split("·")[0].strip()
            out.append((pending[0], pending[1], head if _DATE.match(head) else ""))
            pending = None
    if pending:
        out.append((pending[0], pending[1], ""))
    return out


def ledger_of(st: State) -> dict:
    led = st.bag.get("ledger")
    if not isinstance(led, dict):
        led = blank()
        st.bag["ledger"] = led
    return led


def _key(tool: str, args: dict) -> str:
    try:
        return tool + SEP + json.dumps(args or {}, sort_keys=True, ensure_ascii=False)
    except TypeError:
        return tool + SEP + repr(sorted((args or {}).items()))


def _axis_of(tool: str, args: dict) -> str:
    if tool != "filter_facts":
        return ""
    for k in ("topic", "entity", "kind", "who"):
        if (args or {}).get(k):
            return f"{k}:{args[k]}"
    return ""


def fold(led: dict, calls: list[tuple[str, dict, str]]) -> dict:
    stat = {"tool_calls": 0, "repeat_calls": 0, "facts_new": 0, "cached_calls": 0}
    seen = {q["key"] for q in led["queries"]}
    for tool, args, result in calls or []:
        stat["tool_calls"] += 1
        k = _key(tool, args)
        rows = parse_facts(result)
        ids = [fid for fid, _t, _w in rows]
        if k in seen:
            stat["repeat_calls"] += 1
        else:
            seen.add(k)
        led["queries"].append({"key": k, "tool": tool, "hit": len(ids),
                               "empty": not ids})
        for fid, text, when in rows:
            if fid not in led["facts"]:
                led["facts"][fid] = {"line": text[:LINE_CHARS], "state": "taken",
                                     "tool": tool, "when": when}
                stat["facts_new"] += 1
            elif when and not led["facts"][fid].get("when"):


                led["facts"][fid]["when"] = when

        axis = _axis_of(tool, args)
        if axis:
            total = _TOTAL.search(result or "")
            slot = led["axes"].setdefault(axis, {"total": 0, "taken": 0})
            if total:
                slot["total"] = max(slot["total"], int(total.group(1)))
            slot["taken"] = max(slot["taken"], len(ids))
        if tool == "list_topics":
            for m in _TOPIC_LINE.finditer(result or ""):
                slot = led["axes"].setdefault(f"topic:{m.group(1)}",
                                              {"total": 0, "taken": 0})
                slot["total"] = max(slot["total"], int(m.group(2)))
    return stat


GAP_MAX_AXES = 8
GAP_MAX_QUERIES = 10


def _pretty_args(args: dict) -> str:
    out = []
    for k, v in (args or {}).items():
        if k in ("limit", "offset", "top_k") or v in (None, "", []):
            continue
        out.append(f"{k}={v}")
    return " ".join(out)


def _split_key(key: str) -> tuple[str, dict]:
    tool, _sep, raw = (key or "").partition(SEP)
    try:
        args = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        args = {}
    return tool, args if isinstance(args, dict) else {}


def gap_summary(led: dict, *, max_axes: int = GAP_MAX_AXES,
                max_queries: int = GAP_MAX_QUERIES) -> str:
    axes = led.get("axes") or {}
    untouched: list[tuple[str, int, int]] = []
    partial: list[tuple[str, int, int]] = []
    done = 0
    for key, slot in axes.items():
        total = int((slot or {}).get("total") or 0)
        taken = int((slot or {}).get("taken") or 0)
        if total <= 0:
            continue
        if taken <= 0:
            untouched.append((key, total, taken))
        elif taken < total:
            partial.append((key, total, taken))
        else:
            done += 1
    untouched.sort(key=lambda r: -r[1])
    partial.sort(key=lambda r: -(r[1] - r[2]))

    lines: list[str] = []
    shown = (untouched + partial)[:max_axes]
    if shown:
        lines.append('[Directions not fully retrieved during this run]')
        for key, total, taken in shown:
            name = key.split(":", 1)[1] if ":" in key else key
            lines.append(f'- {name}: {total} records available; '
                         + ('none retrieved' if taken <= 0 else f'retrieved {taken} records'))
        hidden = len(untouched) + len(partial) - len(shown)
        if hidden > 0:
            lines.append(f'({hidden} additional directions remain partially retrieved.)')
        if done:


            lines.append(f'({done} other directions have already been retrieved.)')

    seen: set[str] = set()
    qlines: list[str] = []
    for q in (led.get("queries") or []):
        key = q.get("key") or ""
        if key in seen:
            continue
        seen.add(key)
        tool, args = _split_key(key)
        if tool not in query_cache.CACHEABLE:


            continue
        text = f"- {tool} {_pretty_args(args)}".rstrip()
        if q.get("empty"):


            text += ' -> 0 records; choose another direction instead of rephrasing the same query'
        qlines.append(text)
    if qlines:
        lines.append("")
        lines.append('[Queries already sent; do not repeat them unchanged]')
        lines.extend(qlines[:max_queries])
        if len(qlines) > max_queries:
            lines.append(f'({len(qlines) - max_queries} additional queries have already been sent.)')

    if not lines:
        return ""
    lines.append("")


    lines.append('Search relevant, unexplored directions above this round. These counts identify gaps; they are not quotas and unrelated topics need not be retrieved.')
    return "\n".join(lines)


def note_topics(led: dict, topics_text: str) -> int:
    n = 0
    for m in _TOPIC_LINE.finditer(topics_text or ""):
        slot = led["axes"].setdefault(f"topic:{m.group(1)}", {"total": 0, "taken": 0})
        slot["total"] = max(slot["total"], int(m.group(2)))
        n += 1
    return n


def repeat_rate(led: dict) -> float:
    qs = led.get("queries") or []
    if not qs:
        return 0.0
    seen: set[str] = set()
    repeat = 0
    for q in qs:
        if q["key"] in seen:
            repeat += 1
        seen.add(q["key"])
    return repeat / len(qs)


def mark_used(led: dict, content: str) -> int:
    n = 0
    for fid, row in led["facts"].items():
        if f"[{fid}]" in (content or ""):
            row["state"] = "used"
            n += 1
    return n


class Ledger:
    name = "ledger"
    hooks = ("before_round", "after_prepare", "after_judge")


    after: tuple[str, ...] = ("facts",)

    async def before_round(self, st: State) -> None:
        query_cache.begin_round(st.ctx, st.round)

    async def after_prepare(self, st: State) -> None:
        if not st.bag.get("run_id"):
            import uuid
            st.bag["run_id"] = uuid.uuid4().hex[:12]
        led = ledger_of(st)
        calls = st.trace.calls if st.trace is not None else []
        stat = fold(led, calls)


        stat["cached_calls"] = int(query_cache.stats(st.ctx)["this_round"]["hits"])


        stat["depth_dropped"] = int(getattr(st.trace, "dropped_depth", 0) or 0)
        st.bag["ledger_round"] = stat

    async def after_judge(self, st: State) -> None:
        led = ledger_of(st)
        mark_used(led, st.content)


        if st.ev is not None and not st.skip_judge:
            st.bag.setdefault("score_vectors", []).append(
                {n: s.level for n, s in st.ev.scores.items()})
        stat = st.bag.get("ledger_round") or {}


        from ...database import store
        scores = ({n: s.level for n, s in st.ev.scores.items()} if st.ev else {})
        store.record_harness_round(
                key=f"{st.mode.key}:{st.ctx.note_id}",
                run_id=st.bag.get("run_id") or "",
                round_=st.round,
                scores=scores,
                status=(st.ev.status if st.ev else "unscored"),
                weakest=((st.ev.weakest or "") if st.ev else ""),
                content_len=len(st.content or ""),
                facts_new=int(stat.get("facts_new") or 0),
                facts_total=len(led["facts"]),
                tool_calls=int(stat.get("tool_calls") or 0),
                repeat_calls=int(stat.get("repeat_calls") or 0),
                cached_calls=int(stat.get("cached_calls") or 0),
                superseded=int(st.bag.get("superseded_round") or 0),


                revisions_proposed=int(st.bag.get("revisions_proposed") or 0),
                revisions_dropped=int(st.bag.get("revisions_dropped") or 0),
                depth_dropped=int(stat.get("depth_dropped") or 0),


                claim_atoms=int(st.bag.pop("claim_atoms", -1)),
                fired_checks=json.dumps(st.bag.pop("fired_checks", []),
                                        ensure_ascii=False),
                abstained=str(st.bag.pop("claim_abstained", "") or ""),


            **_cite_cols(st.bag.pop("cite_cover", None)))


def _cite_cols(cov) -> dict:
    if not cov:
        return {"cite_located": -1, "cite_marked": -1, "cite_matched": -1}
    located, marked, matched = cov
    return {"cite_located": int(located), "cite_marked": int(marked),
            "cite_matched": int(matched)}
