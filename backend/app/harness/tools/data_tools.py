"""Calculate note-local statistics and generate validated chart and table blocks."""

from __future__ import annotations

import json

from . import blocks, tabular
from .registry import ToolContext, register


NEAR_CHARS = 600


def _tables(ctx: ToolContext) -> list[tabular.Table]:
    return tabular.find_tables(ctx.content or "")


def _cursor(ctx: ToolContext) -> int:
    return max(0, min(int(ctx.cursor or 0), len(ctx.content or "")))


def _default_index(ctx: ToolContext) -> int:
    """Choose the table nearest the cursor when no index was supplied."""
    n = tabular.nearest(_tables(ctx), _cursor(ctx))
    return n.index if n else 0


def _pick(ctx: ToolContext, index: int | None) -> tabular.Table | str:
    ts = _tables(ctx)
    if not ts:
        return '(No table data found in this note. Markdown tables and fenced csv/tsv blocks are supported.)'
    if index is None:
        index = _default_index(ctx)
    if index < 0 or index >= len(ts):
        return f"(Table {index} does not exist. There are {len(ts)} tables, indexed 0 to {len(ts) - 1}.)"
    return ts[index]


@register(
    name="list_tables", group="data",
    description='List tables in the current note with their indices, origins, column names and row counts. Call this before analyzing a table.',
    params={},
)
def list_tables(ctx: ToolContext) -> str:
    ts = _tables(ctx)
    if not ts:
        return '(This note has no table data. Markdown tables and fenced csv/tsv blocks are supported.)'
    cur = _cursor(ctx)
    lines = []


    for t in sorted(ts, key=lambda x: tabular.distance(x, cur)):
        rows, cols = t.shape
        kinds = ['numeric' if tabular.is_numeric_column(t.column(c)) else 'text' for c in t.columns]
        d = tabular.distance(t, cur)
        crossed = tabular.headings_between(ctx.content or "", cur, t.start, t.end)
        if crossed:
            tag = f"  — {crossed} headings intervene; **this belongs to another topic**"
            lines.append(f"Table {t.index} ({t.source}, {rows} rows, {cols} columns): "
                         + ", ".join(f"{c}[{k}]" for c, k in zip(t.columns, kinds)) + tag)
            continue
        if d <= NEAR_CHARS:
            tag = '  — **This table is beside the cursor; use it unless another table was explicitly requested.**'
        else:
            tag = f"  — {d} characters from the cursor; **not near the cursor**"
        lines.append(f"Table {t.index} ({t.source}, {rows} rows, {cols} columns): "
                     + ", ".join(f"{c}[{k}]" for c, k in zip(t.columns, kinds)) + tag)
    if all(tabular.distance(t, cur) > NEAR_CHARS
           or tabular.headings_between(ctx.content or "", cur, t.start, t.end)
           for t in ts):
        lines.insert(0, '(**No table near the cursor.** The tables below are distant and may concern other content. Use numbers_near_cursor to inspect the prose currently being edited before choosing a table.)')
    return "\n".join(lines)


@register(
    name="numbers_near_cursor", group="data",
    description="Return original sentences containing numbers near the cursor, nearest first. Start prose-based visualization here: prefer the user's current context over an unrelated table elsewhere in the note.",
    params={"radius": {"type": "integer",
                       "description": 'Characters to inspect on each side of the cursor; keep the default of 1200'}},
)
def numbers_near_cursor(ctx: ToolContext, radius: int | None = None) -> str:
    text = ctx.content or ""
    r = int(radius) if radius else 1200
    hits = tabular.sentences_with_numbers(text, _cursor(ctx), radius=r)
    if not hits:
        return f"(No sentences containing numbers within {r} characters of the cursor.)"
    head = ('Sentences containing numbers near the cursor, nearest first. **Read their units and keep compatible measurements together in each chart**:\n')
    return head + "\n".join(f"{i}. {s}" for i, s in enumerate(hits[:12], 1))


@register(
    name="describe_table", group="data",
    description='Profile a table: column types and missing counts; numeric minimum, maximum, mean, median, P25, P75, standard deviation and sum; distinct text values and frequent categories. All statistics are calculated by code; do not estimate them yourself.',
    params={"index": {"type": "integer",
                      "description": 'Table index from list_tables; defaults to the table nearest the cursor'}},
)
def describe_table(ctx: ToolContext, index: int | None = None) -> str:
    t = _pick(ctx, None if index is None else int(index))
    if isinstance(t, str):
        return t
    out = [tabular.describe_column(c, t.column(c)) for c in t.columns]
    return json.dumps(out, ensure_ascii=False, indent=1)


