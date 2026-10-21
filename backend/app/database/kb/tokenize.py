"""Stable multilingual tokenization and stop-word rules for local retrieval; avoid process-random query ordering."""

from __future__ import annotations

import gzip
import math
import re
from pathlib import Path


MAXLEN = 4

_DICT = Path(__file__).with_name("cn_words.txt.gz")
_CJK = re.compile('[\u4e00-\u9fff]+')

_base: dict[str, int] | None = None


def base_words() -> dict[str, int]:
    global _base
    if _base is None:
        out: dict[str, int] = {}
        try:
            blob = gzip.decompress(_DICT.read_bytes()).decode("utf-8")
        except Exception:      # noqa: BLE001
            blob = ""
        for line in blob.split("\n"):
            if len(line) >= 3:
                out[line[:-1]] = ord(line[-1]) - 33
        _base = out
    return _base


class Tokenizer:
    __slots__ = ("_freq", "_maxlen", "_logtotal", "_memo", "_attest", "_amemo")


    EXTRA_FREQ = 96


    ATTEST_FREQ = 12

    def __init__(self, extra=(), attest=None) -> None:
        freq = dict(base_words())
        maxlen = MAXLEN
        for w in extra or ():
            w = str(w)
            if 2 <= len(w) <= 8 and _CJK.fullmatch(w):
                freq[w] = self.EXTRA_FREQ
                maxlen = max(maxlen, len(w))
        self._freq = freq
        self._maxlen = maxlen
        self._attest = attest
        self._amemo: dict[str, bool] = {}

        self._logtotal = math.log(sum(math.exp(v / 6.0) for v in freq.values()) or 1.0)
        self._memo: dict[str, tuple[str, ...]] = {}

    def enabled(self) -> bool:
        return bool(self._freq)

    def _attested(self, w: str) -> bool:
        hit = self._amemo.get(w)
        if hit is None:
            try:
                hit = bool(self._attest(w))
            except Exception:      # noqa: BLE001
                hit = False
            if len(self._amemo) >= 8192:
                self._amemo.clear()
            self._amemo[w] = hit
        return hit

    def cut(self, text: str) -> list[str]:
        out: list[str] = []
        pos = 0
        for m in _CJK.finditer(text or ""):
            if m.start() > pos:
                out.append(text[pos:m.start()])
            out.extend(self._cut_cjk(m.group()))
            pos = m.end()
        if pos < len(text or ""):
            out.append(text[pos:])
        return out

    def _cut_cjk(self, s: str) -> tuple[str, ...]:
        hit = self._memo.get(s)
        if hit is not None:
            return hit
        n = len(s)

        route: list[tuple[float, int]] = [(0.0, 0)] * (n + 1)
        for i in range(n - 1, -1, -1):
            best = (-1e18, i + 1)
            for L in range(1, min(self._maxlen, n - i) + 1):
                f = self._freq.get(s[i:i + L])
                if f is None and 2 <= L <= 3 and self._attest is not None:
                    f = self.ATTEST_FREQ if self._attested(s[i:i + L]) else None
                if f is None and L > 1:
                    continue
                lp = (f or 0) / 6.0 - self._logtotal + route[i + L][0]
                if lp > best[0]:
                    best = (lp, i + L)
            route[i] = best
        out: list[str] = []
        i = 0
        while i < n:
            j = route[i][1]
            out.append(s[i:j])
            i = j
        res = tuple(out)
        if len(self._memo) >= 4096:
            self._memo.clear()
        self._memo[s] = res
        return res


_default: Tokenizer | None = None


def default() -> Tokenizer:
    global _default
    if _default is None:
        _default = Tokenizer()
    return _default


def content_chars(run: str, text: str, cut, is_filler=None) -> int | None:
    i = (text or "").find(run)
    if i < 0:
        return None
    j = i + len(run)
    total = 0
    pos = 0
    for t in cut(text):
        a, b = pos, pos + len(t)
        pos = b


        if a >= j:
            break


        ov = min(b, j) - max(a, i)
        if ov >= 2 and len(t) >= 2 and _CJK.fullmatch(t):
            if is_filler is None or not is_filler(t):
                total += len(t)
    return total
