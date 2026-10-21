"""Map a check failure to an applicable judge dimension without inventing an unavailable criterion."""

from __future__ import annotations

from ..state import State


MECHANICS = "mechanics"


def pick_dimension(st: State, *candidates: str) -> str:
    have = {d.name for d in st.mode.dims}
    return next((c for c in candidates if c in have), MECHANICS)
