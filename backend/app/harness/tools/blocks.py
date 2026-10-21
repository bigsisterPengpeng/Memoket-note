"""Render Markdown tables and Mermaid diagrams with escaped labels and bounded sizes."""

from __future__ import annotations

import re


_LABEL_BAD = re.compile(r'["\'\[\]{}()<>;|\n\r]')


def safe_label(s: str, limit: int = 28) -> str:
    out = _LABEL_BAD.sub(" ", str(s)).strip()
    out = re.sub(r"\s+", " ", out)
    return (out[:limit] + "…") if len(out) > limit else (out or 'Untitled')


def markdown_table(columns: list[str], rows: list[list[str]], limit: int = 50) -> str:
    cols = [safe_label(c, 40).replace("|", "/") for c in columns] or ['Column']
    body = rows[:limit]
    lines = ["| " + " | ".join(cols) + " |",
             "|" + "---|" * len(cols)]
    for r in body:
        cells = [str(x).replace("|", "/").replace("\n", " ") for x in r[:len(cols)]]
        cells += [""] * (len(cols) - len(cells))
        lines.append("| " + " | ".join(cells) + " |")
    if len(rows) > limit:
        lines.append(f"\n> {len(rows)} rows total; showing the first {limit}.")
    return "\n".join(lines)


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{float(v):.4g}"


def mermaid_pie(title: str, data: list[tuple[str, float]], limit: int = 8) -> str:
    items = [(safe_label(k), float(v)) for k, v in data if float(v) > 0]
    items.sort(key=lambda kv: -kv[1])
    if len(items) > limit:
        rest = sum(v for _k, v in items[limit:])
        items = items[:limit] + [('Other', rest)]
    lines = [f'pie title {safe_label(title, 40)}']
    lines += [f'    "{k}" : {_fmt(v)}' for k, v in items]
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def mermaid_xy(title: str, labels: list[str], values: list[float],
               series: str = 'Value', kind: str = "bar", limit: int = 24,
               extra: list[tuple[str, list[float], str]] | None = None) -> str:
    n = min(len(labels), len(values), limit)


    cap = 24 if n <= 4 else (16 if n <= 8 else 10)
    xs = [safe_label(x, cap) for x in labels[:n]] or ['No data']
    ys = [float(v) for v in values[:n]] or [0.0]
    kind = "line" if kind == "line" else "bar"
    names = [series] + [nm for nm, _v, _k in (extra or [])]
    axis = f'    y-axis "{safe_label(" / ".join(names), 30)}"'
    if kind == "bar" or any(k != "line" for _nm, _v, k in (extra or [])):
        all_values = ys + [float(v) for _nm, vs, _k in (extra or []) for v in vs[:n]]
        lower, upper = min(0.0, *all_values), max(0.0, *all_values)
        axis += f" {_fmt(lower)} --> {_fmt(upper if upper > lower else lower + 1)}"
    lines = [
        "xychart-beta",
        f'    title "{safe_label(title, 40)}"',
        "    x-axis [" + ", ".join(f'"{x}"' for x in xs) + "]",

        axis,
        f"    {kind} [" + ", ".join(_fmt(v) for v in ys) + "]",
    ]
    for _nm, vs, k in (extra or []):
        vv = [float(v) for v in vs[:n]]
        vv += [0.0] * (n - len(vv))
        lines.append(f"    {'line' if k == 'line' else 'bar'} ["
                     + ", ".join(_fmt(v) for v in vv) + "]")
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def mermaid_flow(title: str, steps: list[str], kind: str = "LR") -> str:
    ids = [f"N{i}" for i in range(len(steps))]
    lines = [f"flowchart {'TD' if kind == 'TD' else 'LR'}"]
    if title:
        lines.insert(0, f"---\ntitle: {safe_label(title, 40)}\n---")
    for i, (nid, label) in enumerate(zip(ids, steps)):
        lines.append(f'    {nid}["{safe_label(label)}"]')
        if i:
            lines.append(f"    {ids[i - 1]} --> {nid}")
    return "```mermaid\n" + "\n".join(lines) + "\n```"
