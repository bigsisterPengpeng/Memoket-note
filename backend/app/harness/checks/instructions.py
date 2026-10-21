"""Deterministic checks for explicit user instructions that can be validated from the body."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..state import State
from ..types import Verdict
from . import blockcheck
from .pick import pick_dimension


TOLERANCE = 0.1


MAX_CONSTRAINTS = 5

_CN_NUM = {'\u4e24': 2, '\u4e8c': 2, '\u4e09': 3, '\u56db': 4, '\u4e94': 5,
           '\u516d': 6, '\u4e03': 7, '\u516b': 8, '\u4e5d': 9, '\u5341': 10}


_NUM = '(\\d{1,4}|[\u4e24\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341])'


_COUNT_RANGE = (2, 12)


_CHARS_RANGE = (10, 5000)


_NEG_BEFORE = re.compile(
    '(?:\u4e0d\u8981|\u4e0d\u7528|\u4e0d\u5fc5|\u65e0\u9700|\u4e0d\u8bb8|\u4e0d\u80fd|\u522b|\u52ff|\u7981\u6b62|\u907f\u514d|\u4e0d\u5f97|\u6ca1\u5fc5\u8981|\u65e0\u987b)\\s*$')


_PER_UNIT_BEFORE = re.compile('(?:\u6bcf|\u5404)(?:\u6bb5|\u70b9|\u6761|\u90e8\u5206|\u4e2a|\u7bc7|\u884c|\u9879|\u8282|\u53e5)\\s*$')

_QUOTE_OPEN = "「『“\"'"
_QUOTE_CLOSE = "」』”\"'"


_PATTERNS: tuple[tuple[str, str], ...] = (

    ("max_chars", f'(?:\u4e0d\u8d85\u8fc7|\u4e0d\u591a\u4e8e|\u6700\u591a|\u522b\u8d85\u8fc7|\u4e0d\u8981\u8d85\u8fc7)\\s*(?:\u5199|\u5199\u5230|\u7ed9|\u8f93\u51fa)?\\s*{_NUM}\\s*(?:\u4e2a)?\u5b57'),
    ("max_chars", f'{_NUM}\\s*(?:\u4e2a)?\u5b57(?:\u4ee5\u5185|\u4e4b\u5185|\u4ee5\u4e0b)'),
    ("min_chars", f'(?:\u81f3\u5c11|\u4e0d\u5c11\u4e8e|\u4e0d\u4f4e\u4e8e|\u6700\u5c11)\\s*(?:\u5199|\u5199\u5230|\u7ed9|\u8f93\u51fa)?\\s*{_NUM}\\s*(?:\u4e2a)?\u5b57'),
    ("min_chars", f'{_NUM}\\s*(?:\u4e2a)?\u5b57\u4ee5\u4e0a'),
    ("min_bullets",
     f'(?:\u5206|\u5217|\u5199|\u7ed9|\u603b\u7ed3|\u5f52\u7eb3|\u6982\u62ec)(?:\u6210|\u51fa)?\\s*{_NUM}\\s*(?:\u70b9|\u6761)(?![0-9])'),
    ("min_paragraphs", f'(?:\u5206|\u5199|\u62c6)(?:\u6210|\u4e3a)?\\s*{_NUM}\\s*(?:\u4e2a)?\u6bb5(?:\u843d)?'),


    ("table", '(?:\u7528|\u505a\u6210|\u6574\u7406\u6210|\u6539\u6210|\u8f93\u51fa\u6210|\u4ee5)\\s*(?:markdown\\s*|\u4e00\u5f20\\s*)?\u8868\u683c'),
    ("table", '\u8868\u683c(?:\u5f62\u5f0f|\u5448\u73b0)'),
)


_MENTION = re.compile(
    f'(?:\u5fc5\u987b|\u4e00\u5b9a|\u8bb0\u5f97|\u9700\u8981|\u52a1\u5fc5|\u8981|\u8bf7)?\\s*(?:\u63d0\u5230|\u63d0\u53ca|\u5305\u542b|\u5199\u4e0a|\u52a0\u4e0a|\u5e26\u4e0a|\u51fa\u73b0)\\s*[{_QUOTE_OPEN}]([^{_QUOTE_CLOSE}\\n]{{1,30}})[{_QUOTE_CLOSE}]')
_NOT_MENTION = re.compile(
    f'(?:\u4e0d\u8981|\u4e0d\u8bb8|\u4e0d\u80fd|\u522b|\u7981\u6b62|\u907f\u514d|\u4e0d\u5f97|\u52ff)\\s*(?:\u63d0\u5230|\u63d0\u53ca|\u5305\u542b|\u51fa\u73b0|\u5199|\u7528|\u4f7f\u7528)\\s*[{_QUOTE_OPEN}]([^{_QUOTE_CLOSE}\\n]{{1,30}})[{_QUOTE_CLOSE}]')


_UNIQUE_KINDS = ("max_chars", "min_chars", "min_bullets", "min_paragraphs", "table")


@dataclass(frozen=True)
class Constraint:
    kind: str
    value: str
    source: str


def _num(raw: str) -> int | None:
    raw = (raw or "").strip()
    if raw.isdigit():
        return int(raw)
    return _CN_NUM.get(raw)


def _in_range(kind: str, n: int) -> bool:
    lo, hi = _CHARS_RANGE if kind.endswith("chars") else _COUNT_RANGE
    return lo <= n <= hi


def extract(instruction: str) -> tuple[Constraint, ...]:
    text = (instruction or "").strip()
    if not text:
        return ()

    found: list[Constraint] = []
    for kind, pattern in _PATTERNS:
        for m in re.finditer(pattern, text):
            before = text[max(0, m.start() - 6):m.start()]
            if _NEG_BEFORE.search(before) or _PER_UNIT_BEFORE.search(before):
                continue
            if kind == "table":
                found.append(Constraint(kind, "1", m.group(0)))
                continue
            n = _num(m.group(1))
            if n is None or not _in_range(kind, n):
                continue
            found.append(Constraint(kind, str(n), m.group(0)))

    for m in _NOT_MENTION.finditer(text):
        found.append(Constraint("must_not_mention", m.group(1).strip(), m.group(0)))
    banned = {c.value for c in found if c.kind == "must_not_mention"}
    for m in _MENTION.finditer(text):
        word = m.group(1).strip()


        if word in banned or _NEG_BEFORE.search(text[max(0, m.start() - 6):m.start()]):
            continue
        if word:
            found.append(Constraint("must_mention", word, m.group(0)))

    return _resolve(found)


def _resolve(found: list[Constraint]) -> tuple[Constraint, ...]:
    out: list[Constraint] = []
    seen: set[tuple[str, str]] = set()
    values: dict[str, set[str]] = {}
    for c in found:
        values.setdefault(c.kind, set()).add(c.value)
    bad_kinds = {k for k in _UNIQUE_KINDS if len(values.get(k, ())) > 1}

    lo = next(iter(values.get("min_chars", ())), None)
    hi = next(iter(values.get("max_chars", ())), None)
    if lo and hi and int(lo) > int(hi):
        bad_kinds |= {"min_chars", "max_chars"}
    for c in found:
        if c.kind in bad_kinds or (c.kind, c.value) in seen:
            continue
        seen.add((c.kind, c.value))
        out.append(c)
    return tuple(out[:MAX_CONSTRAINTS])


_FENCE = re.compile(r"```.*?```", re.S)
_BULLET = re.compile('^\\s*(?:[-*+]|\\d{1,2}[.\u3001)]|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+[\u3001.])\\s+', re.M)
_CJK = re.compile('[\u4e00-\u9fff]')
_LATIN_WORD = re.compile(r"[A-Za-z0-9]+")
_SPACE = re.compile(r"\s+")


def _body(text: str) -> str:
    return _FENCE.sub("\n", text or "")


def count_chars(text: str) -> int | None:
    body = _body(text)
    n = len(_CJK.findall(body)) + len(_LATIN_WORD.findall(body))
    return n or None


def count_units(text: str) -> int:
    body = _body(text)
    bullets = len(_BULLET.findall(body))
    paras = len([p for p in re.split(r"\n\s*\n", body) if p.strip()])
    return max(bullets, paras)


def _norm(text: str) -> str:
    return _SPACE.sub("", (text or "")).lower()


def verify(c: Constraint, text: str) -> bool | None:
    body = _body(text)
    if not (text or "").strip() or not body.strip():
        return None
    if c.kind in ("max_chars", "min_chars"):
        n = count_chars(text)
        if n is None:
            return None
        want = int(c.value)
        if c.kind == "max_chars":
            return n <= want * (1 + TOLERANCE)
        return n >= want * (1 - TOLERANCE)
    if c.kind in ("min_bullets", "min_paragraphs"):
        return count_units(text) >= int(c.value)
    if c.kind == "table":
        return blockcheck.has_table(text)
    if c.kind == "must_mention":
        return _norm(c.value) in _norm(text)
    if c.kind == "must_not_mention":
        return _norm(c.value) not in _norm(text)
    return None


def failure(c: Constraint, text: str) -> str:
    prefix = f'The user requested "{c.source}". '
    if c.kind == "max_chars":
        return prefix + f"The draft has {count_chars(text)} characters. Reduce it to at most {c.value} characters while preserving informative sentences."
    if c.kind == "min_chars":
        return prefix + f"The draft has only {count_chars(text)} characters. Reach {c.value} characters with useful content, without padding."
    if c.kind in ("min_bullets", "min_paragraphs"):
        unit = "bullets" if c.kind == "min_bullets" else "paragraphs"
        return prefix + f"The draft has {count_units(text)} {unit}; provide at least {c.value}."
    if c.kind == "table":
        return prefix + "The draft has no Markdown table with a header and separator row."
    if c.kind == "must_mention":
        return prefix + f'The draft does not mention "{c.value}".'
    if c.kind == "must_not_mention":
        return prefix + f'The draft contains the prohibited text "{c.value}".'
    return prefix + "The draft does not meet this constraint."


def instruction_constraints(st: State) -> Verdict | None:
    constraints = tuple(st.bag.get("prompt_constraints") or ())
    if not constraints:
        return None
    for c in constraints:
        if not isinstance(c, Constraint):
            continue
        if verify(c, st.content) is False:
            return Verdict(dimension=pick_dimension(st, "follows_prompt"),
                           message=failure(c, st.content))
    return None
