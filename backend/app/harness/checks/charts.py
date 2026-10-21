"""Check generated chart syntax and traceable numeric inputs before accepting chart output."""

from __future__ import annotations

import re

from . import blockcheck
from ..state import State
from ..types import Verdict
from .pick import pick_dimension


_ALL = 99


def no_fake_charts(st: State) -> Verdict | None:
    before = str(st.bag.get("content_at_start") or "")
    was_there = set(blockcheck.fake_charts(before, limit=_ALL))
    hits = [h for h in blockcheck.fake_charts(st.content, limit=_ALL)
            if h not in was_there][:3]
    if not hits:


        was_flow = set(blockcheck.text_flow(before, limit=_ALL))
        flows = [f for f in blockcheck.text_flow(st.content, limit=_ALL)
                 if f not in was_flow][:2]
        if flows:
            return Verdict(
                pick_dimension(st, "has_charts", "chart_validity"),
                f"The body presents an arrow-separated process instead of a diagram: {'; '.join(flows)}. Call render_chart with kind=flow and the steps as labels, without values. Insert the returned block unchanged and add one explanatory sentence; do not repeat every step in prose.",
            )
        return None
    return Verdict(
        pick_dimension(st, "has_charts", "chart_validity"),
        f"This round describes a chart without rendering it: {'; '.join(hits)}. Call chart_column, render_chart or chart_from_text and insert the returned Mermaid block unchanged. Use the validated tool output. For a two-column relationship, report the correlation or show two bar/line series instead of inventing unsupported scatter syntax.",
    )


def charts_from_tools(st: State) -> Verdict | None:
    """Mermaid that a tool did not produce.

    The model learned to route around ``no_fake_charts`` by hand-writing
    mermaid that mimics tool output -- the numbers were even correct, but the
    syntax was its own invention (``y-axis "impressions" 0 --> 260000``,
    a range ``render_chart`` never emits because getting it wrong turns the
    whole chart into an error message).

    So the test is not "does it look right" but **"is it byte-for-byte what a
    tool returned"**. Correct numbers don't make a chart render, and don't
    guarantee the next one won't quietly change a digit.
    """


    allowed = st.charts + blockcheck.mermaid_blocks(st.bag.get("content_at_start") or "")
    bad = blockcheck.unauthorized_charts(st.content, allowed)
    if not bad:
        return None
    if "chart" not in st.mode.groups:


        return Verdict(
            pick_dimension(st, "has_charts", "chart_validity"),
            f"Found {len(bad)} handwritten Mermaid charts ({'; '.join(bad)}). Removed them because whole-note continuation does not create diagrams. Use the Smart illustration slash command to generate a validated diagram.",
            fix=lambda text: _drop_unauthorized(text, allowed),


            fix_note=(f'Removed {len(bad)} handwritten Mermaid charts. Use the Smart illustration slash command for diagrams.'),
        )
    return Verdict(
        pick_dimension(st, "has_charts", "chart_validity"),
        f"Found {len(bad)} Mermaid charts without tool provenance ({'; '.join(bad)}). Use code returned unchanged by chart tools. If the result is unsuitable, call render_chart again during the next material-gathering phase; tools are unavailable during body generation. Only a simple graph TD or flowchart LR with basic A[Step] --> B[Next] edges may be handwritten.",
    )


def _drop_blocks(text: str, should_drop) -> str:
    def _sub(m):
        body = "\n".join(ln.rstrip() for ln in m.group(1).strip().split("\n"))
        return "" if should_drop(body) else m.group(0)
    out = re.sub(r"```mermaid\n(.*?)```[ \t]*\n?", _sub, text or "", flags=re.S)
    return re.sub(r"\n{3,}", "\n\n", out)


def _drop_unauthorized(text: str, allowed: list[str]) -> str:
    ok = set(allowed)
    return _drop_blocks(text, lambda b: b not in ok and not blockcheck.is_plain_flowchart(b))


RESTATE_NODE_COVER = 0.5
RESTATE_CHART_COVER = 0.8
RESTATE_WINDOW = 4
RESTATE_MIN_NODES = 3

_NODE_LABEL = re.compile(
    r"\[\[([^\]]+)\]\]|\(\(([^)]+)\)\)|\[([^\]]+)\]|\(([^)]+)\)|\{([^}]+)\}|\|([^|]+)\|")