@register(
    name="aggregate_table", group="data",
    description='Group by one column and aggregate another with sum, mean, count, max, min or median. Return results in descending value order.',
    params={
        "index": {"type": "integer", "description": 'Table index; defaults to the table nearest the cursor'},
        "group_by": {"type": "string", "description": 'Column to group by'},
        "value": {"type": "string", "description": 'Column to aggregate; any column is acceptable for count'},
        "agg": {"type": "string", "description": "sum / mean / count / max / min / median"},
    },
    required=["group_by", "value", "agg"],
)
def aggregate_table(ctx: ToolContext, group_by: str, value: str, agg: str,
                    index: int | None = None) -> str:
    t = _pick(ctx, None if index is None else int(index))
    if isinstance(t, str):
        return t
    try:
        rows = tabular.aggregate(t, group_by, value, str(agg).lower())
    except (KeyError, ValueError) as exc:
        return f"({exc}. Table columns: {', '.join(t.columns)})"
    if not rows:
        return f"(No numeric values to aggregate by {group_by}; column {value} may be nonnumeric.)"
    return json.dumps([{'group': k, 'value': v} for k, v in rows], ensure_ascii=False)


@register(
    name="correlate_columns", group="data",
    description='Calculate the Pearson correlation between two numeric columns and report the number of participating rows. Treat correlation from a small sample cautiously.',
    params={
        "index": {"type": "integer", "description": 'Table index; defaults to the table nearest the cursor'},
        "x": {"type": "string", "description": 'First column name'},
        "y": {"type": "string", "description": 'Second column name'},
    },
    required=["x", "y"],
)
def correlate_columns(ctx: ToolContext, x: str, y: str, index: int | None = None) -> str:
    t = _pick(ctx, None if index is None else int(index))
    if isinstance(t, str):
        return t
    try:
        return json.dumps(tabular.correlate(t, x, y), ensure_ascii=False)
    except KeyError as exc:
        return f"(Column {exc} does not exist. Table columns: {', '.join(t.columns)})"


_MIXED = ("/", "／", "、", "，", ",", " and ", " or ", " + ", ' \u548c ', ' \u4e0e ', ' \u6216 ', '\u6216')


def _mixed_unit(unit: str) -> str:
    u = (unit or "").strip()
    if not u or len(u) > 12:
        return ""
    return u if any(sep in u for sep in _MIXED) else ""


def _too_few(values: list[float], values2: list | None, kind: str) -> str:
    """Avoid charts with only one value and no comparison series."""
    if str(kind).lower() == "flow" or len(values) != 1 or values2:
        return ""
    return ('(Only one value is available without a comparison series. State it in prose or find a source-backed comparison such as another period or a target before drawing a chart.)')


def _unit_clash(ctx: ToolContext, values: list[float]) -> str:
    """Reject incompatible units using their original prose context."""
    by = tabular.mixed_units(ctx.content or "", values, _cursor(ctx))
    if not by:
        return ""
    detail = "; ".join(f"{u}: {', '.join(f'{v:g}' for v in vs)}" for u, vs in by.items())
    return (f"(The original values have incompatible units: {detail}. "
            "Values with different units cannot be compared on the same axis. "
            "**Split them into separate charts by unit.**)")


MIN_POINTS_FOR_HISTOGRAM = 10


@register(
    name="chart_column", group="chart",
    description='Render a column distribution as an insertable Mermaid block. Prefer this for column visualization: numeric columns produce code-binned histograms, while text columns produce category-share pie charts. Do not calculate bins yourself.',
    params={
        "index": {"type": "integer", "description": 'Table index; defaults to the table nearest the cursor'},
        "column": {"type": "string", "description": 'Column name'},
    },
    required=["column"],
)
def chart_column(ctx: ToolContext, column: str, index: int | None = None) -> str:
    t = _pick(ctx, None if index is None else int(index))
    if isinstance(t, str):
        return t
    try:
        vals = t.column(column)
    except KeyError:
        return f"(Column {column!r} does not exist. Table columns: {', '.join(t.columns)})"

    if tabular.is_numeric_column(vals):
        n = len(tabular.numeric([v for v in vals if (v or "").strip()]))
        if n < MIN_POINTS_FOR_HISTOGRAM:
            return (f"(Column {column} has only {n} data points; a histogram would not show a useful distribution. "
                    f"For this sample size, compare individual items directly. "
                    f"Use aggregate_table or render_chart for a grouped comparison.)")
        labels, counts = tabular.histogram(vals)
        if not labels:
            return f"(Column {column} has fewer than two valid numeric values; no distribution can be plotted.)"
        return blocks.mermaid_xy(f"{column} distribution", labels, counts, 'Count', kind="bar")

    counts: dict[str, int] = {}
    for v in vals:
        v = (v or "").strip()
        if v:
            counts[v] = counts.get(v, 0) + 1
    if not counts:
        return f"(Column {column} contains only empty values.)"
    freqs = set(counts.values())
    if len(freqs) == 1:

        only = next(iter(freqs))
        return (f"(Each of the {len(counts)} values in {column} occurs {only} times. A share chart adds no useful comparison. "
                f"Use this column as a **grouping dimension** with aggregate_table, "
                f"then compare the grouped numeric results.)")
    return blocks.mermaid_pie(f"{column} category share",
                              sorted(((k, float(n)) for k, n in counts.items()),
                                     key=lambda kv: -kv[1]))


