"""Build topic presentation groups from vocabulary and facts; grouping does not rewrite the underlying codebook."""

from __future__ import annotations

import re

from .who import is_speaker_tag, norm_who


SPREAD_MIN_HITS = 20


SPREAD_GENERIC = 0.75


WHO_GENERIC = 0.85


SPEAKER_TAG_MAX = 0.5


_ASCII_TERM = re.compile(r"^[0-9A-Za-z][0-9A-Za-z .+#_-]*$")


_HAS_CJK = re.compile('[\u4e00-\u9fff]')


def has_cjk(term: str) -> bool:
    return bool(_HAS_CJK.search(term or ""))


class TopicFace:
    AXIS = "topics"
    GENERIC = SPREAD_GENERIC

    def _keys(self, f) -> tuple:
        return tuple(getattr(f, "topics", None) or ())

    def __init__(self, facts, units_for=None) -> None:
        self._units_for = units_for
        self.by_unit: dict[str, list] = {}
        self.all: list = []
        prior: dict[str, int] = {}
        for f in facts:
            self.all.append(f)
            self.by_unit.setdefault(getattr(f, "unit", "") or "", []).append(f)
            for t in self._keys(f):
                prior[t] = prior.get(t, 0) + 1
        total = sum(prior.values()) or 1
        self.ps = [v / total for v in prior.values()]
        self._memo: dict[str, tuple[int, int]] = {}

        self.usable = True


    def expected(self, n: int) -> float:
        return sum(1.0 - (1.0 - p) ** n for p in self.ps)

    @staticmethod
    def _rx(term: str):
        if _ASCII_TERM.match(term or ""):
            return re.compile(rf"(?<![0-9A-Za-z]){re.escape(term)}(?![0-9A-Za-z])", re.I)
        return re.compile(re.escape(term or ""), re.I)

    def _pool(self, term: str):
        if self._units_for is None:
            return self.all
        try:
            units = self._units_for(term)
        except Exception:      # noqa: BLE001
            return self.all
        if units is None:
            return self.all
        return [f for u in units for f in self.by_unit.get(u, ())]


    def face(self, term: str) -> tuple[int, int]:
        hit = self._memo.get(term)
        if hit is not None:
            return hit
        rx = self._rx(term)
        seen: dict[str, int] = {}
        for f in self._pool(term):
            if rx.search(getattr(f, "text", "") or ""):
                for t in self._keys(f):
                    seen[t] = seen.get(t, 0) + 1
        out = (sum(seen.values()), len(seen))
        if len(self._memo) >= 8192:
            self._memo.clear()
        self._memo[term] = out
        return out

    def spread(self, term: str) -> float | None:
        n, k = self.face(term)
        if n < SPREAD_MIN_HITS:
            return None
        e = self.expected(n)
        return (k / e) if e > 0 else None

    def generic(self, term: str) -> bool | None:
        if not self.usable:
            return None
        s = self.spread(term)
        return None if s is None else s >= self.GENERIC


class WhoFace(TopicFace):
    AXIS = "who"
    GENERIC = WHO_GENERIC

    def _keys(self, f) -> tuple:
        w = norm_who(getattr(f, "who", "") or "")
        return (w,) if w else ()

    def __init__(self, facts, units_for=None) -> None:
        super().__init__(facts, units_for)
        filled = tagged = 0
        for f in self.all:
            for w in self._keys(f):
                filled += 1
                if is_speaker_tag(w):
                    tagged += 1
        self.filled = filled
        self.speaker_share = (tagged / filled) if filled else 0.0

        self.usable = filled > 0 and self.speaker_share < SPEAKER_TAG_MAX
