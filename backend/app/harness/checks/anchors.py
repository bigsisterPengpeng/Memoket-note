"""Conservative specificity signals for advisory prose checks.

These signals do not establish factual support. English prose needs more than
the presence of an ordinary Latin word; mixed CJK prose retains its Latin-name
signal for compatibility with existing notes.
"""

import re


_QUOTED_OR_NUMBER = re.compile(r'\d|[`“"\u300c\u300e\u300a][^`”"\u300d\u300f\u300b]{2,}[`”"\u300d\u300f\u300b]')
_LATIN = re.compile(r"[A-Za-z]{2,}")
_CJK = re.compile(r"[\u3400-\u9fff]")
_IDENTIFIER = re.compile(r"\b(?:[A-Z]{2,}|[a-z]+[A-Z][A-Za-z]*|[\w-]+[./_#][\w./#-]+)\b")
_PROPER_NAME = re.compile(r"(?<=\s)[A-Z][a-z]+\b")


def has_concrete_anchor(text: str) -> bool:
    if _QUOTED_OR_NUMBER.search(text):
        return True
    if _CJK.search(text):
        return bool(_LATIN.search(text))
    return bool(_IDENTIFIER.search(text) or _PROPER_NAME.search(text))