@register(
    name="chart_from_text", group="chart",
    description='Use this when nearby prose contains numbers without a table. Extract ordered labels and values from the cursor context; the tool renders the chart and checks values against the original text. Incorrect or invented values are rejected. Use pie for shares, bar for comparisons or line for trends.',
    params={
        "kind": {"type": "string", "description": "pie / bar / line"},
        "title": {"type": "string", "description": 'Chart title'},
        "labels": {"type": "array", "items": {"type": "string"},
                   "description": 'Ordered label for each value'},
        "values": {"type": "array", "items": {"type": "number"},
                   "description": 'Values copied from the original prose. Normalize formatting only; never calculate or invent values absent from the text.'},
        "series": {"type": "string", "description": 'Name of the first series, such as March or impressions'},
        "unit": {"type": "string",
                 "description": 'One compatible unit for this chart, such as percent, devices or kilometers. Do not place different units on the same axis; split incompatible measurements into separate charts.'},
        "values2": {"type": "array", "items": {"type": "number"},
                    "description": 'Optional second series. For grouped comparisons, use categories on the x-axis and separate series for periods rather than flattening period-by-category pairs into one dimension.'},
        "series2": {"type": "string", "description": 'Name of the second series'},
        "kind2": {"type": "string", "description": 'Render the second series as bar or line. Keep units compatible; use separate charts for incompatible measurements.'},
    },
    required=["kind", "title", "labels", "values", "unit"],
)
def chart_from_text(ctx: ToolContext, kind: str, title: str, labels: list,
                    values: list, unit: str = "", series: str = "Value",
                    values2: list | None = None, series2: str = "Series 2",
                    kind2: str = "bar") -> str:
    text = ctx.content or ""
    if not text.strip():
        return '(Note content is unavailable)'
    mixed = _mixed_unit(unit) or _mixed_unit(series)
    if mixed:
        return (f"(The unit {mixed} combines incompatible measurements. "
                "Keep one compatible unit per chart; heights on a shared axis must be comparable. "
                "Split the values into separate charts by unit.)")
    clash = _unit_clash(ctx, [float(v) for v in (values or [])
                              if isinstance(v, (int, float))])
    if clash:
        return clash
    few = _too_few([float(v) for v in (values or []) if isinstance(v, (int, float))],
                   values2, kind)
    if few:
        return few
    labs = [str(x) for x in (labels or [])]
    vals: list[float] = []
    for v in (values or []):
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            return f"(values contains a nonnumeric item: {v!r})"
    if not labs or not vals or len(labs) != len(vals):
        return f"(labels and values must have equal lengths; received {len(labs)} labels and {len(vals)} values.)"


    all_vals = list(vals) + [float(v) for v in (values2 or []) if isinstance(v, (int, float))]


    near_text = "\n".join(tabular.sentences_with_numbers(text, _cursor(ctx))) or text
    bad = tabular.unsupported_numbers(near_text, all_vals)
    if not bad:


        bad = tabular.without_unit(near_text, all_vals, unit)
    if bad:
        pairs = ", ".join(f"{labs[vals.index(v)]}={v:g}" for v in bad if v in vals)
        return (f"(These values have no source in the prose near the cursor: {pairs}. "
                "Use only numbers actually present in sentences returned by numbers_near_cursor. "
                "Do not calculate, estimate or invent comparison values to fill a chart. "
                "Do not present approximate source wording as precise chart data.)")

    k = str(kind).lower()
    if k == "pie":
        return blocks.mermaid_pie(title, list(zip(labs, vals)))


    axis = f"{series} ({unit.strip()})" if unit.strip() else series
    return blocks.mermaid_xy(title, labs, vals, axis, kind="line" if k == "line" else "bar")


