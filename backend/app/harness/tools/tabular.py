"""Parse note-local tables and calculate deterministic summaries, aggregations and distributions."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


_MD_TABLE = re.compile(
    r"(?:^\|.*\|[ \t]*\n)"
    r"(?:^\|[\s:|-]+\|[ \t]*\n)"
    r"(?:^\|.*\|[ \t]*\n?)+",
    re.M)

_FENCED = re.compile(r"^```(csv|tsv)[ \t]*\n(.*?)^```", re.M | re.S)
_NUM = re.compile(r"^-?[\d,]+(?:\.\d+)?%?$")


@dataclass
class Table:
    index: int
    source: str                 # markdown / csv / tsv
    columns: list[str]
    rows: list[list[str]]
    start: int = 0
    end: int = 0

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.rows), len(self.columns)

    def column(self, name: str) -> list[str]:
        if name not in self.columns:
            raise KeyError(name)
        i = self.columns.index(name)
        return [r[i] if i < len(r) else "" for r in self.rows]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def find_tables(text: str) -> list[Table]:
    out: list[Table] = []
    for m in _MD_TABLE.finditer(text or ""):
        lines = [ln for ln in m.group(0).splitlines() if ln.strip()]
        if len(lines) < 3:
            continue
        cols = _cells(lines[0])
        rows = [_cells(ln) for ln in lines[2:]]
        rows = [r for r in rows if any(c for c in r)]
        if cols and rows:
            out.append(Table(len(out), "markdown", cols, rows, m.start(), m.end()))
    for m in _FENCED.finditer(text or ""):
        sep = "\t" if m.group(1) == "tsv" else ","
        lines = [ln for ln in m.group(2).splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        cols = [c.strip() for c in lines[0].split(sep)]
        rows = [[c.strip() for c in ln.split(sep)] for ln in lines[1:]]
        out.append(Table(len(out), m.group(1), cols, rows, m.start(), m.end()))
    return out


def to_number(cell: str) -> float | None:
    s = (cell or "").strip()
    if not s or not _NUM.match(s):
        return None
    try:
        return float(s.rstrip("%").replace(",", ""))
    except ValueError:
        return None


def numeric(values: list[str]) -> list[float]:
    return [v for v in (to_number(x) for x in values) if v is not None]


def is_numeric_column(values: list[str]) -> bool:
    filled = [v for v in values if (v or "").strip()]
    if not filled:
        return False
    return len(numeric(filled)) * 2 >= len(filled)


def quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return math.nan
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def describe_column(name: str, values: list[str]) -> dict:
    """Summarize numeric or categorical values with explicit missing counts."""
    filled = [v for v in values if (v or "").strip()]
    base = {'column': name, 'rows': len(values), 'missing': len(values) - len(filled)}
    if is_numeric_column(values):
        nums = sorted(numeric(filled))
        n = len(nums)
        mean = sum(nums) / n
        var = sum((x - mean) ** 2 for x in nums) / n if n > 1 else 0.0
        return {**base, 'type': 'numeric', 'valid': n, 'min': nums[0], 'max': nums[-1],
                'mean': round(mean, 4), 'median': round(quantile(nums, 0.5), 4),
                "P25": round(quantile(nums, 0.25), 4), "P75": round(quantile(nums, 0.75), 4),
                'stddev': round(math.sqrt(var), 4), 'sum': round(sum(nums), 4)}
    counts: dict[str, int] = {}
    for v in filled:
        counts[v] = counts.get(v, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {**base, 'type': 'text', 'distinct': len(counts),
            'top_values': [{'value': k, 'count': v} for k, v in top]}


AGGS = ("sum", "mean", "count", "max", "min", "median")


def aggregate(table: Table, group_by: str, value: str, agg: str) -> list[tuple[str, float]]:
    if agg not in AGGS:
        raise ValueError(f"Unsupported aggregation {agg!r}; supported: {', '.join(AGGS)}")
    keys = table.column(group_by)
    vals = table.column(value)
    buckets: dict[str, list[float]] = {}
    for k, v in zip(keys, vals):
        key = (k or "").strip() or '(empty)'
        if agg == "count":
            buckets.setdefault(key, []).append(1.0)
            continue
        num = to_number(v)
        if num is not None:
            buckets.setdefault(key, []).append(num)
    out: list[tuple[str, float]] = []
    for k, xs in buckets.items():
        if not xs:
            continue
        if agg in ("sum", "count"):
            r = sum(xs)
        elif agg == "mean":
            r = sum(xs) / len(xs)
        elif agg == "max":
            r = max(xs)
        elif agg == "min":
            r = min(xs)
        else:
            r = quantile(sorted(xs), 0.5)
        out.append((k, round(r, 4)))
    return sorted(out, key=lambda kv: -kv[1])


def correlate(table: Table, x: str, y: str) -> dict:
    """Calculate Pearson correlation using only rows with both numeric values."""
    xs_raw, ys_raw = table.column(x), table.column(y)
    pairs = [(a, b) for a, b in ((to_number(p), to_number(q)) for p, q in zip(xs_raw, ys_raw))
             if a is not None and b is not None]
    n = len(pairs)
    if n < 3:
        return {"x": x, "y": y, "n": n, "r": None,
                'note': 'Fewer than three rows have numeric values in both columns; correlation is not meaningful.'}
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    cov = sum((a - mx) * (b - my) for a, b in pairs)
    vx = math.sqrt(sum((a - mx) ** 2 for a, _ in pairs))
    vy = math.sqrt(sum((b - my) ** 2 for _, b in pairs))
    if not vx or not vy:
        return {"x": x, "y": y, "n": n, "r": None, 'note': 'One column has no variation; correlation is undefined.'}
    return {"x": x, "y": y, "n": n, "r": round(cov / (vx * vy), 4)}


def histogram(values: list[str], bins: int = 8) -> tuple[list[str], list[float]]:
    """Bin numeric values into a bounded distribution without model arithmetic."""
    nums = sorted(numeric(values))
    if len(nums) < 2:
        return [], []
    lo, hi = nums[0], nums[-1]
    if hi == lo:
        return [_fmt_edge(lo)], [float(len(nums))]
    n = max(2, min(bins, int(len(nums) ** 0.5) if len(nums) < bins * 2 else bins))
    step = (hi - lo) / n
    counts = [0.0] * n
    for v in nums:
        idx = min(n - 1, int((v - lo) / step))
        counts[idx] += 1
    labels = [f"{_fmt_edge(lo + i * step)}~{_fmt_edge(lo + (i + 1) * step)}" for i in range(n)]
    return labels, counts


def _fmt_edge(v: float) -> str:
    a = abs(v)
    if a >= 1_000_000:
        return f"{v / 1_000_000:.1f}M".replace(".0M", "M")
    if a >= 1000:
        return f"{v / 1000:.1f}k".replace(".0k", "k")
    return str(int(v)) if float(v).is_integer() else f"{v:.4g}"


def nearest(tables: list[Table], cursor: int) -> Table | None:
    if not tables:
        return None
    def dist(t: Table) -> int:
        if t.start <= cursor <= t.end:
            return 0
        return t.start - cursor if cursor < t.start else cursor - t.end
    return min(tables, key=dist)


def distance(t: Table, cursor: int) -> int:
    if t.start <= cursor <= t.end:
        return 0
    return t.start - cursor if cursor < t.start else cursor - t.end


_UNITS = {'\u4e07': 1e4, '\u842c': 1e4, '\u4ebf': 1e8, '\u5104': 1e8, '\u5343': 1e3, '\u767e': 1e2,
          "k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6, "w": 1e4, "W": 1e4}
_TEXT_NUM = re.compile('(-?\\d[\\d,]*(?:\\.\\d+)?)\\s*([\u4e07\u842c\u4ebf\u5104\u5343\u767ekKmMwW])?')


def numbers_in_text(text: str) -> set[float]:
    """Normalize source numerals for chart-value verification."""
    out: set[float] = set()
    for m in _TEXT_NUM.finditer(text or ""):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        out.add(v)
        if m.group(2):
            out.add(v * _UNITS[m.group(2)])
    return out


def unsupported_numbers(text: str, values: list[float], *, rel: float = 0.005) -> list[float]:
    have = numbers_in_text(text)
    bad: list[float] = []
    for v in values:
        if any(abs(v - h) <= max(rel * abs(v), 1e-9) for h in have):
            continue
        bad.append(v)
    return bad


_SENT_END = re.compile(r"[。！？；!?;]+|\n+")


_NOT_A_QUANTITY = (
    re.compile(r"\[[A-Za-z][A-Za-z0-9_-]*-(?:\d+|[0-9a-f]{12})-[0-9A-Fa-f]+\]"),
    re.compile(r"https?://\S+"),
    re.compile('\\d{4}\\s*[-/\u5e74.]\\s*\\d{1,2}(?:\\s*[-/\u6708.]\\s*\\d{1,2}\\s*\u65e5?)?'),
    re.compile('\\d{1,2}\\s*\u6708\\s*\\d{1,2}\\s*[\u65e5\u53f7]?'),
    re.compile('\\d{1,2}\\s*[\u65e5\u53f7]\\b|\\d{1,2}\\s*[\u65e5\u53f7](?=[^\\d])'),
    re.compile('\u7b2c\\s*\\d+(?:\\s*[\u3001,\uff0c/\u548c\u53ca]\\s*\\d+)*'),
    re.compile(r"[A-Za-z]+\d+[A-Za-z0-9]*"),                                        # Q3、iOS16、F1
)


def has_quantity(sentence: str) -> bool:
    s = sentence
    for pat in _NOT_A_QUANTITY:
        s = pat.sub(" ", s)
    return any(ch.isdigit() for ch in s)


def sentences_with_numbers(text: str, cursor: int, radius: int = 1200) -> list[str]:
    text = text or ""
    if not text.strip():
        return []
    lo, hi = max(0, cursor - radius), min(len(text), cursor + radius)
    spans = [(tb.start, tb.end) for tb in find_tables(text)]


    bounds = [lo]
    for m in _SENT_END.finditer(text, lo, hi):
        bounds.append(m.end())
    bounds.append(hi)

    out: list[tuple[int, str]] = []
    for a, b in zip(bounds, bounds[1:]):
        if b <= a:
            continue
        s = text[a:b].strip()
        if len(s) < 6 or not has_quantity(s):
            continue
        if any(ts <= a <= te for ts, te in spans):
            continue
        d = 0 if a <= cursor <= b else min(abs(cursor - a), abs(cursor - b))
        out.append((d, s))
    out.sort(key=lambda x: x[0])
    seen: list[str] = []
    for _d, s in out:
        if s not in seen:
            seen.append(s)
    return seen


_UNIT_AFTER = re.compile(r"\s*(%|％|[\u4e00-\u9fffA-Za-z]{1,4})")


def unit_near(text: str, value: float, cursor: int, *, rel: float = 0.005) -> str:
    best, bestd = "", None
    for m in _TEXT_NUM.finditer(text or ""):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if m.group(2):
            v *= _UNITS[m.group(2)]
        if abs(v - value) > max(rel * abs(value), 1e-9):
            continue
        d = abs(m.start() - cursor)
        if bestd is None or d < bestd:
            u = _UNIT_AFTER.match(text, m.end())
            best, bestd = (u.group(1) if u else ""), d
    return best


def mixed_units(text: str, values: list[float], cursor: int) -> dict[str, list[float]]:
    by: dict[str, list[float]] = {}
    for v in values:
        u = unit_near(text, v, cursor)
        if u:
            by.setdefault(u, []).append(v)
    return by if len(by) > 1 else {}


_MD_HEADING = re.compile(r"^#{1,6} ", re.M)


def headings_between(text: str, cursor: int, start: int, end: int) -> int:
    lo, hi = (cursor, start) if cursor < start else (end, cursor)
    if hi <= lo:
        return 0
    return len(_MD_HEADING.findall(text or "", lo, hi))


def _sentence_span(text: str, pos: int) -> tuple[int, int]:
    a = 0
    for m in _SENT_END.finditer(text, 0, pos):
        a = m.end()
    m2 = _SENT_END.search(text, pos)
    return a, (m2.end() if m2 else len(text))


def _occurrences(text: str, value: float, rel: float) -> list[tuple[int, str]]:
    out = []
    for m in _TEXT_NUM.finditer(text or ""):
        try:
            got = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if m.group(2):
            got *= _UNITS[m.group(2)]
        if abs(got - value) > max(rel * abs(value), 1e-9):
            continue
        a = _UNIT_AFTER.match(text, m.end())
        out.append((m.start(), a.group(1) if a else ""))
    return out


def without_unit(text: str, values: list[float], unit: str,
                 *, rel: float = 0.005) -> list[float]:
    u = (unit or "").strip()
    if not u:
        return []
    occ = {v: _occurrences(text, v, rel) for v in values}
    spans = [_sentence_span(text, pos) for v in values
             for pos, got in occ[v] if got == u]


    if not spans:
        return []
    bad = []
    for v in values:
        if any(got == u for _p, got in occ[v]):
            continue
        if any(a <= p <= b for p, _g in occ[v] for a, b in spans):
            continue
        bad.append(v)
    return bad
