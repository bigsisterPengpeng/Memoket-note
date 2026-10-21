"""Ordering rules for the middleware chain, checked rather than assumed.

Two middleware on the same hook run in list order, and sometimes that matters
-- ``Compact`` reads the content ``Revise`` just rewrote. Those dependencies
used to live only in a comment, which is the same as living only in someone's
head.

Each middleware declares ``hooks`` (where it runs) and ``after`` (who must run
before it). This module verifies the assembled chain satisfies every
declaration, and the loop calls it once at startup so a bad order fails loudly
instead of producing subtly stale input.
"""

from __future__ import annotations

from typing import Sequence


class OrderError(RuntimeError):
    """The assembled chain violates a declared ordering dependency."""


def verify(chain: Sequence) -> None:
    """Raise if any middleware runs before something it declared ``after``.

    Only checks within a shared hook: ``Compact after Revise`` matters because
    both are on ``before_produce``. Two middleware on different hooks already
    have their order fixed by the loop.
    """
    positions = {getattr(m, "name", type(m).__name__): i for i, m in enumerate(chain)}
    for i, m in enumerate(chain):
        name = getattr(m, "name", type(m).__name__)
        my_hooks = set(getattr(m, "hooks", ()))
        for required in getattr(m, "after", ()):
            j = positions.get(required)
            if j is None:
                continue        # not in this chain at all; nothing to order against
            other = chain[j]
            if not (my_hooks & set(getattr(other, "hooks", ()))):
                continue        # different hooks -- the loop already orders them
            if j > i:
                raise OrderError(
                    f"{name!r} declares after={required!r} and they share a hook, "
                    f"but {required!r} is at position {j} and {name!r} at {i}. "
                    f"Fix the order in BASE or Mode.extra_mw.")


def describe(chain: Sequence) -> list[tuple[str, tuple[str, ...]]]:
    """(name, hooks) for the whole chain -- what runs, and where."""
    return [(getattr(m, "name", type(m).__name__), tuple(getattr(m, "hooks", ())))
            for m in chain]