def chart_node_labels(block: str) -> list[str]:
    out: list[str] = []
    for m in _NODE_LABEL.finditer(block or ""):
        label = next((g for g in m.groups() if g), "").strip().strip('"')
        if label and label not in out:
            out.append(label)
    return out


def chart_restates(block: str, around: str) -> tuple[int, int]:
    from .relevance import terms
    ctx = terms(around)

    labels = [(label, terms(label)) for label in chart_node_labels(block)]
    labels = [(label, lt) for label, lt in labels if lt]
    said = sum(1 for _label, lt in labels if len(lt & ctx) / len(lt) >= RESTATE_NODE_COVER)
    return said, len(labels)


def restating_charts(content: str, before: str = "") -> list[tuple[str, int, int]]:
    was = set(blockcheck.mermaid_blocks(before))
    paras = re.split(r"\n\s*\n", content or "")
    out: list[tuple[str, int, int]] = []
    for i, para in enumerate(paras):
        if not para.strip().startswith("```mermaid"):
            continue
        blocks = blockcheck.mermaid_blocks(para)
        if not blocks or blocks[0] in was:
            continue
        window = [p for p in paras[max(0, i - RESTATE_WINDOW):i] + paras[i + 1:i + 1 + RESTATE_WINDOW]
                  if not p.strip().startswith("```")]
        said, total = chart_restates(blocks[0], "\n\n".join(window))
        if total >= RESTATE_MIN_NODES and said / total >= RESTATE_CHART_COVER:
            out.append((blocks[0], said, total))
    return out


def chart_restates_list(st: State) -> Verdict | None:
    before = str(st.bag.get("content_at_start") or "")
    hits = restating_charts(st.content, before)
    if not hits:
        return None
    block, said, total = hits[0]
    gone = {b for b, _s, _t in hits}
    head = chart_node_labels(block)[:3]
    return Verdict(
        pick_dimension(st, "has_charts", "non_repetition"),
        f"Of the chart's {total} nodes, {said} ({'、'.join(head)}...) repeat the adjacent list or paragraph. The redundant chart was removed. Use diagrams for branches, dependencies or relationships that prose does not show clearly.",
        fix=lambda text: _drop_blocks(text, lambda b: b in gone),


        fix_note=(f"Removed {len(hits)} charts that repeat the adjacent list or paragraph ({'、'.join(head)}...)."),
    )


MAX_PIE_SLICES = 8
MAX_XY_CATEGORIES = 12
MAX_FLOW_NODES = 14


def chart_readable(st: State) -> Verdict | None:
    start = blockcheck.mermaid_blocks(st.bag.get("content_at_start") or "")
    problems: list[str] = []
    for block in blockcheck.mermaid_blocks(st.content):
        if block in start:
            continue
        shape = blockcheck.chart_shape(block)
        title = shape["title"] or '(untitled)'
        cats = shape["categories"]
        if shape["kind"] == "xy":
            if not shape["axis"]:
                problems.append(f'「{title}" has no y-axis name, so the measurement is unclear.')
            elif shape["series"] > 1 and len(
                    [n for n in shape["axis"].split("/") if n.strip()]) < shape["series"]:
                problems.append(
                    f"""「{title}" has {shape['series']} series, but the y-axis names only {len([n for n in shape['axis'].split('/') if n.strip()])} metrics ({shape['axis']}). Use short, distinct series names.""")
            if len(cats) > MAX_XY_CATEGORIES:
                problems.append(
                    f'「{title}" has {len(cats)} x-axis categories. Select the most useful comparisons or split the chart by dimension.')
            truncated = [c for c in cats if c.endswith("…")]
            if truncated:
                problems.append(
                    f"""「{title}" has truncated x-axis labels ({'、'.join(truncated[:2])}). Use shorter labels and render again.""")
        elif shape["kind"] == "pie" and len(cats) > MAX_PIE_SLICES:
            problems.append(
                f'「{title}" has {len(cats)} pie slices. Retain the largest categories and group the rest as Other.')
        elif shape["kind"] == "flow" and shape["nodes"] > MAX_FLOW_NODES:
            problems.append(
                f"The flowchart has {shape['nodes']} nodes and does not fit one screen. Split it or show only the main path.")
    if not problems:
        return None
    return Verdict(
        pick_dimension(st, "has_charts", "chart_validity"),
        'The chart is unreadable: ' + "；".join(problems[:2]) + '. Redraw with chart_from_text, render_chart or chart_column; do not edit generated Mermaid code manually.',
    )
