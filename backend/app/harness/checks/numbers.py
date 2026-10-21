"""Compare generated quantities with supplied evidence while retaining units and date distinctions."""

from __future__ import annotations

import re

from ..state import State
from ..tools import tabular
from ..types import Verdict
from . import blockcheck
from .pick import pick_dimension


REL = 0.005


MIN_MAGNITUDE = 100


_NOT_DATA = (
    re.compile('(?:1[6-9]|20|21)\\d{2}\\s*(?:\u5e74|\u8d22\u5e74|Q[1-4])'),
    re.compile(r"^#{1,6}\s*\d+(?:\.\d+)*", re.M),
    re.compile(r"^[ \t]*\d+(?:\.\d+)*\s*[、.)）]", re.M),
    re.compile(r"\d+(?:\.\d+){2,}"),
    re.compile(r"\d+\s*[:：]\s*\d+"),
)


_PROSE_NUM = re.compile('(?<![\\d.-])(-?\\d[\\d,]*(?:\\.\\d+)?)\\s*([\u4e07\u842c\u4ebf\u5104\u5343\u767e])?\\s*([%\uff05])?')

_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"!?\[[^\]]*\]\([^)]*\)")


def sources(st: State) -> str:
    st_facts = list(st.bag.get("facts_all") or []) or list(st.facts)
    parts = [st.ctx.content or "", st.before or "", st.after or "",
             str(st.bag.get("prompt") or ""), str(st.bag.get("selection") or ""),
             str(st.bag.get("content_at_start") or "")]
    parts += st_facts + list(st.facts) + list(st.charts)
    if st.trace is not None:
        parts += [r for _n, _a, r in st.trace.calls if r]
    return "\n".join(p for p in parts if p)


def has_tool_output(st: State) -> bool:
    if st.charts or st.facts or st.bag.get("facts_all"):
        return True
    return st.trace is not None and bool(st.trace.calls)


def unsupported(values: list[float], known: set[float]) -> list[float]:
    bad: list[float] = []
    for v in values:
        if any(any(abs(c - h) <= max(REL * abs(c), 1e-9) for h in known)
               for c in (v, v / 100.0, v * 100.0)):
            continue
        bad.append(v)
    return bad


def _fmt(values: list[float], limit: int = 5) -> str:
    return "、".join(f"{v:g}" for v in values[:limit]) + (
        f' (plus {len(values) - limit} others)' if len(values) > limit else "")


def chart_numbers_grounded(st: State) -> Verdict | None:
    if not has_tool_output(st):
        return None
    values: list[float] = []
    for block in blockcheck.mermaid_blocks(st.content):
        values += blockcheck.chart_numbers(block)
    values += blockcheck.table_numbers(st.content)
    if not values:
        return None
    bad = unsupported(values, tabular.numbers_in_text(sources(st)))
    if not bad:
        return None
    return Verdict(
        pick_dimension(st, "data_grounding", "numbers_from_tools"),
        f'These chart/table numbers occur neither in tool output nor in the original note: {_fmt(bad)}. These values must be calculated by tools. In the next evidence phase, call describe_table, aggregate_table or correlate_columns and redraw with the returned values. Omit values the tools cannot calculate. Change only the affected chart/table cells, leaving unrelated prose intact.',
    )


def prose_statistics(text: str) -> list[float]:
    body = _FENCE.sub(" ", text or "")
    body = _INLINE_CODE.sub(" ", body)
    body = _LINK.sub(" ", body)
    for block in blockcheck.table_blocks(body):
        body = body.replace(block, " ")
    for pat in tabular._NOT_A_QUANTITY:          # noqa: SLF001
        body = pat.sub(" ", body)
    for pat in _NOT_DATA:
        body = pat.sub(" ", body)
    out: list[float] = []
    for m in _PROSE_NUM.finditer(body):
        raw, unit, pct = m.group(1), m.group(2), m.group(3)
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            continue
        if unit:
            v *= tabular._UNITS[unit]            # noqa: SLF001
        if not (pct or "." in raw or abs(v) >= MIN_MAGNITUDE):
            continue


        if not pct and not unit and blockcheck._looks_like_a_year(raw, v):   # noqa: SLF001
            continue
        out.append(v)
    return out


def numbers_from_tools(st: State) -> Verdict | None:
    if not has_tool_output(st):
        return None
    values = prose_statistics(st.content)
    if not values:
        return None
    bad = unsupported(values, tabular.numbers_in_text(sources(st)))
    if not bad:
        return None
    return Verdict(
        pick_dimension(st, "numbers_from_tools", "data_grounding"),
        f'These body numbers occur neither in tool output nor in the original note: {_fmt(bad)}. In this mode, obtain all calculated totals, means and proportions from aggregate_table, describe_table or correlate_columns. Make the missing call in the next evidence phase. If it cannot be calculated, rewrite the affected statement without the number and preserve unrelated sentences.',
    )
