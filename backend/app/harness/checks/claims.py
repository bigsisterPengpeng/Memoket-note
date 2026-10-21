"""Locate factual claims that require source support and produce bounded repair guidance."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..state import State
from ..types import Verdict
from . import numbers
from .pick import pick_dimension


_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;\n])")
_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.M)
_QUOTE_ROW = re.compile(r"^\s*>.*$", re.M)
_LINK = re.compile(r"!?\[[^\]]*\]\([^)]*\)")


_ANAPHOR = re.compile('\u8fd9(?:\u4e2a|\u4e9b|\u9879|\u6b21|\u4e00|\u7c7b|\u79cd|\u6761|\u6279)?|\u8be5(?:\u9879|\u6279|\u6761|\u65b9\u6848|\u4ea7\u54c1|\u529f\u80fd)?|\u5176(?:\u4e2d|\u4f59|\u4ed6|\u5b83)?|\u6b64(?:\u5916|\u524d|\u540e|\u5904)?|\u4e0a\u8ff0|\u524d\u8005|\u540e\u8005')


def _strip_uncheckable(text: str) -> str:
    t = _FENCE.sub(" ", text or "")
    t = _INLINE_CODE.sub(" ", t)
    t = _LINK.sub(" ", t)
    t = _TABLE_ROW.sub(" ", t)
    t = _QUOTE_ROW.sub(" ", t)
    return t


def decompose(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(_strip_uncheckable(text)) if s.strip()]


def has_anaphor(unit: str) -> bool:
    return bool(_ANAPHOR.search(unit or ""))


@dataclass(frozen=True)
class Atom:
    kind: str           # "date" / "attributed"
    surface: str
    key: object
    unit: str


_DATE_FULL = re.compile(
    '(?<![\\d])(\\d{4})\\s*[-/\u5e74.]\\s*(\\d{1,2})\\s*[-/\u6708.]\\s*(\\d{1,2})\\s*[\u65e5\u53f7]?(?![\\d])')


_DATE_YM = re.compile('(?<![\\d])(\\d{4})\\s*[-/\u5e74.]\\s*(\\d{1,2})(?![\\d:])')
_DATE_MD = re.compile('(?<![\\d])(\\d{1,2})\\s*\u6708\\s*(\\d{1,2})\\s*[\u65e5\u53f7](?![\\d])')


_SPEECH = ('(?:\u8bf4|\u8bb2\u8fc7|\u8bb2|\u63d0\u5230|\u63d0\u8fc7|\u8868\u793a|\u8ba4\u4e3a|\u6307\u51fa|\u5f3a\u8c03|\u786e\u8ba4|\u7b54\u590d|\u56de\u590d|\u5efa\u8bae|\u8981\u6c42|\u62cd\u677f|\u51b3\u5b9a|\u8d1f\u8d23|\u627f\u8bfa|\u53cd\u9988|\u95ee\u8fc7)')
_ATTRIBUTED = re.compile(
    rf"(?<![A-Za-z])([A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)?)\s*(?={_SPEECH})")


_NOT_A_NAME = {
    "owner", "app", "beta", "preview", "agent", "top", "team", "product",
    "design", "customer", "manufacturer", "insights", "note", "notes",
    "this", "that", "these", "those", "you", "we", "they", "it", "he", "she",
    "after", "before", "when", "while", "the", "and", "but", "for", "with",
    "ok", "yes", "no", "all", "one", "two", "some", "any", "new", "old",
}


def _date_key(y: int, mo: int, d: int) -> tuple[int, int, int]:
    return (y, mo, d)


def date_atoms(unit: str) -> list[Atom]:
    out: list[Atom] = []
    for m in _DATE_FULL.finditer(unit):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31 and 1900 <= y <= 2200):
            continue
        out.append(Atom("date", m.group(0).strip(), _date_key(y, mo, d), unit))
    return out


def _norm_name(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def attributed_atoms(unit: str) -> list[Atom]:
    out: list[Atom] = []
    for m in _ATTRIBUTED.finditer(unit):
        name = _norm_name(m.group(1))
        if name.lower() in _NOT_A_NAME:
            continue
        if len(name.replace(" ", "")) < 2:
            continue
        out.append(Atom("attributed", name, name.lower(), unit))
    return out


def atoms(text: str) -> list[Atom]:
    out: list[Atom] = []
    for unit in decompose(text):
        out += date_atoms(unit)
        out += attributed_atoms(unit)
    return out


def relevant(atoms_: list[Atom]) -> list[Atom]:
    seen: set[tuple[str, object]] = set()
    out: list[Atom] = []
    for a in atoms_:
        sig = (a.kind, a.key)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(a)
    return out


def source_keys(text: str) -> dict[str, set]:
    dates: set[tuple[int, int, int]] = set()
    body = text or ""
    for m in _DATE_FULL.finditer(body):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        dates |= {(y, mo, d), (y, mo, 0), (0, mo, d)}
    for m in _DATE_YM.finditer(body):
        dates.add((int(m.group(1)), int(m.group(2)), 0))
    for m in _DATE_MD.finditer(body):
        dates.add((0, int(m.group(1)), int(m.group(2))))
    return {"date": dates, "text": {re.sub(r"\s+", " ", body).lower()}}


def supported(atom: Atom, keys: dict[str, set]) -> bool:
    if atom.kind == "date":
        y, mo, d = atom.key                     # type: ignore[misc]
        pool = keys.get("date") or set()
        return (y, mo, d) in pool or (y, mo, 0) in pool
    blob = next(iter(keys.get("text") or {""}))
    return str(atom.key) in blob


MIN_FRESH_CHARS = 120

MAX_REPORT = 3


def fresh_text(st: State) -> str:
    return (st.fresh or "").strip()


def sources(st: State) -> str:
    prior = st.content or ""
    fresh = st.fresh or ""
    if fresh and prior.endswith(fresh):
        prior = prior[: len(prior) - len(fresh)]
    elif fresh and fresh in prior:

        prior = prior.replace(fresh, " ")
    return numbers.sources(st) + "\n" + prior


# |---|---|


NOT_IN_MODE = "not_in_mode"
TOO_SHORT = "too_short"
NO_ORACLE = "no_oracle"
NO_ATOMS = "no_atoms"
JUDGED = "judged"


def probe(st: State) -> tuple[list[Atom], str]:
    text = fresh_text(st)
    cands = relevant(atoms(text))
    if len(text) < MIN_FRESH_CHARS:
        return cands, TOO_SHORT
    if not numbers.has_tool_output(st):
        return cands, NO_ORACLE
    if not cands:
        return cands, NO_ATOMS
    return cands, JUDGED


def unsupported_specifics(st: State) -> Verdict | None:
    cands, why = probe(st)
    if why != JUDGED:
        return None
    keys = source_keys(sources(st))
    bad = [a for a in cands if not supported(a, keys)]
    if not bad:
        return None
    lines = []
    for a in bad[:MAX_REPORT]:
        unit = a.unit if len(a.unit) <= 60 else a.unit[:60] + "…"
        lines.append(f'"{a.surface}" (in: {unit})')
    more = f', plus {len(bad) - MAX_REPORT} other unlocated claims' if len(bad) > MAX_REPORT else ""


    return Verdict(
        pick_dimension(st, "factual_grounding", "no_fabrication", "material_use"),
        'Needs verification: these concrete claims from this round have no located source in the retrieved material: '
        + "；".join(lines) + more + '. A missing match is not counterevidence. Retain the original names and dates. The user may supply sources, or later retrieval may locate them. Change the body only when an explicit contradiction is found, and leave unrelated sentences intact.',
        advisory=True,
    )
