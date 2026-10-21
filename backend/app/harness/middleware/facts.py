"""Accumulate material across rounds, and trim it -- welded together.

Two separate bugs came out of doing only one half:

* **Reset per round.** The output accumulates but the material didn't, so
  round 3's scoring judged the whole piece using only round 3's material.
  This shipped in note_harness, then again in compose_block, then sat
  undiscovered in writing_plan (where measurements later showed its rounds
  losing 0.278 on average while the other two held steady).
* **No ceiling.** Three separate accumulators grew without bound.

Welding them means there is no way to write "accumulate but don't trim".
"""

from __future__ import annotations

import re

from ..params import FACT_INDEX
from ..state import State


_FACT_ID = re.compile(r"^\[([A-Za-z0-9_\-]+)\]")


class Facts:
    """Fold this round's haul into the run's material.

    Note this trims a *list of fact strings*; it is not the same thing as
    ``Compact``, which folds a long body of prose into section summaries.
    Different shapes, different functions -- they were conflated once in the
    design and it produced a call to a function that doesn't exist.
    """

    name = "facts"
    hooks = ("after_prepare",)
    after: tuple[str, ...] = ()

    async def after_prepare(self, st: State) -> None:
        if st.bag.get("cleanup_only"):
            # A repair round does not go looking for material, so "found
            # nothing" is not a finding about the material. Counting it as a
            # dry round measured wrong immediately: two repair rounds in a row
            # and the run stopped with "material_used_up" on a note whose
            # knowledge base had just returned 22 facts.
            return


        all_facts = st.bag.setdefault("facts_all", [])


        pinned = [f for f in (st.bag.get("tray_lines") or []) if f]
        fresh = [f for f in st.facts_new if f not in all_facts and f not in pinned]
        all_facts.extend(fresh)
        if FACT_INDEX:
            budget = st.mode.fact_budget
            st.facts = pinned + (all_facts[-budget:] if budget else list(all_facts))
            st.bag["facts_index"] = _index_lines(
                all_facts[:-budget] if budget else [], st.bag.get("ledger"))
        else:

            st.facts = pinned + all_facts[-st.mode.fact_budget:]
            st.bag["facts_index"] = []

        if st.trace is not None:
            for chart in _mermaid_of(st.trace):
                if chart not in st.charts:
                    st.charts.append(chart)

        # A round that brought back nothing new. Long-form harnesses use this
        # to notice the topic is exhausted -- though see the note in modes.py:
        # the existing threshold almost never fires, because every round
        # retrieves fact rows that differ in wording while saying the same thing.
        st.bag["dry_rounds"] = 0 if fresh else st.bag.get("dry_rounds", 0) + 1


def _index_lines(older: list[str], ledger: dict | None) -> list[str]:
    facts = ((ledger or {}).get("facts") or {})
    out: list[str] = []
    for f in older:
        m = _FACT_ID.match(f)
        fid = m.group(1) if m else ""
        line = (facts.get(fid) or {}).get("line") if fid else ""
        if not line:
            line = f[len(fid) + 2:].strip() if fid else f
            line = line[:60]
        out.append(f"[{fid}] {line}" if fid else line)
    return out


def _mermaid_of(trace) -> list[str]:
    """Mermaid blocks the tools actually emitted.

    Kept so ``charts_from_tools`` can compare byte-for-byte: the model has
    been observed copying a tool's output and adjusting it, which produces
    charts that look right and don't render.
    """
    from ..checks.blockcheck import mermaid_blocks

    out: list[str] = []
    for _name, _args, result in trace.calls:
        out.extend(mermaid_blocks(result or ""))
    return out
