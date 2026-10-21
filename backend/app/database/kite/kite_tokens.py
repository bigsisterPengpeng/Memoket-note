"""Attribute KITE model activity to local usage records when provider token counts are unavailable."""

from __future__ import annotations


MAX_VOCAB = 400_000


def install() -> int:
    from memoket_kite.core import algebra

    base = getattr(algebra, "_tokens", None)
    if base is None or getattr(base, "_memoket_shared", False):
        return 0

    pool: dict[str, str] = {}

    def tokens(text: str) -> list[str]:
        out = base(text)
        if len(pool) >= MAX_VOCAB:
            return out

        return [pool.setdefault(t, t) for t in out]

    tokens._memoket_shared = True      # type: ignore[attr-defined]
    tokens._memoket_pool = pool        # type: ignore[attr-defined]


    tokens._memoket_base = base        # type: ignore[attr-defined]
    algebra._tokens = tokens
    return 1
