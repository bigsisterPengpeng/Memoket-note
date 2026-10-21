"""Deterministic extraction validation and conservative normalization against supplied source text."""

from __future__ import annotations

import re

# Digit runs, keeping decimals and comma grouping together. Splitting
# ``10,000`` into ``10`` and ``000`` was a measured false positive.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Anything date-shaped, so a date written inside the sentence does not
# contribute its parts as free-floating numbers to check.
_DATE = re.compile('\\d{4}\\s*[-\u5e74/]\\s*\\d{1,2}(?:\\s*[-\u6708/]\\s*\\d{1,2})?\\s*\u65e5?')

# One-digit numbers are noise: "1" appears in almost any long source text by
# accident, so its presence proves nothing either way.
MIN_DIGITS = 2

# Chinese numerals, for sources that spell figures out. Deliberately only the
# small ones -- a general converter would be a project, and the measured

_CN_DIGIT = {'\u96f6': 0, "〇": 0, '\u4e00': 1, '\u4e8c': 2, '\u4e24': 2, '\u4e09': 3, '\u56db': 4,
             '\u4e94': 5, '\u516d': 6, '\u4e03': 7, '\u516b': 8, '\u4e5d': 9}
_CN_RUN = re.compile('[\u96f6\u3007\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]{1,3}')


def numbers_without_source(fact_text: str, source_text: str,
                           when: str = "") -> list[str]:
    if not fact_text or not source_text:
        return []

    known = set(_NUMBER.findall(source_text))
    known |= {n.replace(",", "") for n in known}
    known |= _chinese_numbers(source_text)
    known |= set(re.findall(r"\d+", when or ""))

    # A date inside the fact is one token, not three numbers.
    body = _DATE.sub(" ", fact_text)

    missing = []
    for raw in _NUMBER.findall(body):
        plain = raw.replace(",", "")
        if len(plain.replace(".", "")) < MIN_DIGITS:
            continue
        if raw in known or plain in known:
            continue
        if plain not in missing:
            missing.append(plain)
    return missing


def rate(facts, lines_by_unit: dict[str, str]) -> dict:
    """The unsupported-number rate over a batch of facts.

    Reported as a fraction of the facts that *could* be checked -- ones that
    contain a number and whose source text is available. Reporting it over
    every fact would hide a bad batch inside a pile of facts with no numbers
    in them.
    """
    checked = flagged = 0
    examples: list[dict] = []
    for fact in facts:
        source = lines_by_unit.get(getattr(fact, "unit", ""), "")
        text = getattr(fact, "text", "") or ""
        if not source or not _NUMBER.search(text):
            continue
        checked += 1
        missing = numbers_without_source(text, source, getattr(fact, "when", ""))
        if missing:
            flagged += 1
            if len(examples) < 10:
                examples.append({"id": getattr(fact, "id", ""),
                                 "numbers": missing, "text": text[:200]})
    return {"checked": checked, "flagged": flagged,
            "rate": round(flagged / checked, 3) if checked else 0.0,
            "examples": examples}


def _chinese_numbers(text: str) -> set[str]:
    """Small Chinese numerals as their digit form."""
    out: set[str] = set()
    for match in _CN_RUN.finditer(text):
        value = _value_of(match.group(0))
        if value is not None:
            out.add(str(value))
    return out


def _value_of(run: str) -> int | None:
    if run in _CN_DIGIT:
        return _CN_DIGIT[run]
    if run == '\u5341':
        return 10
    if len(run) == 2 and run[0] == '\u5341':
        return 10 + _CN_DIGIT.get(run[1], 0)
    if len(run) == 2 and run[1] == '\u5341':
        return _CN_DIGIT.get(run[0], 0) * 10
    if len(run) == 3 and run[1] == '\u5341':
        return _CN_DIGIT.get(run[0], 0) * 10 + _CN_DIGIT.get(run[2], 0)
    return None


# ---------------------------------------------------------------- shape ---

# Below this a fact cannot carry what it needs to (what happened, to what,
# with which constraint). Measured against real output: the source codebook
# has 1699 facts shorter than this, most of them noun phrases.
MIN_USEFUL_CHARS = 16

_FILLER = re.compile('(\u90a3\u4e2a\u90a3\u4e2a|\u5c31\u662f\u5c31\u662f|\u4ed6\u4ed6\u4ed6|\u8981\u8981|\u55ef\u55ef|\u5443\u5443|\u6211\u8bf4\u90a3\u4e2a|\u8fd9\u4e2a\u8fd9\u4e2a)')

# A fact whose whole content is "Speaker B said <a few words>". The label is
# useless (it names a different person next session) and what remains is too
# little to write from.
_SPEAKER_ONLY = re.compile('^Speaker [A-Z] ?(\u8bf4|\u8868\u793a|\u8ba4\u4e3a|\u63d0\u5230)?\\s*[\u300c\\"\\\']?.{0,12}[\u300d\\"\\\']?$')

# The label anywhere in the content, which the extraction rules forbid
# outright: attribution belongs in the ``who`` field.
_SPEAKER_LABEL = re.compile(r"Speaker [A-Z]")


def unusable_shape(text: str) -> str | None:
    if len(text) < MIN_USEFUL_CHARS:
        return 'Too short'
    if _FILLER.search(text):
        return 'Filler or transcription noise'
    if text.rstrip().endswith(("？", "?")):
        return 'Question rather than a fact'
    if _SPEAKER_ONLY.match(text):
        return 'Only a speaker label and a short phrase'
    return None


def shapes(facts) -> dict:
    """How many facts are the wrong shape to write from, and which way.

    Separate from ``rate`` because it needs no source text: shape is decidable
    from the fact alone, so this runs over a whole codebook in milliseconds.
    """
    reasons: dict[str, int] = {}
    labelled = 0
    total = 0
    for fact in facts:
        text = (getattr(fact, "text", "") or "").strip()
        if not text:
            continue
        total += 1
        why = unusable_shape(text)
        if why:
            reasons[why] = reasons.get(why, 0) + 1
        if _SPEAKER_LABEL.search(text):
            labelled += 1
    unusable = sum(reasons.values())
    return {
        "facts": total,
        "unusable": unusable,
        "unusable_rate": round(unusable / total, 3) if total else 0.0,
        "reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),


        "speaker_labels": labelled,
        "speaker_label_rate": round(labelled / total, 3) if total else 0.0,
    }
