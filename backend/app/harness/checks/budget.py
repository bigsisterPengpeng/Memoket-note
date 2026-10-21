"""Bound repeated retrieval, generation and repair work within a run."""

from __future__ import annotations

import re

from ..state import State
from ..types import Verdict
from .grounding_rules import fact_usage
from .pick import pick_dimension


MIN_SECTION_CHARS = 600


USED_RATIO = 0.5


MIN_FACTS = 4


def section_budget(st: State) -> Verdict | None:
    if st.bag.get("outline_mode") or st.bag.get("polish"):


        return None
    if st.round >= st.mode.max_rounds:


        return None
    if len(st.facts) < MIN_FACTS:
        return None
    body = re.sub(r"\s", "", st.content or "")
    if len(body) >= MIN_SECTION_CHARS:
        return None
    used, _hit = fact_usage(st.content, st.facts)
    if used >= len(st.facts) * USED_RATIO:
        return None
    return Verdict(
        pick_dimension(st, "section_coverage", "beat_coverage", "material_use"),
        f'This section contains only one round of writing. Of the {len(st.facts)} available records, only {used} appear in the body. Continue an uncovered aspect rather than repeating the current topic. Choose unused material with a concrete project, time, number or decision and develop it into a paragraph.',
    )