@register(
    name="render_chart", group="chart",
    description='Render an insertable Mermaid chart from data. Use the tool-generated syntax rather than writing Mermaid yourself. Supported kinds: pie, bar, line and flow. For flow, labels are ordered steps and values are unnecessary.',
    params={
        "kind": {"type": "string", "description": "pie / bar / line / flow"},
        "title": {"type": "string", "description": 'Chart title'},
        "labels": {"type": "array", "items": {"type": "string"},
                   "description": 'Ordered categories or flow steps'},
        "values": {"type": "array", "items": {"type": "number"},
                   "description": 'Corresponding values; omit for flow'},
        "series": {"type": "string", "description": 'Name of the first series, such as March or impressions'},
        "values2": {"type": "array", "items": {"type": "number"},
                    "description": 'Optional second series. For grouped comparisons, use categories on the x-axis and separate series for periods rather than flattening period-by-category pairs into one dimension.'},
        "series2": {"type": "string", "description": 'Name of the second series'},
        "kind2": {"type": "string", "description": 'Render the second series as bar or line. Keep units compatible; use separate charts for incompatible measurements.'},
    },
    required=["kind", "title", "labels"],
)
def render_chart(ctx: ToolContext, kind: str, title: str, labels: list,
                 values: list | None = None, series: str = "Value",
                 values2: list | None = None, series2: str = "Series 2",
                 kind2: str = "bar") -> str:
    labs = [str(x) for x in (labels or [])]
    vals: list[float] = []
    for v in (values or []):
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            vals.append(0.0)
    k = str(kind).lower()
    if k == "flow":
        return blocks.mermaid_flow(title, labs)
    if not vals:
        return '(This chart requires values: supply one per label. Use kind=flow only for a flow diagram.)'


    mixed = _mixed_unit(series)
    if mixed:
        return (f"(The unit {mixed} combines incompatible measurements. Keep compatible units together "
                "and split incompatible units into separate charts.)")
    clash = _unit_clash(ctx, vals)
    if clash:
        return clash
    few = _too_few(vals, values2, k)
    if few:
        return few
    if k == "pie":
        return blocks.mermaid_pie(title, list(zip(labs, vals)))
    return blocks.mermaid_xy(title, labs, vals, series,
                             kind="line" if k == "line" else "bar",
                             extra=_extra(values2, series2, kind2))


def _extra(values2, series2: str, kind2: str):
    """Render a second series only when the caller supplied it."""
    if not values2:
        return None
    out = []
    for v in values2:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(0.0)
    return [(str(series2 or 'Series 2'), out, str(kind2 or "bar"))]


@register(
    # Its own group, not "chart": building a table is not drawing. While it
    # lived under chart, every drawing mode was handed a table builder and
    # the table mode was handed three chart builders -- each one costing
    # prompt space and one more thing for the model to pick wrongly.
    name="render_table", group="table",
    description='Build an insertable Markdown table. Excess rows are truncated with a notice.',
    params={
        "columns": {"type": "array", "items": {"type": "string"}, "description": 'Column headers'},
        "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}},
                 "description": 'Cells in each row, in the same order as the headers'},
    },
    required=["columns", "rows"],
)
def render_table(ctx: ToolContext, columns: list, rows: list) -> str:
    cols = [str(c) for c in (columns or [])]
    body = [[str(c) for c in (r or [])] for r in (rows or []) if isinstance(r, (list, tuple))]
    if not cols:
        return '(columns must not be empty)'
    return blocks.markdown_table(cols, body)


@register(
    name="render_image", group="image", max_calls_per_round=1,
    description='Generate a conceptual illustration and return an insertable Markdown image reference. Use it for abstract concepts, scenes or cover artwork. For numeric charts or flow diagrams, use render_chart so the underlying data and structure remain explicit. Generation uses the configured image service and may take time or incur charges.',
    params={"prompt": {"type": "string",
                       "description": 'Describe the image, style, composition and required elements. Specify any text that must appear.'}},
    required=["prompt"],
)
async def render_image(ctx: ToolContext, prompt: str) -> str:
    from . import imagegen
    try:
        png, model = await imagegen.generate(str(prompt))
    except imagegen.ImageGenError as exc:
        return f"(Image generation failed: {exc})"
    url = imagegen.save(png)
    alt = str(prompt)[:60].replace("]", "").replace("\n", " ")
    return f"![{alt}]({url})\n\n> Generated by {model}"
