"""Reversible entity-group presentation and explicit merge/drop decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .entities import norm_key
from .who import is_speaker_tag


MIN_FACTS = 5


TRANSLIT_MIN = 0.62


SPELL_MIN = 0.85


MIN_SUB_CJK = 2
MIN_SUB_LATIN = 5
MIN_SUB_RATIO = 0.5

_CJK = re.compile('[\u4e00-\u9fff]')
_SPLIT = re.compile(r"[\s_\-.·]+")


def has_cjk(s: str) -> bool:
    return bool(_CJK.search(s or ""))


def initials(s: str) -> str:
    return "".join(w[0] for w in _SPLIT.split(s or "") if w).lower()


def roman(s: str, pinyin=None) -> str:
    s = s or ""
    if not has_cjk(s):
        return norm_key(s)
    if pinyin is None:
        from pypinyin import lazy_pinyin
        pinyin = lazy_pinyin
    return "".join(pinyin(s)).lower()


@dataclass(frozen=True)
class Candidate:
    a: str
    b: str
    why: str
    score: float
    facts_a: int
    facts_b: int

    @property
    def facts_total(self) -> int:
        return self.facts_a + self.facts_b


def _pair(a_name: str, b_name: str, pinyin=None) -> tuple[str, float] | None:
    na, nb = norm_key(a_name), norm_key(b_name)
    if not na or not nb or na == nb:
        return None
    if na in nb or nb in na:
        short, long_ = sorted((na, nb), key=len)
        ratio = len(short) / len(long_)


        min_len = MIN_SUB_CJK if (has_cjk(short) or has_cjk(long_)) else MIN_SUB_LATIN
        if len(short) >= min_len and ratio >= MIN_SUB_RATIO:
            return "substring", round(ratio, 3)
    if (len(na) >= 2 and na == initials(b_name)) or (len(nb) >= 2 and nb == initials(a_name)):
        return "initials", 1.0


    if has_cjk(a_name) or has_cjk(b_name):
        ra, rb = roman(a_name, pinyin), roman(b_name, pinyin)
        if ra and rb:
            r = SequenceMatcher(None, ra, rb).ratio()
            if r >= TRANSLIT_MIN:
                return "translit", round(r, 3)


    elif len(na) >= 4 and len(nb) >= 4:
        r = SequenceMatcher(None, na, nb).ratio()
        if r >= SPELL_MIN:
            return "spelling", round(r, 3)
    return None


def find_candidates(entities: list[tuple[str, str, int]], *, min_facts: int = MIN_FACTS,
                    pinyin=None, limit: int = 400) -> list[Candidate]:
    rows = [(c, n, f) for c, n, f in entities
            if f >= min_facts and (n or "").strip() and not is_speaker_tag(n)]
    weight = {"initials": 1.0, "translit": 0.8, "spelling": 0.7, "substring": 0.5}
    out: list[Candidate] = []
    for i, (ca, na, fa) in enumerate(rows):
        for cb, nb, fb in rows[i + 1:]:
            hit = _pair(na, nb, pinyin)
            if not hit:
                continue
            why, score = hit
            out.append(Candidate(a=ca, b=cb, why=why, score=score, facts_a=fa, facts_b=fb))
    out.sort(key=lambda c: -(c.facts_total * weight.get(c.why, 0.5) * c.score))
    return out[:limit] if limit else out


def pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)
